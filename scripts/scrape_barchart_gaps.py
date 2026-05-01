#!/usr/bin/env python3
"""
Scrape Barchart historical CSVs for specific gap ranges.

Reuses the Selenium helpers already living in ../RiseTrader/download_crude_oil_data.py
(login, set_frequency_dropdown, set_date_range, click_download_button, …) and drives
them range-by-range instead of the existing wallclock-duration loop.

Outputs land directly in data/downloads/barchart/{SYMBOL}_{TF}_{yyyymmdd}_{yyyymmdd}.csv
so scripts/import_barchart_csvs.py ingests them without any renames.

What it does per (symbol, gap_range):
    1. Navigate to the symbol's Barchart historical-download page.
    2. Set frequency to "Intraday" (specific-contract, NOT "Intraday Nearby"
       which rolls continuously and wouldn't match the URL ticker) with the
       requested aggregation minutes. Re-set per window — Barchart's UI
       occasionally reverts to Daily after a download.
    3. Walk end_date backward in 20-day windows (Barchart's typical intraday cap).
       For each window:
          a. set_start_date(window_start), set_end_date(window_end)
             (zero-padded day + dual-occurrence handling for days > 20)
          b. randomized 10-15s pre-wait, click download, wait for CSV
          c. dismiss Barchart notification overlay, re-focus Firefox
          d. rename the file to SYMBOL_TF_{start}_{end}.csv
          e. span-sanity check: if span > 2× window AND rows < window×10,
             flag as DAILY_SUSPECTED (Barchart silently served daily bars)
          f. randomized 15-20s post-wait before next window
    4. For CL futures: per window, resolve the active front-month contract
       (CLF, CLG, CLH, …) using NYMEX expiry = 3 business days before the 25th
       of the month PRIOR to delivery. That means e.g. bars in August 2025 live
       under CLU25 (Sep-delivery contract) most of the month.

Prerequisites
-------------
    * Firefox + geckodriver installed on the host.
    * .env has BARCHART_USERNAME and BARCHART_PASSWORD.
    * The RiseTrader repo sits alongside RiseTraderMVP (defaults to
      ../RiseTrader). Override with --risetrader-path.
    * pip install selenium webdriver-manager pandas python-dotenv

Run examples
------------
    # CrudeOIL 2025 gap-fill (5 holes) — uses monthly contract resolver
    python3 scripts/scrape_barchart_gaps.py \\
        --symbol CrudeOIL --interval 1 \\
        --start 2025-06-18 --end 2025-11-25

    # TSLA full M1 backfill, walk back from today until Barchart empties out
    python3 scripts/scrape_barchart_gaps.py \\
        --symbol TSLA --interval 1 \\
        --start 2010-06-29 --end 2026-04-21 \\
        --stop-on-empty

    # Dry run — print the download plan without launching Firefox
    python3 scripts/scrape_barchart_gaps.py --symbol CrudeOIL --interval 1 \\
        --start 2025-06-18 --end 2025-11-25 --dry-run
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import random
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv


# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
MVP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RISETRADER = MVP_ROOT.parent / "RiseTrader"
OUT_DIR = MVP_ROOT / "data" / "downloads" / "barchart"

WINDOW_DAYS = 20  # Barchart's intraday export cap — windows walk backward by this.

logger = logging.getLogger("scrape_barchart_gaps")


# ----------------------------------------------------------------------
# Barchart URLs per asset class — central registry so adding a new
# symbol only needs an entry in SYMBOL_CONFIG below.
# ----------------------------------------------------------------------
# Each entry: (profile, ticker, ...) — profile drives URL template.
# For continuous-front-month futures we use the *0 meta-symbol so
# Barchart auto-rolls and serves a clean stitched series.
SYMBOL_CONFIG: Dict[str, Dict[str, str]] = {
    # ─── Energy futures (NYMEX/ICE) ──────────────────────────────────
    "CrudeOIL":  {"profile": "futures", "ticker": "CL*0"},
    "BRENT_OIL": {"profile": "futures", "ticker": "BZ*0"},  # Brent ICE continuous
    "GASOLINE":  {"profile": "futures", "ticker": "RB*0"},  # RBOB NYMEX continuous
    # ─── Grain futures (CBOT) ────────────────────────────────────────
    "WHEAT":     {"profile": "futures", "ticker": "ZW*0"},
    "CORN":      {"profile": "futures", "ticker": "ZC*0"},
    # ─── Cash indices (Barchart hosts them under /futures/) ─────────
    "DXY":       {"profile": "futures", "ticker": "$DXY"},  # ICE USD index
    "VIX":       {"profile": "futures", "ticker": "$VIX"},  # CBOE volatility index
    # ─── Stocks (NASDAQ/NYSE) ────────────────────────────────────────
    "TSLA":      {"profile": "stock",   "ticker": "TSLA"},
    "MSFT":      {"profile": "stock",   "ticker": "MSFT"},
    # ─── Index cash quote ────────────────────────────────────────────
    "USA500":    {"profile": "stock",   "ticker": "$SPX"},  # S&P 500 cash
    # ─── Forex ───────────────────────────────────────────────────────
    "GBPJPY":    {"profile": "forex",   "ticker": "^GBPJPY"},
}

PROFILE_URL: Dict[str, str] = {
    "futures": "https://www.barchart.com/futures/quotes/{ticker}/historical-download",
    "stock":   "https://www.barchart.com/stocks/quotes/{ticker}/historical-download",
    "forex":   "https://www.barchart.com/forex/quotes/{ticker}/historical-download",
}


def url_for(symbol: str, ticker: str) -> str:
    cfg = SYMBOL_CONFIG.get(symbol)
    if cfg is None:
        raise ValueError(f"unsupported symbol: {symbol} (add to SYMBOL_CONFIG)")
    return PROFILE_URL[cfg["profile"]].format(ticker=ticker)


# ----------------------------------------------------------------------
# CL front-month contract resolver
# ----------------------------------------------------------------------
# NYMEX CL contracts: expiry = 3 business days before the 25th of the month
# PRIOR to delivery. Month codes: F=Jan, G=Feb, H=Mar, J=Apr, K=May, M=Jun,
# N=Jul, Q=Aug, U=Sep, V=Oct, X=Nov, Z=Dec.
CL_MONTH_CODES = "FGHJKMNQUVXZ"


def _business_days_before(d: date, n: int) -> date:
    cur = d
    while n > 0:
        cur -= timedelta(days=1)
        if cur.weekday() < 5:
            n -= 1
    return cur


def _expiry_for_delivery(delivery_year: int, delivery_month: int) -> date:
    prior = date(delivery_year, delivery_month, 1) - timedelta(days=1)
    anchor = date(prior.year, prior.month, 25)
    return _business_days_before(anchor, 3)


def cl_contract_for(d: date) -> str:
    """Return Barchart CL ticker (e.g. CLH25) active on calendar date d."""
    y = d.year
    m = d.month
    for dm_offset in range(0, 6):
        dm = m + dm_offset
        dy = y
        if dm > 12:
            dm -= 12
            dy += 1
        expiry = _expiry_for_delivery(dy, dm)
        if d <= expiry:
            code = CL_MONTH_CODES[dm - 1]
            return f"CL{code}{str(dy)[-2:]}"
    code = CL_MONTH_CODES[(m - 1) % 12]
    return f"CL{code}{str(y)[-2:]}"


# Legacy alias kept for backward compatibility — same data now lives in
# SYMBOL_CONFIG above. The resolve_ticker() function reads from there.
FIXED_TICKER: Dict[str, str] = {sym: cfg["ticker"] for sym, cfg in SYMBOL_CONFIG.items()}


def resolve_ticker(symbol: str, window_end: date) -> str:
    """Return the Barchart ticker for a given MT4 symbol on a given date.
    For futures we always use the *0 continuous meta-symbol — Barchart
    auto-rolls at expiry, so no per-contract resolution needed. For
    cash/stock/forex symbols the ticker is fixed."""
    cfg = SYMBOL_CONFIG.get(symbol)
    if cfg is None:
        raise ValueError(f"unsupported symbol: {symbol}")
    return cfg["ticker"]


# ----------------------------------------------------------------------
# Helper import from RiseTrader scraper
# ----------------------------------------------------------------------
def load_risetrader_helpers(risetrader_path: Path):
    """Dynamically import the existing scraper as a module."""
    script = risetrader_path / "download_crude_oil_data.py"
    if not script.exists():
        raise FileNotFoundError(f"can't find scraper at {script}")
    spec = importlib.util.spec_from_file_location("rt_scraper", script)
    mod = importlib.util.module_from_spec(spec)
    # Ensure that helper uses selenium imports from its own environment.
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    # Only pull the stable helpers from the base file; date/frequency
    # handling + notification dismissal use V9-equivalent versions
    # embedded directly below (see _set_frequency_intraday, _set_start_date,
    # _set_end_date, _set_single_date, _click_on_historical_download_div,
    # _click_center_of_screen).
    required = [
        "login",
        "set_total_volume_checkbox",
        "click_download_button",
        "wait_for_downloads_to_complete",
    ]
    missing = [n for n in required if not hasattr(mod, n)]
    if missing:
        raise ImportError(f"scraper missing helpers: {missing}")
    return mod


# ----------------------------------------------------------------------
# Firefox driver pointed at our output directory
# ----------------------------------------------------------------------
def make_driver(download_dir: Path):
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium import webdriver
    from webdriver_manager.firefox import GeckoDriverManager

    download_dir.mkdir(parents=True, exist_ok=True)
    opts = FirefoxOptions()
    # V9-parity: suppress every Firefox download UI that can obscure the
    # page and block subsequent clicks.
    opts.set_preference("browser.download.folderList", 2)
    opts.set_preference("browser.download.dir", str(download_dir))
    opts.set_preference("browser.download.manager.showAlertOnComplete", False)
    opts.set_preference("browser.download.manager.showWhenStarting", False)
    opts.set_preference("browser.download.panel.shown", False)
    opts.set_preference("browser.download.alwaysOpenPanel", False)
    opts.set_preference("browser.download.manager.closeWhenDone", True)
    opts.set_preference("browser.download.manager.focusWhenStarting", False)
    opts.set_preference("dom.webnotifications.enabled", False)
    # Include octet-stream for the cases where Barchart serves CSV with
    # that Content-Type, otherwise Firefox prompts instead of auto-saving.
    opts.set_preference(
        "browser.helperApps.neverAsk.saveToDisk",
        "text/csv,application/csv,application/vnd.ms-excel,application/octet-stream",
    )
    # Uncomment for headless:
    # opts.add_argument("--headless")

    service = FirefoxService(GeckoDriverManager().install())
    return webdriver.Firefox(service=service, options=opts)


# ----------------------------------------------------------------------
# V9-equivalent helpers embedded locally
# ----------------------------------------------------------------------
# The base RiseTrader/download_crude_oil_data.py ships older date-picker
# handling that (a) uses `str(day)` without zero padding, so single-digit
# days never match DOM labels like "05", and (b) has no disambiguation
# when Barchart's calendar renders overflow days from the adjacent month
# (30/31 can appear twice non-muted). V9 fixed both. We replicate V9's
# versions here so the MVP scraper is self-contained and doesn't depend
# on which revision of the base file happens to be on disk.
def _set_single_date(driver, date_input, target_date) -> bool:
    """Set a date via Barchart's picker. Tries three commit strategies in
    order, because recent Barchart UI revisions stopped honoring
    `execute_script('arguments[0].click()')` on picker day buttons — the
    picker closes but never writes the value back to the input.
      1. Native selenium .click() on the day button (dispatches real
         pointer events; most likely to satisfy the Vue/Angular binding).
      2. ActionChains move + click.
      3. Fallback: clear the input and type the date directly
         (mm/dd/yyyy) + TAB. Many bc-datepicker builds accept this.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    expected_date = target_date.strftime("%m/%d/%Y")

    # Diagnostic: what's in the input BEFORE we touch it? Helps tell
    # "picker commit failed" from "wrong input selector" in the logs.
    try:
        pre_value = date_input.get_attribute("value")
        logger.info("date input pre-value=%r (expecting to set to %s)", pre_value, expected_date)
    except Exception:
        pass

    date_input.click()
    logger.info("clicked on date input for %s", target_date)
    try:
        date_picker = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "bc-datepicker"))
        )

        # Anti-bot unlock dance: click Today first, then re-open + navigate.
        if _click_today_in_picker(driver):
            time.sleep(0.6)
            try:
                date_input.click()
                date_picker = WebDriverWait(driver, 10).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "bc-datepicker"))
                )
            except Exception as exc:
                logger.debug("picker re-open after Today failed: %s", exc)

        max_iterations = 264
        iterations = 0
        while iterations < max_iterations:
            current_month_year = date_picker.find_element(By.CLASS_NAME, "text-center").text
            target_month_year = target_date.strftime("%B %Y")
            if target_month_year in current_month_year:
                logger.info("navigated to %s", target_month_year)
                break
            current_date = datetime.strptime(current_month_year, "%B %Y").date().replace(day=1)
            target_month_start = date(target_date.year, target_date.month, 1)
            if target_month_start < current_date:
                date_picker.find_element(By.CLASS_NAME, "bc-glyph-chevron-left").click()
            else:
                date_picker.find_element(By.CLASS_NAME, "bc-glyph-chevron-right").click()
            time.sleep(0.5)
            iterations += 1

        if iterations == max_iterations:
            logger.error("failed to navigate to %s after %d attempts",
                         target_date.strftime("%B %Y"), max_iterations)
            return False

        # Let the calendar render finish binding events after the last nav.
        time.sleep(1.0)

        # V9 fix #1: zero-padded day string so "05" matches "05".
        target_day_str = f"{target_date.day:02d}"
        target_day = target_date.day
        date_buttons = date_picker.find_elements(By.CSS_SELECTOR, "button.btn-item")
        matching_buttons = []
        for button in date_buttons:
            if button.text == target_day_str and "text-muted" not in button.get_attribute("class"):
                matching_buttons.append(button)
            if len(matching_buttons) == 2 or button == date_buttons[-1]:
                break

        if not matching_buttons:
            logger.error("could not find non-muted button for day %s", target_day_str)
            return False

        # V9 fix #2: for days > 20 the calendar often shows the current
        # month's XX and the *next* month's XX both un-muted; the target
        # is the second occurrence.
        target_button = (
            matching_buttons[1]
            if target_day > 20 and len(matching_buttons) > 1
            else matching_buttons[0]
        )

        # Strategy 1: native selenium click (real pointer event).
        try:
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", target_button
            )
            time.sleep(0.4)
            target_button.click()
            logger.info("clicked on %s (native)", target_date.strftime("%B %d, %Y"))
        except Exception as exc:
            logger.debug("native click failed: %s", exc)
            try:
                ActionChains(driver).move_to_element(target_button).pause(0.2).click().perform()
                logger.info("clicked on %s (action-chains)", target_date.strftime("%B %d, %Y"))
            except Exception as exc2:
                logger.debug("action-chains click failed: %s", exc2)
                driver.execute_script("arguments[0].click();", target_button)
                logger.info("clicked on %s (js-fallback)", target_date.strftime("%B %d, %Y"))

        time.sleep(1.5)
        selected_date = date_input.get_attribute("value")
        if selected_date == expected_date:
            return True
        logger.warning(
            "picker click didn't commit: got=%s expected=%s — trying direct keyboard input",
            selected_date, expected_date,
        )

        # Strategy 2: type the date directly into the input.
        try:
            # Re-focus the input; use keyboard to wipe existing value and type fresh.
            date_input.click()
            time.sleep(0.3)
            date_input.send_keys(Keys.END)
            for _ in range(14):
                date_input.send_keys(Keys.BACK_SPACE)
            time.sleep(0.2)
            date_input.send_keys(expected_date)
            date_input.send_keys(Keys.TAB)
            time.sleep(1.0)
            selected_date = date_input.get_attribute("value")
            if selected_date == expected_date:
                logger.info("direct-type succeeded: %s", selected_date)
                return True
            logger.warning(
                "direct-type also didn't stick: got=%s expected=%s",
                selected_date, expected_date,
            )
        except Exception as type_exc:
            logger.warning("direct-type attempt errored: %s", type_exc)

        # Strategy 3: brute-force the value via JS using the native
        # HTMLInputElement.prototype.value setter. Vue/React intercept the
        # default setter for controlled inputs; using the native one
        # bypasses that and triggers a real `input` event the framework
        # trusts. Also dispatch change + blur to flush form validators.
        try:
            js_code = (
                "var el = arguments[0]; var v = arguments[1];"
                "var setter = Object.getOwnPropertyDescriptor("
                "  HTMLInputElement.prototype, 'value'"
                ").set;"
                "setter.call(el, v);"
                "el.dispatchEvent(new Event('input',  { bubbles: true }));"
                "el.dispatchEvent(new Event('change', { bubbles: true }));"
                "el.dispatchEvent(new Event('blur',   { bubbles: true }));"
            )
            driver.execute_script(js_code, date_input, expected_date)
            time.sleep(1.5)
            selected_date = date_input.get_attribute("value")
            if selected_date == expected_date:
                logger.info("js-native-setter succeeded: %s", selected_date)
                return True
            logger.warning(
                "js-native-setter didn't stick: got=%s expected=%s",
                selected_date, expected_date,
            )
        except Exception as js_exc:
            logger.warning("js-native-setter errored: %s", js_exc)

        return False

    except Exception as exc:
        logger.error("error while setting date: %s", exc)
        return False


