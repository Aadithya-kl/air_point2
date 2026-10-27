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
      const els = Array.from(document.querySelectorAll('*'))
      return els
        .filter(el => {
          const r = el.getBoundingClientRect()
          return r.y < 500 && r.height > 50 && r.width > 200
        })
        .map(el => ({
          tag: el.tagName,
          class: el.className,
          y: el.getBoundingClientRect().y,
          h: el.getBoundingClientRect().height
        }))
    })

    console.log('Elements above:\n', JSON.stringify(details, null, 2))
  } finally {
    await browser.close()
  }
}

run()
