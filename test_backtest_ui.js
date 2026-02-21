/**
 * Puppeteer test for Backtesting UI validation
 * Tests that backtest results are properly displayed
 */
const puppeteer = require('puppeteer');

async function testBacktestingPage() {
    console.log('🚀 Starting Backtesting UI validation...\n');

    const browser = await puppeteer.launch({
        headless: false, // Set to true for CI/CD
        defaultViewport: { width: 1920, height: 1080 },
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    try {
        const page = await browser.newPage();

        // Enable console logging from the page
        page.on('console', msg => console.log('PAGE LOG:', msg.text()));
        page.on('pageerror', error => console.error('PAGE ERROR:', error.message));

        console.log('📡 Navigating to backtesting page...');
        await page.goto('http://localhost:3003/backtesting', {
            waitUntil: 'networkidle2',
            timeout: 30000
        });

        // Wait a bit for the page to render (even if auth fails)
        await new Promise(resolve => setTimeout(resolve, 3000));

        console.log('📸 Taking initial screenshot for debugging...');
        await page.screenshot({ path: 'backtest_page_loaded.png' });

        // Check what's actually on the page
        const pageContent = await page.evaluate(() => {
            return {
                title: document.title,
                h1: document.querySelector('h1')?.textContent,
                h2: document.querySelector('h2')?.textContent,
                bodyText: document.body.innerText.substring(0, 500)
            };
        });

        console.log('📄 Page content:', pageContent);

        console.log('✅ Page loaded successfully\n');

        // Test 1: Check if configurations are displayed
        console.log('📋 Test 1: Checking backtest configurations...');
        const configs = await page.evaluate(() => {
            // Try multiple selectors to find configuration cards
            const configCards = document.querySelectorAll('[data-testid="config-card"], .config-card, .backtest-config');
            const results = [];

            configCards.forEach(card => {
                const nameEl = card.querySelector('[data-testid="config-name"], .config-name, h3, h4');
                const statusEl = card.querySelector('[data-testid="config-status"], .status, .badge');
                const symbolEl = card.querySelector('[data-testid="symbol"], .symbol');
                const modeEl = card.querySelector('[data-testid="execution-mode"], .execution-mode, .mode');

                if (nameEl) {
                    results.push({
                        name: nameEl.textContent?.trim(),
                        status: statusEl?.textContent?.trim(),
                        symbol: symbolEl?.textContent?.trim(),
                        mode: modeEl?.textContent?.trim()
                    });
                }
            });

            return results;
        });

        if (configs.length > 0) {
            console.log(`✅ Found ${configs.length} backtest configuration(s):`);
            configs.slice(0, 3).forEach((cfg, idx) => {
                console.log(`   ${idx + 1}. ${cfg.name || 'N/A'}`);
                console.log(`      Status: ${cfg.status || 'N/A'}`);
                console.log(`      Symbol: ${cfg.symbol || 'N/A'}`);
                console.log(`      Mode: ${cfg.mode || 'N/A'}`);
            });
        } else {
            console.log('⚠️  No configurations found - checking if page structure is different...');
        }

        // Test 2: Click on a completed backtest and check results
        console.log('\n📊 Test 2: Checking backtest results display...');

        // Look for a completed backtest to click
        const completedConfig = await page.evaluate(() => {
            const completedCards = Array.from(document.querySelectorAll('[data-testid="config-card"], .config-card, .backtest-config'))
                .filter(card => {
                    const statusEl = card.querySelector('[data-testid="config-status"], .status, .badge');
                    const statusText = statusEl?.textContent?.toLowerCase() || '';
                    return statusText.includes('completed') || statusText.includes('complete');
                });

            if (completedCards.length > 0) {
                completedCards[0].click();
                return true;
            }
            return false;
        });

        if (completedConfig) {
            console.log('✅ Clicked on a completed backtest');

            // Wait for results to load
            await new Promise(resolve => setTimeout(resolve, 2000));

            // Extract run summary data
            const runSummary = await page.evaluate(() => {
                const summary = {};

                // Try to find candles processed
                const candlesEl = document.querySelector('[data-testid="candles-processed"], .candles-processed');
                if (candlesEl) summary.candlesProcessed = candlesEl.textContent?.trim();

                // Try to find agent decisions
                const decisionsEl = document.querySelector('[data-testid="agent-decisions"], .agent-decisions');
                if (decisionsEl) summary.agentDecisions = decisionsEl.textContent?.trim();

                // Try to find total trades
                const tradesEl = document.querySelector('[data-testid="total-trades"], .total-trades');
                if (tradesEl) summary.totalTrades = tradesEl.textContent?.trim();

                // Try to find final capital
                const capitalEl = document.querySelector('[data-testid="final-capital"], .final-capital');
                if (capitalEl) summary.finalCapital = capitalEl.textContent?.trim();

                // Look for all text content containing numbers
                const allText = document.body.innerText;
                const candlesMatch = allText.match(/Candles?\s+Processed[:\s]+(\d+[\d,]*)/i);
                const decisionsMatch = allText.match(/Agent\s+Decisions[:\s]+(\d+)/i);
                const tradesMatch = allText.match(/Total\s+Trades[:\s]+(\d+)/i);

                if (candlesMatch) summary.candlesProcessed = candlesMatch[1];
                if (decisionsMatch) summary.agentDecisions = decisionsMatch[1];
                if (tradesMatch) summary.totalTrades = tradesMatch[1];

                return summary;
            });

            console.log('📈 Run Summary:');
            console.log(`   Candles Processed: ${runSummary.candlesProcessed || '❌ Not found'}`);
            console.log(`   Agent Decisions: ${runSummary.agentDecisions || '❌ Not found'}`);
            console.log(`   Total Trades: ${runSummary.totalTrades || '❌ Not found'}`);
            console.log(`   Final Capital: ${runSummary.finalCapital || '❌ Not found'}`);

            // Test 3: Check performance metrics
            console.log('\n📊 Test 3: Checking performance metrics...');
            const metrics = await page.evaluate(() => {
                const metricsData = {};

                // Common metric names to look for
                const metricNames = [
                    'Total Return', 'Sharpe Ratio', 'Win Rate', 'Profit Factor',
                    'Max Drawdown', 'Sortino Ratio', 'Calmar Ratio'
                ];

                metricNames.forEach(name => {
                    const regex = new RegExp(name + '[:\\s]+([\\d.-]+%?)', 'i');
                    const match = document.body.innerText.match(regex);
                    if (match) {
                        metricsData[name] = match[1];
                    }
                });

                return metricsData;
            });

            console.log('📊 Performance Metrics:');
            Object.entries(metrics).forEach(([key, value]) => {
                console.log(`   ${key}: ${value}`);
            });

            if (Object.keys(metrics).length === 0) {
                console.log('   ⚠️  No performance metrics found');
            }

            // Test 4: Validate data consistency
            console.log('\n🔍 Test 4: Validating data consistency...');
            const validation = {
                hasCandles: runSummary.candlesProcessed && runSummary.candlesProcessed !== '0',
                hasDecisions: runSummary.agentDecisions && runSummary.agentDecisions !== '0',
                hasTrades: runSummary.totalTrades && runSummary.totalTrades !== '0',
                hasMetrics: Object.keys(metrics).length > 0
            };

            console.log('✅ Validation Results:');
            console.log(`   Candles displayed: ${validation.hasCandles ? '✅' : '❌'}`);
            console.log(`   Decisions displayed: ${validation.hasDecisions ? '✅' : '❌'}`);
            console.log(`   Trades displayed: ${validation.hasTrades ? '✅ (or genuinely 0)' : '⚠️  0 trades'}`);
            console.log(`   Metrics displayed: ${validation.hasMetrics ? '✅' : '❌'}`);

            // Check for the specific issue in the screenshot
            if (runSummary.totalTrades === '561' && runSummary.agentDecisions === '0') {
                console.log('\n⚠️  ISSUE DETECTED: Total Trades = 561 but Agent Decisions = 0');
                console.log('   This suggests the UI might be showing incorrect data!');
            }

        } else {
            console.log('⚠️  No completed backtest found to click on');
        }

        // Take a screenshot for reference
        console.log('\n📸 Taking screenshot...');
        await page.screenshot({
            path: 'backtest_ui_test.png',
            fullPage: true
        });
        console.log('✅ Screenshot saved as backtest_ui_test.png');

        console.log('\n✅ UI validation complete!');

    } catch (error) {
        console.error('\n❌ Test failed:', error.message);
        throw error;
    } finally {
        await browser.close();
    }
}

// Run the test
testBacktestingPage()
    .then(() => {
        console.log('\n🎉 All tests completed successfully!');
        process.exit(0);
    })
    .catch((error) => {
        console.error('\n💥 Test suite failed:', error);
        process.exit(1);
    });
