#!/usr/bin/env node

/**
 * Interactive Dashboard Testing with Puppeteer
 * Actually clicks through and verifies data is displayed
 */

const puppeteer = require('puppeteer');

const DASHBOARD_URL = 'http://localhost:3003';

async function testDashboard() {
  console.log('🚀 Starting Interactive Dashboard Test\n');

  const browser = await puppeteer.launch({
    headless: false,  // Show browser so we can see what's happening
    slowMo: 100,      // Slow down so we can see actions
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });

    // Collect errors
    const errors = [];
    page.on('console', msg => {
      if (msg.type() === 'error') {
        errors.push({ type: 'console', text: msg.text(), url: page.url() });
      }
    });
    page.on('pageerror', error => {
      errors.push({ type: 'page', text: error.message, url: page.url() });
    });

    console.log('📄 Testing Backtesting Runs Page');
    console.log('='.repeat(80));

    // Navigate to backtesting runs
    await page.goto(`${DASHBOARD_URL}/backtesting/runs`, {
      waitUntil: 'networkidle0',
      timeout: 15000
    });

    await new Promise(resolve => setTimeout(resolve, 3000));

    // Check for table/data
    const hasTable = await page.evaluate(() => {
      const tables = document.querySelectorAll('table, [role="table"]');
      const rows = document.querySelectorAll('tr, [role="row"]');
      return {
        tableCount: tables.length,
        rowCount: rows.length,
        bodyText: document.body.innerText.substring(0, 500)
      };
    });

    console.log(`\nPage Content Check:`);
    console.log(`- Tables found: ${hasTable.tableCount}`);
    console.log(`- Rows found: ${hasTable.rowCount}`);
    console.log(`- Body preview: ${hasTable.bodyText.substring(0, 200)}...`);

    // Look for backtest run data
    const backtestData = await page.evaluate(() => {
      const results = {
        runIds: [],
        statuses: [],
        metrics: [],
        charts: []
      };

      // Look for run IDs in the page
      const pageText = document.body.innerText;
      const runMatches = pageText.match(/run[_-]?\d+/gi) || [];
      results.runIds = [...new Set(runMatches)].slice(0, 5);

      // Look for status indicators
      const statusElements = document.querySelectorAll('[class*="status"], [class*="badge"]');
      results.statuses = Array.from(statusElements).map(el => el.innerText.trim()).filter(Boolean).slice(0, 5);

      // Look for metrics (numbers with decimals or percentages)
      const metricMatches = pageText.match(/\d+\.\d+%?/g) || [];
      results.metrics = [...new Set(metricMatches)].slice(0, 10);

      // Check for chart canvases
      const canvases = document.querySelectorAll('canvas');
      results.charts = Array.from(canvases).map(c => ({
        width: c.width,
        height: c.height
      }));

      return results;
    });

    console.log(`\nBacktest Data Found:`);
    console.log(`- Run IDs: ${backtestData.runIds.join(', ') || 'NONE FOUND'}`);
    console.log(`- Statuses: ${backtestData.statuses.join(', ') || 'NONE FOUND'}`);
    console.log(`- Metrics: ${backtestData.metrics.slice(0, 5).join(', ') || 'NONE FOUND'}`);
    console.log(`- Charts: ${backtestData.charts.length} canvas elements`);

    // Try to click on a run if available
    const clickableRuns = await page.$$('[role="row"], tr');
    if (clickableRuns.length > 1) {
      console.log(`\n🖱️  Attempting to click first backtest run...`);
      try {
        // Click the second row (first is usually header)
        await clickableRuns[1].click();
        await new Promise(resolve => setTimeout(resolve, 3000));

        // Check if detail view opened
        const detailView = await page.evaluate(() => {
          const bodyText = document.body.innerText;
          return {
            hasEquityCurve: bodyText.includes('Equity Curve') || bodyText.includes('equity'),
            hasTrades: bodyText.includes('Trades') || bodyText.includes('trade'),
            hasMetrics: bodyText.includes('Return') || bodyText.includes('Sharpe') || bodyText.includes('Drawdown'),
            canvasCount: document.querySelectorAll('canvas').length
          };
        });

        console.log(`\nDetail View Check:`);
        console.log(`- Has Equity Curve: ${detailView.hasEquityCurve ? '✅' : '❌'}`);
        console.log(`- Has Trades Data: ${detailView.hasTrades ? '✅' : '❌'}`);
        console.log(`- Has Metrics: ${detailView.hasMetrics ? '✅' : '❌'}`);
        console.log(`- Charts (canvases): ${detailView.canvasCount}`);

        // Take screenshot of detail view
        await page.screenshot({ path: 'backtest_detail_view.png', fullPage: true });
        console.log(`\n📸 Screenshot saved: backtest_detail_view.png`);

      } catch (clickError) {
        console.log(`❌ Failed to click run: ${clickError.message}`);
      }
    } else {
      console.log(`\n⚠️  No clickable runs found`);
    }

    // Check for equity curve specifically
    console.log(`\n📊 Checking for Equity Curve Chart...`);
    const equityCurveCheck = await page.evaluate(() => {
      const canvases = document.querySelectorAll('canvas');
      const hasEquityText = document.body.innerText.toLowerCase().includes('equity');
      const lightweightChartDivs = document.querySelectorAll('[class*="tv-lightweight-charts"]');

      return {
        canvasCount: canvases.length,
        hasEquityText,
        lightweightChartsFound: lightweightChartDivs.length,
        allText: Array.from(document.querySelectorAll('h1, h2, h3, h4')).map(h => h.innerText).join(' | ')
      };
    });

    console.log(`- Canvas elements: ${equityCurveCheck.canvasCount}`);
    console.log(`- "Equity" mentioned: ${equityCurveCheck.hasEquityText ? '✅' : '❌'}`);
    console.log(`- Lightweight Charts divs: ${equityCurveCheck.lightweightChartsFound}`);
    console.log(`- Page headings: ${equityCurveCheck.allText}`);

    // Final error summary
    console.log(`\n${'='.repeat(80)}`);
    console.log('📋 ERROR SUMMARY');
    console.log('='.repeat(80));

    if (errors.length === 0) {
      console.log('✅ NO ERRORS DETECTED');
    } else {
      console.log(`❌ ${errors.length} errors found:\n`);
      errors.forEach((err, i) => {
        console.log(`${i + 1}. [${err.type}] ${err.text}`);
      });
    }

    // Wait for user to inspect
    console.log(`\n⏸️  Browser will stay open for 10 seconds for inspection...`);
    await new Promise(resolve => setTimeout(resolve, 10000));

  } catch (error) {
    console.error('❌ Test failed:', error);
  } finally {
    await browser.close();
  }
}

testDashboard().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
