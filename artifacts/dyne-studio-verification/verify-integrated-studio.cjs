const puppeteer = require('C:/Users/loges/Documents/antigravity/elegant-bell/dyne-studio-application/node_modules/puppeteer-core')
const fs = require('fs')
const path = require('path')

const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const chromePath = (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe'
const execPath = fs.existsSync(chromePath) ? chromePath : edgePath

const outDir = path.resolve(__dirname, 'screenshots')
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function clickOption(opt) {
  await opt.evaluate(el => {
    const target = el.querySelector('path') || el
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
  })
}

async function run() {
  console.log('Launching browser from:', execPath)
  const browser = await puppeteer.launch({
    executablePath: execPath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  })

  try {
    const page = await browser.newPage()
    await page.setViewport({ width: 1440, height: 900 })

    const errors = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        console.error('[Browser Error]', msg.text())
        errors.push(msg.text())
      }
    })
    page.on('pageerror', err => {
      console.error('[Page Error]', err.message)
      errors.push(err.message)
    })

    console.log('Navigating to http://localhost:5199/island...')
    await page.goto('http://localhost:5199/island', { waitUntil: 'networkidle0' })
    await sleep(600)

    // 1. Resting capsule state
    console.log('1. Capturing Resting Capsule State on /island...')
    await page.screenshot({ path: path.join(outDir, '01-integrated-island-rest.png'), fullPage: false })

    // 2. Click central capsule to open Main options
    console.log('2. Opening Main options...')
    await page.click('.central-capsule')
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '02-integrated-main-options.png'), fullPage: false })

    // 3. Click Colour to open Colour category
    console.log('3. Opening Colour category...')
    const options = await page.$$('.shell-option')
    for (const opt of options) {
      const text = await opt.evaluate(el => el.textContent)
      if (text.includes('Colour')) {
        await clickOption(opt)
        break
      }
    }
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '03-integrated-colour-category.png'), fullPage: false })

    // 4. Click Custom to open Custom RGB mixer
    console.log('4. Opening Custom RGB mixer...')
    const colOptions = await page.$$('.shell-option')
    for (const opt of colOptions) {
      const text = await opt.evaluate(el => el.textContent)
      if (text.includes('Custom')) {
        await clickOption(opt)
        break
      }
    }
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '04-integrated-custom-rgb-mixer.png'), fullPage: false })

    // 5. Press Escape to go back to Colour category, then open More Colours
    console.log('5. Opening More Colours palette...')
    await page.keyboard.press('Escape')
    await sleep(350)
    const colOptions2 = await page.$$('.shell-option')
    for (const opt of colOptions2) {
      const text = await opt.evaluate(el => el.textContent)
      if (text.includes('More Colours') || text.includes('More')) {
        await clickOption(opt)
        break
      }
    }
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '05-integrated-two-ring-palette.png'), fullPage: false })

    // 6. Navigate back to Main, then open Time adjustment track
    console.log('6. Opening Time dial track...')
    await page.keyboard.press('Escape')
    await sleep(300)
    await page.keyboard.press('Escape')
    await sleep(300)
    const mainOpts2 = await page.$$('.shell-option')
    for (const opt of mainOpts2) {
      const text = await opt.evaluate(el => el.textContent)
      if (text.includes('Time')) {
        await clickOption(opt)
        break
      }
    }
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '06-integrated-time-dial.png'), fullPage: false })

    // 7. Go back to Main, test Capsule Switcher (Focus, Performance, Media)
    console.log('7. Testing Capsule Switcher...')
    await page.keyboard.press('Escape')
    await sleep(350)
    // Click next capsule arrow
    await page.click('.capsule-nav-next')
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '07-integrated-switcher-focus.png'), fullPage: false })

    await page.click('.capsule-nav-next')
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '07-integrated-switcher-performance.png'), fullPage: false })

    // 8. Capture Real Desktop Overlay status & controls section
    console.log('8. Capturing Desktop status & controls section...')
    const statusSection = await page.$('.grid.grid-cols-1.lg\\:grid-cols-3')
    if (statusSection) {
      await statusSection.screenshot({ path: path.join(outDir, '08-integrated-desktop-status-and-controls.png') })
    }

    // 9. Viewport responsive check: 1280x800
    console.log('9. Checking 1280x800 viewport...')
    await page.setViewport({ width: 1280, height: 800 })
    await sleep(300)
    await page.screenshot({ path: path.join(outDir, '09-integrated-viewport-1280x800.png'), fullPage: false })

    // 10. Viewport responsive check: 1920x1080
    console.log('10. Checking 1920x1080 viewport...')
    await page.setViewport({ width: 1920, height: 1080 })
    await sleep(300)
    await page.screenshot({ path: path.join(outDir, '10-integrated-viewport-1920x1080.png'), fullPage: false })

    console.log('All verification screenshots captured successfully!')
    console.log('Recorded browser errors count:', errors.length)
  } finally {
    await browser.close()
  }
}

run().catch(err => {
  console.error('Verification script failed:', err)
  process.exit(1)
})