def _pick_date_input(driver, name: str):
    """Return the best candidate for the intraday-form date input.

    Barchart's historical-download page appears to render TWO forms —
    a Daily one (whose `input[name='dateFrom']` sits locked at the
    contract's historical floor, e.g. 11/01/2014) and an Intraday one.
    `find_element` returns the first match, which is often the locked
    Daily input. We enumerate all candidates, dump them for diagnostics,
    and pick the one that's (a) visible AND (b) doesn't carry the
    11/01/2014 floor marker. Fallback: last visible candidate.
    """
    from selenium.webdriver.common.by import By
    inputs = driver.find_elements(By.CSS_SELECTOR, f"input[name='{name}']")
    visible = []
    for idx, inp in enumerate(inputs):
        try:
            displayed = inp.is_displayed()
            val = inp.get_attribute("value") or ""
            enabled = inp.is_enabled()
            # Parent class helps tell daily-form from intraday-form.
            try:
                parent_cls = inp.find_element(By.XPATH, "./..").get_attribute("class") or ""
            except Exception:
                parent_cls = "?"
            logger.info(
                "  input[name='%s'][%d] visible=%s enabled=%s value=%r parent-class=%r",
                name, idx, displayed, enabled, val, parent_cls[:80],
            )
            if displayed:
                visible.append((inp, val, parent_cls))
        except Exception as exc:
            logger.debug("  candidate %d inspection failed: %s", idx, exc)
    if not visible:
        return None
    # Prefer candidate whose value is NOT the Daily-floor 11/01/2014.
    for inp, val, _cls in visible:
        if val and val != "11/01/2014":
            return inp
    # Prefer candidate whose parent class hints intraday.
    for inp, _val, cls in visible:
        low = (cls or "").lower()
        if "intraday" in low or "intra" in low:
            return inp
    # Fallback: last visible (newer DOM subtree is usually appended).
    return visible[-1][0]


