#!/usr/bin/env bash
# ==============================================================================
# daily_health.sh — RiseTrader automated daily health checks
#
# Add to crontab via `crontab -e`. Uncomment lines as you opt into automation.
#
# How to enable:
#   1. Set PROJECT_DIR to the absolute path of your RiseTraderMVP checkout.
#   2. Uncomment the cron entries you want to run.
#   3. Run `crontab -e` and paste the block.
#
# Logs are written to $PROJECT_DIR/logs/ (created if absent).
# The exit code of each script is preserved in the log filename suffix.
# ==============================================================================

# ------------------------------------------------------------------------------
# Daily 09:00 UTC throughput check — surface whether the loop is producing trades.
# Exits 1 if any symbol has <10 resolved trades in the last 7 days.
# Uncomment to enable.
# ------------------------------------------------------------------------------
# 0 9 * * * cd /path/to/RiseTraderMVP && /usr/bin/env python3 scripts/check_loop_throughput.py >> logs/throughput_$(date +\%Y\%m\%d).log 2>&1
