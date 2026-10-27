const puppeteer = require('C:/Users/loges/Documents/antigravity/elegant-bell/dyne-studio-application/node_modules/puppeteer-core')
const fs = require('fs')

const edgePath = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const chromePath = (process.env.LOCALAPPDATA || '') + '\\Google\\Chrome\\Application\\chrome.exe'
const execPath = fs.existsSync(chromePath) ? chromePath : edgePath

async function run() {
  const browser = await puppeteer.launch({
    executablePath: execPath,
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox']
  })

  try {
    const page = await browser.newPage()
    await page.setViewport({ width: 390, height: 844 })
    await page.goto('http://localhost:5199/island', { waitUntil: 'networkidle0' })
    await new Promise(r => setTimeout(r, 600))

    const details = await page.evaluate(() => {
      const windowShell = document.querySelector('.window-shell')
      const windowBody = document.querySelector('.window-body')
      const sidebar = document.querySelector('.window-sidebar')
      const main = document.querySelector('.window-content')
      const pageEl = document.querySelector('.dyne-island-page')
      const studio = document.querySelector('.studio')
      const stage = document.querySelector('.capsule-stage')
      const assembly = document.querySelector('.capsule-assembly')
      const capsule = document.querySelector('.central-capsule')

      function rect(el) {
        if (!el) return null
        const r = el.getBoundingClientRect()
        const cs = window.getComputedStyle(el)
        return {
          width: r.width,
          height: r.height,
          x: r.x,
          y: r.y,
          display: cs.display,
          overflow: cs.overflow,
          flexShrink: cs.flexShrink,
          minWidth: cs.minWidth
        }
      }

      return {
        windowShell: rect(windowShell),
        windowBody: rect(windowBody),
        sidebar: rect(sidebar),
        main: rect(main),
        pageEl: rect(pageEl),
        studio: rect(studio),
        stage: rect(stage),
        assembly: rect(assembly),
        capsule: rect(capsule)
      }
    })

    console.log('Mobile 390x844 layout details:\n', JSON.stringify(details, null, 2))
  } finally {
    await browser.close()
  }
}

run()