def _click_today_in_picker(driver) -> bool:
    """Click the 'Today' button inside Barchart's open datepicker.

    Anti-bot workaround: Barchart's Vue datepicker appears to reject
    arbitrary day-button clicks on fresh load unless a 'known safe'
    interaction (clicking the built-in Today button) has committed a
    value first. Once that's done, subsequent day clicks in the same
    picker are accepted normally.
    """
    from selenium.webdriver.common.by import By
    try:
        picker = driver.find_element(By.CLASS_NAME, "bc-datepicker")
        for b in picker.find_elements(By.TAG_NAME, "button"):
            try:
                if b.text.strip().lower() == "today" and b.is_displayed():
                    b.click()
                    time.sleep(0.6)
                    logger.info("clicked Today in picker")
                    return True
            except Exception:
                continue
    except Exception as exc:
        logger.debug("couldn't find Today button: %s", exc)
    return False


def _clear_both_date_inputs(driver) -> None:
    """Clear BOTH dateFrom and dateTo inputs up-front. Barchart's form
    relocks one date when you try to set only the other, so we empty both
    before attempting any set. Opens each picker, clicks Clear, and
    closes the picker (via Escape or Close) so the next picker-open on
    the real target date starts from a clean slate.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    for which in ("dateFrom", "dateTo"):
        inp = _pick_date_input(driver, which)
        if inp is None:
            logger.warning("pre-clear: no input[name='%s'] — skipping", which)
            continue
        try:
            pre = inp.get_attribute("value")
            logger.info("pre-clear %s: current=%r", which, pre)
        except Exception:
            pre = None
        # Open the picker with retries — Barchart's JS handler binding
        # can be slow after a hard reload, especially for older dates
        # that touch lazy-loaded sub-modules.
        picker_opened = False
        for attempt in range(1, 4):
            try:
                if attempt == 1:
                    inp.click()
                else:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", inp
                    )
                    time.sleep(0.4)
                    driver.execute_script("arguments[0].click();", inp)
                WebDriverWait(driver, 12).until(
                    EC.visibility_of_element_located((By.CLASS_NAME, "bc-datepicker"))
                )
                picker_opened = True
                if attempt > 1:
                    logger.info("pre-clear %s: picker opened on attempt %d", which, attempt)
                break
            except Exception as exc:
                logger.debug("pre-clear %s: picker open attempt %d failed: %s",
                             which, attempt, exc)
                time.sleep(1.0)
        if not picker_opened:
            logger.warning("pre-clear %s: picker would not open after 3 attempts", which)
            continue
        cleared = _clear_picker(driver)
        try:
            post = inp.get_attribute("value")
            logger.info("pre-clear %s: cleared=%s post=%r", which, cleared, post)
        except Exception:
            pass
        # Close any lingering picker so the next iteration opens fresh.
        try:
            inp.send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.4)


def _clear_picker(driver) -> bool:
    """Click the Clear button inside Barchart's open datepicker popup.
    Vue's datepicker treats an already-valid value as locked and ignores
    subsequent day clicks; clearing the bound value unlocks it. Barchart
    used to render this as `button[data-ng-click='$clear()']`; also
    accept any visible button inside .bc-datepicker whose text is 'Clear'.
    """
    from selenium.webdriver.common.by import By

    # First try the angular-era selector (works on legacy builds).
    for selector in [
        "button[data-ng-click='$clear()']",
        ".bc-datepicker button[data-ng-click='$clear()']",
    ]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed():
                btn.click()
                time.sleep(0.4)
                logger.info("clicked Clear (ng-click)")
                return True
        except Exception:
            continue

    # Fallback: any visible button labeled 'Clear' inside the picker.
    try:
        picker = driver.find_element(By.CLASS_NAME, "bc-datepicker")
        for b in picker.find_elements(By.TAG_NAME, "button"):
            try:
                if b.text.strip().lower() == "clear" and b.is_displayed():
                    b.click()
                    time.sleep(0.4)
                    logger.info("clicked Clear (by text)")
                    return True
            except Exception:
                continue
    except Exception as exc:
        logger.debug("no picker open when searching for Clear: %s", exc)
    logger.debug("Clear button not found in picker")
    return False


def _interactive_set_date(driver, date_input, target_date) -> bool:
    """Navigate the picker to the right month (automated — chevron clicks
    work), then pause for the USER to click the target day with their real
    mouse in Firefox. Vue's datepicker accepts real-pointer clicks but
    ignores Selenium's. After the user presses Enter, verify the input
    value and return True on match, False (with retry prompt) otherwise.
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    expected_date = target_date.strftime("%m/%d/%Y")
    target_label = target_date.strftime("%B %Y")
    day_str = f"{target_date.day:02d}"

    # Diagnostic: what's in the input before we open the picker?
    try:
        pre_value = date_input.get_attribute("value")
        logger.info("INTERACTIVE: pre-value=%r (target=%s)", pre_value, expected_date)
    except Exception:
        pass

    date_input.click()
    try:
        date_picker = WebDriverWait(driver, 10).until(
            EC.visibility_of_element_located((By.CLASS_NAME, "bc-datepicker"))
        )
    except Exception as exc:
        logger.error("picker didn't open: %s", exc)
        return False

    # Anti-bot unlock dance: click Today first (Barchart's Vue layer
    # accepts this interaction), then re-open picker and navigate to the
    # real target month. Only after a legitimate Today commit does the
    # datepicker start accepting arbitrary day clicks.
    today_clicked = _click_today_in_picker(driver)
    if today_clicked:
        time.sleep(0.6)
        # Picker usually closes after Today. Re-open for the real pick.
        try:
            date_input.click()
            date_picker = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CLASS_NAME, "bc-datepicker"))
            )
        except Exception as exc:
            logger.warning("picker didn't re-open after Today: %s", exc)
            return False
        try:
            post_today_val = date_input.get_attribute("value")
            logger.info("after Today click: input=%r — now navigating to target", post_today_val)
        except Exception:
            pass

    # Chevron-walk to target month. These clicks DO commit — only the day
    # button click is problematic — so this part stays automated.
    max_iter = 264
    iterations = 0
    while iterations < max_iter:
        current = date_picker.find_element(By.CLASS_NAME, "text-center").text
        if target_label in current:
            logger.info("INTERACTIVE: picker on %s", target_label)
            break
        try:
            cur_first = datetime.strptime(current, "%B %Y").date().replace(day=1)
        except Exception:
            break
        target_first = date(target_date.year, target_date.month, 1)
        glyph = "bc-glyph-chevron-left" if target_first < cur_first else "bc-glyph-chevron-right"
        try:
            date_picker.find_element(By.CLASS_NAME, glyph).click()
        except Exception:
            break
        time.sleep(0.4)
        iterations += 1

    # Hand off to the human. Flush stdout so the prompt appears promptly.
    print("", flush=True)
    print("=" * 72, flush=True)
    print(f"  >>> CLICK DAY {day_str} of {target_label} in the Firefox calendar", flush=True)
    print(f"  >>> Target date: {expected_date}", flush=True)
    print(f"  >>> Then return to THIS TERMINAL and press Enter", flush=True)
    print("=" * 72, flush=True)

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            input(f"  [attempt {attempt}/{max_attempts}]  READY? [Enter to verify]  ")
        except EOFError:
            logger.error("stdin closed, cannot continue interactive mode")
            return False
        time.sleep(0.6)
        try:
            actual = date_input.get_attribute("value")
        except Exception as exc:
            logger.warning("couldn't read input value: %s", exc)
            actual = None
        if actual == expected_date:
            logger.info("INTERACTIVE: click committed %s", actual)
            # Close the picker by clicking outside (optional — the next
            # auto-step will click elsewhere anyway).
            return True
        print(f"  !! value is {actual!r}, expected {expected_date!r}. Try again.", flush=True)
    logger.warning("INTERACTIVE: gave up after %d attempts", max_attempts)
    return False


