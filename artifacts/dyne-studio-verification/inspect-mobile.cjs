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
    await page.goto('http://127.0.0.1:5173/island', { waitUntil: 'networkidle0' })
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

    await page.evaluate(() => document.querySelector('.central-capsule').click());
    await new Promise(r => setTimeout(r, 400));

    const hits = await page.evaluate(() => {
      const opts = Array.from(document.querySelectorAll('.shell-option'));
      return opts.map(opt => {
        const text = opt.querySelector('text');
        const rect = text ? text.getBoundingClientRect() : null;
        if (!rect) return { label: opt.getAttribute('aria-label'), error: 'no text' };
        const cx = rect.left + rect.width / 2;
        const cy = rect.top + rect.height / 2;
        const hit = document.elementFromPoint(cx, cy);
        return {
          label: opt.getAttribute('aria-label'),
          cx, cy,
          hitTag: hit ? hit.tagName : null,
          hitClass: hit ? (typeof hit.className === 'string' ? hit.className : hit.className.baseVal) : null,
          matches: hit === text || opt.contains(hit)
        };
      });
    });
    console.log('Hits:\n', JSON.stringify(hits, null, 2));
  } finally {
    await browser.close()
  }
}

run()
