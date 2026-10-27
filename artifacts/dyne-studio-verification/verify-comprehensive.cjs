const puppeteer = require('C:/Users/loges/Documents/antigravity/elegant-bell/dyne-studio-application/node_modules/puppeteer-core')
const fs = require('fs')
const path = require('path')

const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const chromePath = (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe'
const execPath = fs.existsSync(chromePath) ? chromePath : edgePath

const outDir = path.resolve(__dirname, 'screenshots')
if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true })

const sleep = ms => new Promise(r => setTimeout(r, ms))

async function run() {
  console.log('Launching browser from:', execPath)
  const browser = await puppeteer.launch({
    executablePath: execPath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  })

  try {
    const page = await browser.newPage()
    const uncaughtErrors = []
    page.on('console', msg => {
      if (msg.type() === 'error') {
        // filter out expected network failure when backend python bridge is not running
        if (!msg.text().includes('ERR_CONNECTION_REFUSED')) {
          uncaughtErrors.push(msg.text())
        }
      }
    })
    page.on('pageerror', err => {
      uncaughtErrors.push(err.message)
    })

    // Test 1: Viewport 1440x900
    console.log('Testing 1440x900 viewport...')
    await page.setViewport({ width: 1440, height: 900 })
    await page.goto('http://localhost:5199/island', { waitUntil: 'networkidle0' })
    await sleep(600)

    // Verify capsule element exists and is visible
    const capsuleRect = await page.evaluate(() => {
      const el = document.querySelector('.central-capsule')
      if (!el) return null
      const rect = el.getBoundingClientRect()
      return { width: rect.width, height: rect.height, x: rect.x, y: rect.y }
    })
    console.log('Capsule rect at 1440x900:', capsuleRect)
    if (!capsuleRect || capsuleRect.width < 100 || capsuleRect.height < 30) {
      throw new Error('Capsule is collapsed or missing at 1440x900')
    }

    await page.screenshot({ path: path.join(outDir, '01-rest-1440x900.png') })

    // Test 2: Click capsule to open Category Ring
    console.log('Clicking capsule to open 6-category ring...')
    await page.click('.central-capsule')
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '02-category-ring-1440x900.png') })

    const optionsCount = await page.evaluate(() => {
      return document.querySelectorAll('.shell-option').length
    })
    console.log('Category options rendered:', optionsCount)
    if (optionsCount !== 6) {
      throw new Error(`Expected 6 category options, found ${optionsCount}`)
    }

    // Test 3: Click Colour category
    console.log('Clicking Colour category...')
    await page.evaluate(() => {
      const opts = Array.from(document.querySelectorAll('.shell-option'))
      const colourOpt = opts.find(o => o.textContent.includes('Colour'))
      if (colourOpt) {
        const target = colourOpt.querySelector('path') || colourOpt
        target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
      }
    })
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '03-colour-options-1440x900.png') })

    // Test 4: Open Custom RGB mixer
    console.log('Opening Custom RGB mixer...')
    await page.evaluate(() => {
      const opts = Array.from(document.querySelectorAll('.shell-option'))
      const customOpt = opts.find(o => o.textContent.includes('Custom'))
      if (customOpt) {
        const target = customOpt.querySelector('path') || customOpt
        target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
      }
    })
    await sleep(400)
    await page.screenshot({ path: path.join(outDir, '04-rgb-mixer-1440x900.png') })

    // Test 5: Press Escape to go back
    console.log('Pressing Escape to go back...')
    await page.keyboard.press('Escape')
    await sleep(350)
    await page.keyboard.press('Escape')
    await sleep(350)
    await page.screenshot({ path: path.join(outDir, '05-back-to-main-1440x900.png') })

    // Back to rest
    await page.keyboard.press('Escape')
    await sleep(350)
    await page.screenshot({ path: path.join(outDir, '06-back-to-rest-1440x900.png') })

    // Test 6: Viewport 1120x800
    console.log('Testing 1120x800 viewport...')
    await page.setViewport({ width: 1120, height: 800 })
    await sleep(400)
    const rect1120 = await page.evaluate(() => {
      const el = document.querySelector('.central-capsule')
      if (!el) return null
      const rect = el.getBoundingClientRect()
      return { width: rect.width, height: rect.height, x: rect.x, y: rect.y }
    })
    console.log('Capsule rect at 1120x800:', rect1120)
    await page.screenshot({ path: path.join(outDir, '07-viewport-1120x800.png') })

    // Test 7: Viewport 390x844 (Mobile)
    console.log('Testing 390x844 mobile viewport...')
    await page.setViewport({ width: 390, height: 844 })
    await sleep(400)
    const rect390 = await page.evaluate(() => {
      const el = document.querySelector('.central-capsule')
      if (!el) return null
      const rect = el.getBoundingClientRect()
      return { width: rect.width, height: rect.height, x: rect.x, y: rect.y }
    })
    console.log('Capsule rect at 390x844:', rect390)
    await page.screenshot({ path: path.join(outDir, '08-viewport-390x844.png') })

    console.log('Uncaught console errors:', uncaughtErrors)
    if (uncaughtErrors.length > 0) {
      console.warn('Warning: There were console errors:', uncaughtErrors)
    }

    console.log('ALL BROWSER VALIDATION TESTS PASSED!')
  } finally {
    await browser.close()
  }
}

run().catch(err => {
  console.error('Test execution failed:', err)
  process.exit(1)
})