def _set_start_date(driver, start_date) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info("setting start date: %s", start_date)
    try:
        # Force a presence wait first so the DOM has had time to render.
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='dateFrom']"))
        )
        logger.info("enumerating dateFrom candidates:")
        start_input = _pick_date_input(driver, "dateFrom")
        if start_input is None:
            logger.error("no visible input[name='dateFrom'] found")
            return False
        if isinstance(start_date, datetime):
            start_date = start_date.date()
        ok = _set_single_date(driver, start_input, start_date)
        # V9 behavior: scroll back to top so end-date input is reachable.
        time.sleep(3)
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(2)
        value = start_input.get_attribute("value")
        expected = start_date.strftime("%m/%d/%Y")
        if ok and value == expected:
            return True
        logger.warning("start date verify failed: got=%s expected=%s", value, expected)
        return False
    except Exception as exc:
        logger.error("error setting start date: %s", exc)
        return False


def _set_end_date(driver, end_date, max_retries: int = 5) -> bool:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    logger.info("setting end date: %s", end_date)
    if isinstance(end_date, datetime):
        end_date = end_date.date()
    for attempt in range(max_retries):
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='dateTo']"))
            )
            logger.info("enumerating dateTo candidates (attempt %d):", attempt + 1)
            end_input = _pick_date_input(driver, "dateTo")
            if end_input is None:
                logger.warning("attempt %d: no visible input[name='dateTo']", attempt + 1)
                time.sleep(3)
                continue
            if _set_single_date(driver, end_input, end_date):
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, 0);")
                time.sleep(2)
                return True
            logger.warning("attempt %d: end date set failed", attempt + 1)
        except Exception as exc:
            logger.error("attempt %d: %s", attempt + 1, exc)
        time.sleep(3)
    logger.error("failed to set end date after %d attempts", max_retries)
    return False


