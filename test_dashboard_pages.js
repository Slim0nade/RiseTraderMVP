#!/usr/bin/env node

/**
 * Dashboard Page Testing with Puppeteer
 * Tests all key pages for console errors and rendering issues
 */

const puppeteer = require('puppeteer');

const DASHBOARD_URL = 'http://localhost:3003';
const PAGES_TO_TEST = [
  { path: '/', name: 'Home' },
  { path: '/backtesting', name: 'Backtesting' },
  { path: '/backtesting/runs', name: 'Backtest Runs' },
  { path: '/performance', name: 'Performance' },
  { path: '/positions', name: 'Positions' },
  { path: '/settings', name: 'Settings' }
];

async function testDashboard() {
  console.log('🚀 Starting Dashboard Test with Puppeteer\n');

  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  });

  const results = [];

  try {
    const page = await browser.newPage();

    // Collect console messages
    const consoleMessages = [];
    page.on('console', msg => {
      const type = msg.type();
      const text = msg.text();
      if (type === 'error' || type === 'warning') {
        consoleMessages.push({ type, text, url: page.url() });
      }
    });

    // Collect page errors
    const pageErrors = [];
    page.on('pageerror', error => {
      pageErrors.push({ error: error.message, url: page.url() });
    });

    // Test each page
    for (const testPage of PAGES_TO_TEST) {
      const url = `${DASHBOARD_URL}${testPage.path}`;
      console.log(`📄 Testing: ${testPage.name} (${url})`);

      consoleMessages.length = 0;
      pageErrors.length = 0;

      try {
        await page.goto(url, {
          waitUntil: 'networkidle0',
          timeout: 10000
        });

        // Wait for React to render
        await new Promise(resolve => setTimeout(resolve, 2000));

        // Check for specific error indicators
        const errorMessages = await page.evaluate(() => {
          const errors = [];

          // Check for React error boundaries
          const errorBoundaries = document.querySelectorAll('[data-error-boundary], .error-boundary');
          if (errorBoundaries.length > 0) {
            errors.push('React Error Boundary detected');
          }

          // Check for "No data" or error messages
          const bodyText = document.body.innerText;
          if (bodyText.includes('Error:') || bodyText.includes('Failed to')) {
            errors.push('Error message found in page content');
          }

          return errors;
        });

        const result = {
          name: testPage.name,
          url,
          status: 'success',
          consoleErrors: consoleMessages.filter(m => m.type === 'error'),
          consoleWarnings: consoleMessages.filter(m => m.type === 'warning'),
          pageErrors: [...pageErrors],
          errorMessages
        };

        results.push(result);

        if (result.consoleErrors.length > 0 || result.pageErrors.length > 0) {
          console.log(`   ❌ ERRORS FOUND (${result.consoleErrors.length} console, ${result.pageErrors.length} page)`);
        } else if (result.consoleWarnings.length > 0) {
          console.log(`   ⚠️  Warnings: ${result.consoleWarnings.length}`);
        } else {
          console.log(`   ✅ PASSED`);
        }

      } catch (error) {
        console.log(`   ❌ FAILED: ${error.message}`);
        results.push({
          name: testPage.name,
          url,
          status: 'failed',
          error: error.message
        });
      }

      console.log('');
    }

  } finally {
    await browser.close();
  }

  // Print detailed results
  console.log('\n' + '='.repeat(80));
  console.log('📊 DETAILED TEST RESULTS');
  console.log('='.repeat(80) + '\n');

  for (const result of results) {
    console.log(`\n🔍 ${result.name} (${result.url})`);
    console.log('-'.repeat(80));

    if (result.status === 'failed') {
      console.log(`❌ FAILED: ${result.error}`);
      continue;
    }

    if (result.consoleErrors.length > 0) {
      console.log(`\n❌ Console Errors (${result.consoleErrors.length}):`);
      result.consoleErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.text}`);
      });
    }

    if (result.pageErrors.length > 0) {
      console.log(`\n❌ Page Errors (${result.pageErrors.length}):`);
      result.pageErrors.forEach((err, i) => {
        console.log(`  ${i + 1}. ${err.error}`);
      });
    }

    if (result.errorMessages && result.errorMessages.length > 0) {
      console.log(`\n⚠️  Error Indicators Found:`);
      result.errorMessages.forEach((msg, i) => {
        console.log(`  ${i + 1}. ${msg}`);
      });
    }

    if (result.consoleWarnings.length > 0) {
      console.log(`\n⚠️  Console Warnings (${result.consoleWarnings.length}):`);
      result.consoleWarnings.slice(0, 5).forEach((warn, i) => {
        console.log(`  ${i + 1}. ${warn.text}`);
      });
      if (result.consoleWarnings.length > 5) {
        console.log(`  ... and ${result.consoleWarnings.length - 5} more warnings`);
      }
    }

    if (result.consoleErrors.length === 0 &&
        result.pageErrors.length === 0 &&
        (!result.errorMessages || result.errorMessages.length === 0)) {
      console.log('✅ All checks passed!');
    }
  }

  // Summary
  const passed = results.filter(r =>
    r.status === 'success' &&
    r.consoleErrors.length === 0 &&
    r.pageErrors.length === 0
  ).length;
  const failed = results.filter(r =>
    r.status === 'failed' ||
    r.consoleErrors.length > 0 ||
    r.pageErrors.length > 0
  ).length;

  console.log('\n' + '='.repeat(80));
  console.log('📈 SUMMARY');
  console.log('='.repeat(80));
  console.log(`Total Pages Tested: ${results.length}`);
  console.log(`✅ Passed: ${passed}`);
  console.log(`❌ Failed: ${failed}`);
  console.log('='.repeat(80) + '\n');

  process.exit(failed > 0 ? 1 : 0);
}

testDashboard().catch(error => {
  console.error('Fatal error:', error);
  process.exit(1);
});
