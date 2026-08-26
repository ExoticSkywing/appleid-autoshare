const { webkit, firefox } = require('playwright');

const base = 'http://127.0.0.1:44120/';
const cases = [
  { name: 'webkit-393', engine: webkit, viewport: { width: 393, height: 852 } },
  { name: 'webkit-320', engine: webkit, viewport: { width: 320, height: 720 } },
  { name: 'firefox-393', engine: firefox, viewport: { width: 393, height: 852 } },
  { name: 'firefox-1440', engine: firefox, viewport: { width: 1440, height: 1000 } },
];

(async () => {
  const results = [];
  for (const test of cases) {
    const browser = await test.engine.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: test.viewport });
      await page.goto(base, { waitUntil: 'domcontentloaded' });
      await page.evaluate(() => {
        document.body.dataset.phase = 'verify';
        document.querySelector('#intentPanel')?.classList.remove('hidden');
      });
      await page.waitForTimeout(80);
      const result = await page.evaluate(() => {
        const panel = document.querySelector('#intentPanel');
        const options = [...document.querySelectorAll('[data-intent]')];
        const style = (el) => getComputedStyle(el);
        const rect = (el) => el.getBoundingClientRect().toJSON();
        return {
          panelRect: rect(panel),
          title: document.querySelector('#intentTitle')?.textContent.trim(),
          kicker: document.querySelector('.intent-kicker')?.textContent.trim(),
          titleColor: style(document.querySelector('#intentTitle')).color,
          kickerColor: style(document.querySelector('.intent-kicker')).color,
          panelBorderTop: style(panel).borderTop,
          columns: style(document.querySelector('.intent-options')).gridTemplateColumns,
          options: options.map((el) => ({
            label: el.getAttribute('aria-label'),
            text: el.textContent.replace(/\s+/g, ' ').trim(),
            rect: rect(el),
            bg: style(el).backgroundColor,
            border: style(el).border,
            cursor: style(el).cursor,
            strong: style(el.querySelector('strong')).color,
            small: style(el.querySelector('small')).color,
            strongText: el.querySelector('strong')?.textContent.trim(),
            smallText: el.querySelector('small')?.textContent.trim(),
            strongRect: rect(el.querySelector('strong')),
            smallRect: rect(el.querySelector('small')),
            imageRect: el.querySelector('img') ? rect(el.querySelector('img')) : null,
            iconRect: el.querySelector('svg') ? rect(el.querySelector('svg')) : null,
            arrowRect: rect(el.querySelector('.intent-arrow')),
          })),
          overflow: Math.max(0, document.documentElement.scrollWidth - innerWidth),
        };
      });
      await page.screenshot({ path: `artifacts/qa/intent-final-${test.name}.png`, fullPage: false });
      results.push({ name: test.name, result });
    } finally {
      await browser.close();
    }
  }
  console.log(JSON.stringify(results, null, 2));
  if (results.some(({ result }) => result.overflow > 0 || result.options.length !== 2 || result.columns.split(' ').length !== 2 || result.options.some((option) => option.rect.width < 44 || option.rect.height < 64 || option.cursor !== 'pointer' || option.strongRect.height > 24 || option.smallRect.height > 20 || !option.strongText || !option.smallText))) process.exit(1);
})().catch((error) => { console.error(error); process.exit(1); });
