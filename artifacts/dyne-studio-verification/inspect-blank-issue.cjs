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
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900']
  })

  try {
    const page = await browser.newPage()
    await page.setViewport({ width: 1440, height: 900 })

    const logs = []
    page.on('console', msg => {
      logs.push(`[${msg.type()}] ${msg.text()}`)
      console.log(`[Browser Console: ${msg.type()}]`, msg.text())
    })
    page.on('pageerror', err => {
      console.error('[Browser PageError]', err.message)
    })

    console.log('Navigating to http://localhost:5199/island...')
    await page.goto('http://localhost:5199/island', { waitUntil: 'networkidle0' })
    await sleep(1000)

    // Capture screenshot of what's currently rendered
    await page.screenshot({ path: path.join(outDir, 'diagnostic-initial-island.png'), fullPage: false })
    console.log('Saved diagnostic-initial-island.png')

    // Inspect DOM elements
    const inspection = await page.evaluate(() => {
      const pageEl = document.querySelector('.dyne-island-page')
      const studioRoot = document.querySelector('.dyne-studio-root')
      const capsule = document.querySelector('.central-capsule')
      const capsuleStage = document.querySelector('.capsule-stage')
      const assembly = document.querySelector('.capsule-assembly')
      const mainContent = document.querySelector('.window-content')

      function getInfo(el) {
        if (!el) return null
        const rect = el.getBoundingClientRect()
        const cs = window.getComputedStyle(el)
        return {
          tagName: el.tagName,
          className: el.className,
          rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
          display: cs.display,
          visibility: cs.visibility,
          opacity: cs.opacity,
          zIndex: cs.zIndex,
          color: cs.color,
          background: cs.background,
          innerHTMLSnippet: el.innerHTML ? el.innerHTML.slice(0, 300) : ''
        }
      }

      return {
        windowContent: getInfo(mainContent),
        pageEl: getInfo(pageEl),
        studioRoot: getInfo(studioRoot),
        capsuleStage: getInfo(capsuleStage),
        assembly: getInfo(assembly),
        capsule: getInfo(capsule),
        bodyHtmlSnippet: document.body.innerHTML.slice(0, 800)
      }
    })

    console.log('DOM Inspection Result:\n', JSON.stringify(inspection, null, 2))

  } catch (err) {
    console.error('Error in run:', err)
  } finally {
    await browser.close()
  }
}

run()
