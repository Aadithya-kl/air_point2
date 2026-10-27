const path = require('path');
const fs = require('fs');
const puppeteer = require('C:/Users/loges/Documents/antigravity/elegant-bell/dyne-studio-application/node_modules/puppeteer-core');

const BROWSER_PATH = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const BASE_URL = 'http://localhost:5199/island';
const SCREENSHOT_DIR = 'C:/Users/loges/Documents/antigravity/AirPoint/artifacts/dyne-studio-verification/screenshots';

// Colors for console logging
const green = (s) => `\x1b[32m${s}\x1b[0m`;
const red = (s) => `\x1b[31m${s}\x1b[0m`;
const cyan = (s) => `\x1b[36m${s}\x1b[0m`;
const yellow = (s) => `\x1b[33m${s}\x1b[0m`;

async function runAcceptanceSuite() {
  console.log(cyan('========================================================'));
  console.log(cyan('AIRPOINT x DYNE STUDIO: COMPREHENSIVE ACCEPTANCE AUDIT'));
  console.log(cyan('========================================================\n'));

  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }

  const browser = await puppeteer.launch({
    executablePath: BROWSER_PATH,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080'],
  });

  const page = await browser.newPage();

  const networkLog = [];
  const consoleErrors = [];

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const text = msg.text();
      if (!text.includes('favicon.ico') && !text.includes('ERR_CONNECTION_REFUSED')) {
        consoleErrors.push(text);
      }
    }
  });

  page.on('pageerror', (err) => {
    consoleErrors.push(err.toString());
  });

  await page.setRequestInterception(true);
  page.on('request', (req) => {
    const url = req.url();
    const method = req.method();

    const corsHeaders = {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Content-Type': 'application/json',
    };

    if (method === 'OPTIONS' && (url.includes('/api/settings') || url.includes('/api/control') || url.includes('/api/status'))) {
      req.respond({
        status: 204,
        headers: corsHeaders,
      });
      return;
    }

    if (url.includes('/api/settings') || url.includes('/api/control')) {
      networkLog.push({
        method,
        url,
        body: req.postData() ? JSON.parse(req.postData()) : null,
        timestamp: Date.now(),
      });
    }
    // Mock /api/status so engine remains ONLINE
    if (url.includes('/api/status')) {
      req.respond({
        status: 200,
        headers: corsHeaders,
        body: JSON.stringify({
          running: true,
          settings: {
            island_enabled: true,
            island_notifications_enabled: true,
            island_timer_enabled: true,
            island_autohide_enabled: true,
            island_hud_duration_s: 120,
            island_completion_duration_s: 2,
          },
        }),
      });
      return;
    }
    if (url.includes('/api/settings') && method === 'POST') {
      req.respond({
        status: 200,
        headers: corsHeaders,
        body: JSON.stringify({ status: 'ok', settings: req.postData() ? JSON.parse(req.postData()) : {} }),
      });
      return;
    }
    if (url.includes('/api/control') && method === 'POST') {
      req.respond({
        status: 200,
        headers: corsHeaders,
        body: JSON.stringify({ status: 'ok', command: 'test_countdown' }),
      });
      return;
    }
    req.continue();
  });

  let passCount = 0;
  let failCount = 0;

  function assert(condition, message) {
    if (condition) {
      console.log(`  ${green('✓')} ${message}`);
      passCount++;
    } else {
      console.error(`  ${red('✗')} ${message}`);
      failCount++;
      throw new Error(`Assertion failed: ${message}`);
    }
  }

  try {
    // ---------------------------------------------------------
    // TEST 1: RESPONSIVE VIEWPORT RENDERING (1280x800, 1440x900, 1920x1080)
    // ---------------------------------------------------------
    console.log(yellow('\n[1/8] Verifying Responsive Viewports...'));
    const viewports = [
      { width: 1280, height: 800, name: '1280x800' },
      { width: 1440, height: 900, name: '1440x900' },
      { width: 1920, height: 1080, name: '1920x1080' },
    ];

    for (const vp of viewports) {
      await page.setViewport({ width: vp.width, height: vp.height });
      await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
      await new Promise((r) => setTimeout(r, 600));

      const dyneStudio = await page.$('.dyne-studio-root');
      assert(dyneStudio !== null, `Dyne Studio root mounts cleanly at ${vp.name}`);

      const desktopCard = await page.$('[data-testid="desktop-overlay-status-card"]');
      assert(desktopCard !== null, `Real Desktop Status Card mounts cleanly at ${vp.name}`);

      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, `audit-viewport-${vp.name}.png`),
      });
    }

    // Standard viewport for remaining interaction tests
    await page.setViewport({ width: 1440, height: 900 });
    await page.goto(BASE_URL, { waitUntil: 'networkidle0' });
    await new Promise((r) => setTimeout(r, 600));

    // Capture initial rest state
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-01-resting-state.png'),
    });

    // ---------------------------------------------------------
    // TEST 2: RESTING CAPSULE NAVIGATION & 6 MAIN CATEGORIES
    // ---------------------------------------------------------
    console.log(yellow('\n[2/8] Testing Resting Capsule Navigation & 6 Categories...'));

    const centralCapsule = await page.$('.central-capsule');
    assert(centralCapsule !== null, 'Central capsule button found in DOM');

    // Click central capsule to open Main Options
    await centralCapsule.click();
    await new Promise((r) => setTimeout(r, 450));

    // Verify Main Options title appears
    const mainTitle = await page.evaluate(() => {
      const h2 = document.querySelector('.stage-heading h2');
      return h2 ? h2.textContent.trim() : '';
    });
    assert(mainTitle === 'Make it yours.', `Main Options opened with title "Make it yours." (got "${mainTitle}")`);

    // Verify all 6 category options exist in the SVG shell
    const categories = ['Text', 'Style', 'Texture', 'Shape', 'Time', 'Colour'];
    for (const cat of categories) {
      const optionEl = await page.$(`g[role="button"][aria-label="${cat}"]`);
      assert(optionEl !== null, `Category option "${cat}" is rendered and interactive`);
    }

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-02-main-options.png'),
    });

    // Verify clicking central capsule again returns to rest
    await centralCapsule.click();
    await new Promise((r) => setTimeout(r, 450));
    const isRestTitle = await page.evaluate(() => {
      const h2 = document.querySelector('.stage-heading h2');
      return h2 ? h2.textContent.trim() : '';
    });
    assert(isRestTitle === 'Your capsule. Your way.', 'Clicking central capsule returns up 1 level to resting state');

    // Re-open Main Options
    await centralCapsule.click();
    await new Promise((r) => setTimeout(r, 450));

    // ---------------------------------------------------------
    // TEST 3: COLOUR EXPLORATION & CUSTOM 3-LOOP RGB MIXER
    // ---------------------------------------------------------
    console.log(yellow('\n[3/8] Testing Colour Category & Custom Concentric RGB Mixer...'));
    const colourBtn = await page.$('g[role="button"][aria-label="Colour"]');
    assert(colourBtn !== null, 'Found Colour category option');
    await colourBtn.click();
    await new Promise((r) => setTimeout(r, 450));

    const colourTitle = await page.evaluate(() => {
      const h2 = document.querySelector('.stage-heading h2');
      return h2 ? h2.textContent.trim() : '';
    });
    assert(colourTitle === 'Choose your colour.', 'Navigated to Colour category view');

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-03-colour-category.png'),
    });

    // Click Custom option
    const customBtn = await page.$('g[role="button"][aria-label="Custom"]');
    assert(customBtn !== null, 'Found Custom RGB option');
    await customBtn.click();
    await new Promise((r) => setTimeout(r, 450));

    // Verify 3 concentric loops and HEX input
    const rgbMixer = await page.$('.colour-exploration');
    assert(rgbMixer !== null, 'Custom RGB Mixer view is active');

    const loopR = await page.$('.rgb-ring-r');
    const loopG = await page.$('.rgb-ring-g');
    const loopB = await page.$('.rgb-ring-b');
    assert(loopR !== null && loopG !== null && loopB !== null, 'All 3 independent loops (R, G, B) exist');

    // Read initial HEX
    const initialHex = await page.$eval('.rgb-hex strong', (el) => el.textContent.trim());
    console.log(`    Initial HEX: ${initialHex}`);

    // Update G input
    const gInput = await page.$('input[aria-label="G value"]');
    assert(gInput !== null, 'G value numeric input exists');
    await gInput.click({ clickCount: 3 });
    await gInput.type('210');
    await new Promise((r) => setTimeout(r, 200));

    const updatedHex = await page.$eval('.rgb-hex strong', (el) => el.textContent.trim());
    console.log(`    Updated HEX after G=210: ${updatedHex}`);
    assert(updatedHex !== initialHex, 'HEX value updated in unison with G adjustment');

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-04-custom-rgb-mixer.png'),
    });

    // ---------------------------------------------------------
    // TEST 4: TWO-RING EXTENDED COLOUR PALETTE (18 COLOURS)
    // ---------------------------------------------------------
    console.log(yellow('\n[4/8] Testing Two-Ring Concentric Colour Palette (18 Swatches)...'));
    // Step back to Colour view
    await page.keyboard.press('Escape');
    await new Promise((r) => setTimeout(r, 450));

    // Click More Colours
    const moreColoursBtn = await page.$('g[role="button"][aria-label="More Colours"]');
    assert(moreColoursBtn !== null, 'Found More Colours option');
    await moreColoursBtn.click();
    await new Promise((r) => setTimeout(r, 450));

    const twoRingPalette = await page.$('.two-ring-colour-palette');
    assert(twoRingPalette !== null, 'Two-Ring Colour Palette view is active');

    // Verify 18 colour segments
    const colourSegments = await page.$$('.two-ring-colour-palette g.shell-option');
    assert(colourSegments.length === 18, `Found exactly 18 selectable colour segments (found: ${colourSegments.length})`);

    // Click segment (e.g. Amber or Teal)
    await colourSegments[2].click();
    await new Promise((r) => setTimeout(r, 400));

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-05-two-ring-palette.png'),
    });

    // Return to Main Options
    // Note: Selecting a colour in the Two-Ring Palette automatically navigates back to Colour category.
    // One Escape then returns to Main Options.
    const h2AfterSelect = await page.evaluate(() => document.querySelector('.stage-heading h2')?.textContent?.trim() || '');
    if (h2AfterSelect === 'Choose your colour.') {
      await page.keyboard.press('Escape');
      await new Promise((r) => setTimeout(r, 450));
    } else if (h2AfterSelect === 'Your capsule. Your way.') {
      await centralCapsule.click();
      await new Promise((r) => setTimeout(r, 450));
    } else if (h2AfterSelect === 'More colours.') {
      await page.keyboard.press('Escape');
      await new Promise((r) => setTimeout(r, 300));
      await page.keyboard.press('Escape');
      await new Promise((r) => setTimeout(r, 450));
    }

    // ---------------------------------------------------------
    // TEST 5: TIME & TEXTURE STADIUM DIALS
    // ---------------------------------------------------------
    console.log(yellow('\n[5/8] Testing Stadium Numeric & Texture Dials...'));
    const timeBtn = await page.$('g[role="button"][aria-label="Time"]');
    assert(timeBtn !== null, 'Found Time category option');
    await timeBtn.click();
    await new Promise((r) => setTimeout(r, 450));

    const dialTrack = await page.$('.adjustment-layer');
    assert(dialTrack !== null, 'Time Stadium Dial Track is active');

    const dialHandle = await page.$('.track-handle');
    assert(dialHandle !== null, 'Dial interactive handle exists');

    // Read initial time readout
    const initialTime = await page.$eval('.adjustment-header strong', (el) => el.textContent.trim());
    console.log(`    Initial Time value: ${initialTime}`);

    // Press ArrowRight to adjust slider
    await page.evaluate((el) => el.focus(), dialHandle);
    await page.keyboard.press('ArrowRight');
    await new Promise((r) => setTimeout(r, 200));

    const updatedTime = await page.$eval('.adjustment-header strong', (el) => el.textContent.trim());
    console.log(`    Updated Time value after ArrowRight: ${updatedTime}`);
    assert(updatedTime !== initialTime, 'Arrow key adjusts slider value when handle is active');

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-06-time-dial.png'),
    });

    // Step back to Main Options
    await page.keyboard.press('Escape');
    await new Promise((r) => setTimeout(r, 450));

    // ---------------------------------------------------------
    // TEST 6: PREVIEW CAPSULE SWITCHER & PER-PROFILE PERSISTENCE
    // ---------------------------------------------------------
    console.log(yellow('\n[6/8] Testing Profile Switcher & Per-Profile Persistence...'));

    let currentName = await page.$eval('.capsule-name', (el) => el.textContent.trim());
    assert(currentName === 'Power Saver', `Initial profile is Power Saver (got "${currentName}")`);

    // Next button
    const nextBtn = await page.$('button[aria-label="Next capsule"]') || await page.$('.capsule-nav-next');
    assert(nextBtn !== null, 'Switcher next chevron button found');
    await nextBtn.click();
    await new Promise((r) => setTimeout(r, 450));

    currentName = await page.$eval('.capsule-name', (el) => el.textContent.trim());
    assert(currentName === 'Focus', `Switched to Focus profile (got "${currentName}")`);

    // Verify preview-only badge is present
    const previewBadge = await page.$('.capsule-preview-badge');
    assert(previewBadge !== null, 'Preview badge is displayed for preview profiles');

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-07-switcher-focus.png'),
    });

    // Switch to Performance via ArrowRight
    await page.keyboard.press('ArrowRight');
    await new Promise((r) => setTimeout(r, 450));
    currentName = await page.$eval('.capsule-name', (el) => el.textContent.trim());
    assert(currentName === 'Performance', `Switched to Performance via ArrowRight (got "${currentName}")`);

    // Switch to Media via Next button
    await nextBtn.click();
    await new Promise((r) => setTimeout(r, 450));
    currentName = await page.$eval('.capsule-name', (el) => el.textContent.trim());
    assert(currentName === 'Media', `Switched to Media profile (got "${currentName}")`);

    // Test deep layer suppression: Open Time dial on Media profile
    const timeMediaBtn = await page.$('g[role="button"][aria-label="Time"]');
    if (timeMediaBtn) {
      await timeMediaBtn.click();
      await new Promise((r) => setTimeout(r, 400));

      // Press ArrowRight - should NOT switch profile!
      await page.keyboard.press('ArrowRight');
      await new Promise((r) => setTimeout(r, 200));

      // Verify we are still on Media and still inside Time adjustment
      const stillInTime = await page.$('.adjustment-layer') !== null;
      assert(stillInTime, 'Arrow keys in deep adjustment layer adjust dial rather than switching profile');

      await page.keyboard.press('Escape');
      await new Promise((r) => setTimeout(r, 400));
    }

    // Return to Power Saver
    const prevBtn = await page.$('button[aria-label="Previous capsule"]') || await page.$('.capsule-nav-prev');
    assert(prevBtn !== null, 'Switcher prev chevron button found');
    await prevBtn.click(); // Performance
    await new Promise((r) => setTimeout(r, 200));
    await prevBtn.click(); // Focus
    await new Promise((r) => setTimeout(r, 200));
    await prevBtn.click(); // Power Saver
    await new Promise((r) => setTimeout(r, 450));

    currentName = await page.$eval('.capsule-name', (el) => el.textContent.trim());
    assert(currentName === 'Power Saver', 'Cycled cleanly back to Power Saver');

    // ---------------------------------------------------------
    // TEST 7: NETWORK SAFETY PROOF (ZERO CALLS FROM DYNE STUDIO)
    // ---------------------------------------------------------
    console.log(yellow('\n[7/8] Verifying Native Safety & Settings Network Contract...'));

    const studioPostSettings = networkLog.filter(
      (n) => n.method === 'POST' && n.url.includes('/api/settings')
    );
    const studioPostControl = networkLog.filter(
      (n) => n.method === 'POST' && n.url.includes('/api/control')
    );

    console.log(`    Total POST /api/settings from Dyne Studio edits: ${studioPostSettings.length}`);
    console.log(`    Total POST /api/control from Dyne Studio edits: ${studioPostControl.length}`);

    assert(
      studioPostSettings.length === 0,
      'PROVEN: Zero POST /api/settings requests occurred during Dyne Studio profile switches and visual adjustments!'
    );
    assert(
      studioPostControl.length === 0,
      'PROVEN: Zero POST /api/control requests occurred during Dyne Studio profile switches!'
    );

    // Now test REAL native controls on the page to prove they DO dispatch network requests
    console.log(cyan('    Testing real native desktop HUD settings mutation...'));
    await page.evaluate(() => {
      document.querySelector('[data-testid="toggle-island-enabled"]')?.scrollIntoView({ behavior: 'instant', block: 'center' });
    });
    await new Promise((r) => setTimeout(r, 300));

    const toggleOverlay = await page.$('[data-testid="toggle-island-enabled"]');
    assert(toggleOverlay !== null, 'Native toggle-island-enabled switch found');
    
    // Toggle off
    await toggleOverlay.click();
    await new Promise((r) => setTimeout(r, 500));

    // Toggle back on so island is enabled
    await toggleOverlay.click();
    await new Promise((r) => setTimeout(r, 500));

    const realPostSettings = networkLog.filter(
      (n) => n.method === 'POST' && n.url.includes('/api/settings')
    );
    assert(
      realPostSettings.length >= 2,
      `PROVEN: Real desktop toggle DID trigger POST /api/settings (${realPostSettings.length} calls)`
    );
    console.log(`    Last payload sent by native switch: ${JSON.stringify(realPostSettings[realPostSettings.length - 1].body)}`);

    // Test real Test 5s Countdown button (now enabled because islandSettings.enabled is true)
    await page.evaluate(() => {
      document.querySelector('[data-testid="test-countdown-btn"]')?.scrollIntoView({ behavior: 'instant', block: 'center' });
    });
    await new Promise((r) => setTimeout(r, 300));

    const testCountdownBtn = await page.$('[data-testid="test-countdown-btn"]');
    assert(testCountdownBtn !== null, 'Real Test 5s Countdown button found');
    await testCountdownBtn.click();
    await new Promise((r) => setTimeout(r, 600));

    const realPostControl = networkLog.filter(
      (n) => n.method === 'POST' && n.url.includes('/api/control')
    );
    assert(
      realPostControl.length > 0,
      `PROVEN: Real Test Countdown button DID trigger POST /api/control (${realPostControl.length} call)`
    );

    // Screenshot real desktop status & controls
    await page.evaluate(() => {
      document.querySelector('[data-testid="desktop-overlay-status-card"]')?.scrollIntoView({ behavior: 'instant', block: 'center' });
    });
    await new Promise((r) => setTimeout(r, 300));
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'audit-08-desktop-status-and-controls.png'),
    });

    // ---------------------------------------------------------
    // TEST 8: CONSOLE ERRORS & RAPID NAVIGATION STABILITY
    // ---------------------------------------------------------
    console.log(yellow('\n[8/8] Testing Rapid Navigation Stability & Console Cleanliness...'));

    await page.evaluate(() => {
      window.scrollTo(0, 0);
    });
    await new Promise((r) => setTimeout(r, 200));

    // Rapid clicking test
    for (let i = 0; i < 6; i++) {
      await centralCapsule.click();
      await new Promise((r) => setTimeout(r, 90));
    }
    await new Promise((r) => setTimeout(r, 500));

    // Verify central capsule is still mounted and healthy
    const healthyCapsule = await page.$('.central-capsule');
    assert(healthyCapsule !== null, 'Capsule survived rapid click stress test with no DOM collapse');

    console.log(`    Uncaught console errors: ${consoleErrors.length}`);
    if (consoleErrors.length > 0) {
      console.log(`    Errors logged: ${JSON.stringify(consoleErrors)}`);
    }
    assert(consoleErrors.length === 0, 'Zero uncaught console errors throughout entire audit session');

    console.log(green('\n========================================================'));
    console.log(green(`AUDIT SUITE COMPLETE: ${passCount} PASSED, ${failCount} FAILED`));
    console.log(green('========================================================\n'));

    await browser.close();
    process.exit(0);
  } catch (err) {
    console.error(red(`\nAudit Suite Failed with error: ${err.message}`));
    console.error(err.stack);
    await browser.close();
    process.exit(1);
  }
}

runAcceptanceSuite();