def _set_symbol_input(driver, symbol: str) -> bool:
    """Type a symbol into Barchart's 'Search for a Symbol' input and
    press Enter. CRITICAL for CrudeOIL: navigating to /CL*0/ resolves
    the page to the current front-month label (e.g. CLM26) and shows
    that in the symbol input — but the form submits whatever is in
    the input. Without this step we'd download CLM26-only data even
    for old dates, which is wrong for backtesting (we want continuous
    front-month, not a single back-month contract).
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        inp = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[type='text'][aria-label*='Search for a Symbol']",
            ))
        )
        inp.clear()
        time.sleep(0.3)
        inp.send_keys(symbol)
        logger.info("typed symbol=%s into search input", symbol)
        time.sleep(1.0)  # let the autocomplete dropdown populate
        inp.send_keys(Keys.RETURN)
        time.sleep(2.0)  # let the form re-bind to the new symbol
        return True
    except Exception as exc:
        logger.warning("native symbol input failed: %s — trying JS fallback", exc)
    # JS fallback — same approach V9 uses when native input fails.
    try:
        js = (
            "var inp = document.querySelector("
            "  \"input[type='text'][aria-label*='Search for a Symbol']\""
            ");"
            "if (inp) {"
            "  inp.value = arguments[0];"
            "  inp.dispatchEvent(new Event('input', { bubbles: true }));"
            "  setTimeout(function() {"
            "    inp.dispatchEvent(new KeyboardEvent('keydown', {"
            "      key: 'Enter', code: 'Enter', which: 13, keyCode: 13,"
            "      bubbles: true"
            "    }));"
            "  }, 800);"
            "}"
        )
        driver.execute_script(js, symbol)
        time.sleep(2.5)
        logger.info("typed symbol=%s via JS fallback", symbol)
        return True
    except Exception as exc:
        logger.error("could not set symbol input to %s: %s", symbol, exc)
        return False


def _set_frequency_intraday(driver, minutes: int) -> None:
    """V9-style: select 'Intraday' (NOT 'Intraday Nearby') and type the
    aggregation minutes. Re-run every window so a Barchart UI revert to
    Daily gets re-corrected before the next download."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import Select, WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    try:
        dropdown = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "select[data-ng-model='frequency']"))
        )
        # "Intraday" (specific-contract intraday) is correct for
        # CLH25/CLM25/etc.; "Intraday Nearby" rolls continuously and
        # would not match the ticker in the URL.
        Select(dropdown).select_by_visible_text("Intraday")
        time.sleep(2)
        minutes_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='aggregation']"))
        )
        minutes_input.clear()
        minutes_input.send_keys(str(minutes))
        logger.info("frequency=Intraday aggregation=%d", minutes)
    except Exception as exc:
        logger.warning("couldn't set frequency/aggregation: %s", exc)


def _click_on_historical_download_div(driver) -> None:
    """V9-parity: click the 'historical-download' block to dismiss the
    Barchart 'download ready' notification overlay."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.action_chains import ActionChains

    try:
        elt = driver.find_element(By.CLASS_NAME, "historical-download")
        driver.execute_script("arguments[0].scrollIntoView(true);", elt)
        time.sleep(1)
        driver.execute_script("arguments[0].click();", elt)
        ActionChains(driver).move_to_element(elt).click().perform()
        logger.info("dismissed historical-download overlay")
    except Exception as exc:
        logger.debug("could not click historical-download div: %s", exc)


def _click_center_of_screen() -> None:
    """OS-level click via pyautogui to re-focus Firefox after a download.
    Optional — no-op when pyautogui isn't available (e.g. a headless or
    restricted Mac that hasn't granted Accessibility permissions)."""
    try:
        import pyautogui  # lazy import keeps the script cheap if it's not installed
        w, h = pyautogui.size()
        pyautogui.moveTo(w / 2, h / 2, duration=0.2)
        pyautogui.click()
        logger.info("re-focused Firefox via OS-level center click")
    except Exception as exc:
        logger.debug("pyautogui click skipped: %s", exc)


# ----------------------------------------------------------------------
# Window iteration + file naming
# ----------------------------------------------------------------------
def backward_windows(start: date, end: date, window_days: int) -> List[Tuple[date, date]]:
    """Yield (win_start, win_end) pairs covering [start, end], walking backward."""
    windows: List[Tuple[date, date]] = []
    cur_end = end
    while cur_end >= start:
        cur_start = max(start, cur_end - timedelta(days=window_days - 1))
        windows.append((cur_start, cur_end))
        if cur_start == start:
            break
        cur_end = cur_start - timedelta(days=1)
    return windows


def rename_latest(download_dir: Path, symbol: str, tf: str, win_start: date, win_end: date) -> Optional[Path]:
    """Rename the newest CSV in download_dir to SYMBOL_TF_YYYYMMDD_YYYYMMDD.csv."""
    csvs = sorted(download_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Don't re-touch files already named in our convention.
    csvs = [p for p in csvs if not p.stem.startswith(f"{symbol}_{tf}_")]
    if not csvs:
        logger.warning("no fresh CSV in %s after download", download_dir)
        return None
    latest = csvs[0]
    new_name = f"{symbol}_{tf}_{win_start:%Y%m%d}_{win_end:%Y%m%d}.csv"
    new_path = download_dir / new_name
    # If there's already a file there from a re-run, overwrite.
    if new_path.exists():
        new_path.unlink()
    latest.rename(new_path)
    return new_path


def inspect_csv(path: Path) -> Dict[str, object]:
    """
    Return a quick-look summary of a downloaded CSV so the scrape loop can
    distinguish between: valid data, Barchart empty-range filler, throttle/
    CAPTCHA HTML dump, or wrong-frequency mis-hit (daily bars in place of
    intraday).

    Keys returned:
        rows       : int data-row count (excluding header & blank lines)
        first_ts   : str ISO timestamp of the first data row (or "")
        last_ts    : str ISO timestamp of the last data row (or "")
        span_days  : int (last_ts - first_ts) in days, or 0 if unknown
        looks_html : True if file looks like an HTML error/CAPTCHA page
        size       : int byte size on disk
    """
    out: Dict[str, object] = {"rows": 0, "first_ts": "", "last_ts": "",
                              "span_days": 0, "looks_html": False, "size": 0}
    try:
        out["size"] = path.stat().st_size
        head = path.read_bytes()[:512].lstrip().lower()
        if head.startswith(b"<!doctype html") or head.startswith(b"<html"):
            out["looks_html"] = True
            return out
        import pandas as pd  # local import to keep dry-run cheap
        df = pd.read_csv(path)
        if df.empty or len(df.columns) < 2:
            return out
        out["rows"] = int(len(df))
        time_col = next((c for c in df.columns
                         if c.lower().strip() in ("time", "date", "datetime", "timestamp")), None)
        if time_col:
            try:
                # Barchart sometimes appends a footer row (e.g. "Downloaded from…").
                # Drop the last row before computing span to stay aligned with V9's
                # `iloc[-2]` pattern.
                ts_all = pd.to_datetime(df[time_col], errors="coerce")
                ts = ts_all.iloc[:-1].dropna() if len(ts_all) > 1 else ts_all.dropna()
                if len(ts):
                    first = ts.min()
                    last = ts.max()
                    out["first_ts"] = str(first)
                    out["last_ts"] = str(last)
                    try:
                        out["span_days"] = int((last - first).days)
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception as exc:
        logger.debug("inspect_csv error %s: %s", path.name, exc)
    return out


def is_csv_empty_ish(info: Dict[str, object]) -> bool:
    """Small data OR HTML error page → treat as no-data for stop-on-empty."""
    return bool(info.get("looks_html")) or int(info.get("rows", 0)) < 5


def is_csv_span_suspicious(info: Dict[str, object], window_days: int) -> bool:
    """Span sanity check — V9's `parse_and_rename_file` flags files where
    the time span is nowhere near the requested window. That's the classic
    "Barchart silently served Daily instead of Intraday" signature: one bar
    per day × 20 days spans ~20 days but only has 20 rows. We flag when
    the observed span is more than 2× the requested window AND row count
    is suspiciously low (<= window_days * 10 → impossible for real M1 or
    M5 data)."""
    span = int(info.get("span_days", 0))
    rows = int(info.get("rows", 0))
    if span <= 0 or rows <= 0:
        return False
    # Real intraday for a 20-day window: M1 → ~6.5k–25k rows, M5 → ~1.3k–5k rows.
    # Daily bars over the same window: ~20 rows. Catch the daily-bar case.
    if span > window_days * 2 and rows < window_days * 10:
        return True
    return False


# ----------------------------------------------------------------------
# Main loop
# ----------------------------------------------------------------------
def scrape(
    symbol: str,
    tf_minutes: int,
    start_date: date,
    end_date: date,
    risetrader_path: Path,
    stop_on_empty: bool = False,
    dry_run: bool = False,
    interactive: bool = False,
) -> None:
    tf_label = {1: "M1", 5: "M5", 15: "M15"}.get(tf_minutes, f"M{tf_minutes}")
    windows = backward_windows(start_date, end_date, WINDOW_DAYS)
    logger.info(
        "scrape plan  symbol=%s tf=%s  %s -> %s  windows=%d",
        symbol, tf_label, start_date, end_date, len(windows),
    )
    for w in windows[:3]:
        logger.info("  first window: %s -> %s  ticker=%s", w[0], w[1], resolve_ticker(symbol, w[1]))

    if dry_run:
        return

    helpers = load_risetrader_helpers(risetrader_path)
    driver = make_driver(OUT_DIR)
    try:
        if not helpers.login(driver):
            logger.error("login failed — aborting")
            return

        prev_ticker: Optional[str] = None
        empty_in_a_row = 0

        for i, (ws, we) in enumerate(windows, start=1):
            ticker = resolve_ticker(symbol, we)
            logger.info("[%d/%d] %s  %s -> %s  ticker=%s", i, len(windows), symbol, ws, we, ticker)

            # Navigate to the ticker page on EVERY window. Plain
            # `driver.get` is NOT enough — Barchart caches form state
            # in localStorage/sessionStorage so the date inputs come
            # back populated with whatever was last set ('07/13/2025'
            # etc.) and the picker click handlers don't re-bind. We
            # nuke browser storage and force a hard reload to make
            # the JS re-bind from scratch every window.
            target = url_for(symbol, ticker)
            logger.info("  navigating: %s", target)
            driver.get(target)
            time.sleep(2)
            try:
                driver.execute_script(
                    "try{window.localStorage.clear();}catch(e){}"
                    "try{window.sessionStorage.clear();}catch(e){}"
                )
                logger.info("  cleared local + session storage")
            except Exception as exc:
                logger.debug("  storage clear failed: %s", exc)
            try:
                driver.execute_script("window.location.reload(true);")
                logger.info("  hard-reloaded page (cache-bypass)")
                time.sleep(5)  # full re-render + JS rebind
            except Exception as exc:
                logger.warning("  hard reload failed: %s", exc)
                time.sleep(3)
            navigated_now = True
            prev_ticker = ticker

            # CRITICAL for CrudeOIL: type 'CL*0' into the symbol input
            # every window after the hard reload. The reload wipes the
            # symbol back to whatever was URL-resolved (CLM26), so we
            # need to retype CL*0 to keep the form on continuous
            # front-month data.
            if symbol == "CrudeOIL":
                _set_symbol_input(driver, "CL*0")
                time.sleep(3)  # let the form fully bind after symbol change

            # V9-parity: re-set frequency + aggregation + volume EVERY
            # window. Barchart's UI occasionally reverts to Daily after a
            # download, which would silently serve daily bars for the
            # rest of the run if we only set these on ticker change.
            _set_frequency_intraday(driver, tf_minutes)
            try:
                helpers.set_total_volume_checkbox(driver)
            except Exception as exc:
                logger.debug("  volume checkbox pass failed (non-fatal): %s", exc)

            # Dates: interactive mode hands off the day click to the
            # human (Barchart's Vue datepicker rejects programmatic
            # clicks). Non-interactive tries four commit strategies.
            # Either way, BOTH dates must be cleared first — Barchart
            # re-locks one when you try to set only the other.
            if interactive:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support.ui import WebDriverWait
                from selenium.webdriver.support import expected_conditions as EC
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "input[name='dateFrom']"))
                    )
                    _clear_both_date_inputs(driver)
                    start_input = _pick_date_input(driver, "dateFrom")
                    if start_input is None or not _interactive_set_date(driver, start_input, ws):
                        logger.warning("  interactive start date failed; skipping window")
                        continue
                    time.sleep(1)
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                    end_input = _pick_date_input(driver, "dateTo")
                    if end_input is None or not _interactive_set_date(driver, end_input, we):
                        logger.warning("  interactive end date failed; skipping window")
                        continue
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(1)
                except Exception as exc:
                    logger.error("  interactive date flow errored: %s", exc)
                    continue
            else:
                # Pre-clear both inputs once per window.
                try:
                    _clear_both_date_inputs(driver)
                except Exception as exc:
                    logger.debug("  pre-clear both failed (non-fatal): %s", exc)
                if not _set_start_date(driver, ws):
                    logger.warning("  start date set failed; skipping window")
                    continue
                if not _set_end_date(driver, we):
                    logger.warning("  end date set failed; skipping window")
                    continue

            # V9 uses randomized 10-15s to look like a human + avoid
            # tripping Barchart's rate-limiter on long runs.
            pre_wait = random.randint(10, 15)
            logger.info("  waiting %ds before download", pre_wait)
            time.sleep(pre_wait)

            helpers.click_download_button(driver, str(OUT_DIR))
            # Brief post-click gap so Firefox can actually start writing.
            time.sleep(5)
            if not helpers.wait_for_downloads_to_complete(str(OUT_DIR)):
                logger.warning("  download didn't complete — moving on")
                continue

            # Dismiss Barchart's "download ready" overlay and re-focus
            # Firefox so the next date-picker click isn't intercepted.
            time.sleep(2)
            _click_on_historical_download_div(driver)
            _click_center_of_screen()

            saved = rename_latest(OUT_DIR, symbol, tf_label, ws, we)
            if saved is None:
                continue

            info = inspect_csv(saved)
            if info["looks_html"]:
                logger.error(
                    "  !! %s looks like an HTML page (CAPTCHA / block) — size=%d bytes",
                    saved.name, info["size"],
                )
            elif is_csv_span_suspicious(info, WINDOW_DAYS):
                # Almost certainly Barchart served Daily instead of
                # Intraday. Rename so the importer skips it and the user
                # can see it in the output directory.
                bad_path = saved.with_name(saved.stem + ".DAILY_SUSPECTED.csv")
                try:
                    saved.rename(bad_path)
                except Exception:
                    pass
                logger.error(
                    "  !! %s span=%dd rows=%d — looks like Daily bars, flagged as DAILY_SUSPECTED",
                    saved.name, int(info.get("span_days", 0)), info["rows"],
                )
            else:
                logger.info(
                    "  saved %s  rows=%d  span=%dd  first=%s  last=%s  (%d bytes)",
                    saved.name, info["rows"], int(info.get("span_days", 0)),
                    info["first_ts"] or "—", info["last_ts"] or "—", info["size"],
                )

            if stop_on_empty and is_csv_empty_ish(info):
                empty_in_a_row += 1
                logger.info("  empty/blocked CSV (%d/2)", empty_in_a_row)
                if empty_in_a_row >= 2:
                    reason = "hit history limit" if not info["looks_html"] else "likely rate-limited"
                    logger.info("  two empty windows in a row — stopping (%s)", reason)
                    break
            else:
                empty_in_a_row = 0

            # V9-parity: randomized 15-20s between iterations.
            post_wait = random.randint(15, 20)
            logger.info("  waiting %ds before next window", post_wait)
            time.sleep(post_wait)

    finally:
        try:
            driver.quit()
        except Exception:
            pass


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", required=True, choices=sorted(SYMBOL_CONFIG.keys()))
    ap.add_argument("--interval", type=int, default=1, help="aggregation minutes (1, 5, 15)")
    ap.add_argument("--start", required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--end",   required=True, help="YYYY-MM-DD (inclusive)")
    ap.add_argument("--risetrader-path", default=str(DEFAULT_RISETRADER),
                    help=f"path to RiseTrader repo with scraper helpers (default: {DEFAULT_RISETRADER})")
    ap.add_argument("--stop-on-empty", action="store_true",
                    help="halt after 2 consecutive empty windows (use when probing max history)")
    ap.add_argument("--dry-run", action="store_true", help="print plan, no browser")
    ap.add_argument("--interactive", action="store_true",
                    help="script navigates calendar to target month, then pauses for YOU to "
                         "click the day with a real mouse (Barchart's Vue datepicker rejects "
                         "programmatic day-button clicks).")
    return ap.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)s  %(message)s",
    )
    load_dotenv(MVP_ROOT / ".env")

    args = parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end   = datetime.strptime(args.end, "%Y-%m-%d").date()

    if not args.dry_run:
        if not os.getenv("BARCHART_USERNAME") or not os.getenv("BARCHART_PASSWORD"):
            logger.error("BARCHART_USERNAME / BARCHART_PASSWORD not in .env — aborting")
            return 1

    scrape(
        symbol=args.symbol,
        tf_minutes=args.interval,
        start_date=start,
        end_date=end,
        risetrader_path=Path(args.risetrader_path),
        stop_on_empty=args.stop_on_empty,
        dry_run=args.dry_run,
        interactive=args.interactive,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
