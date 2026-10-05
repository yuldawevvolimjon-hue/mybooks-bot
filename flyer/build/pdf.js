const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({args:['--disable-gpu']});
  const p = await b.newPage({ viewport: { width: 794, height: 1123 }, deviceScaleFactor: 2 });
  await p.goto('file://' + require('path').resolve(__dirname, '../saydali-flyer.html'));
  await p.evaluate(() => document.fonts.ready);
  await p.emulateMedia({ media: 'print' });
  await p.pdf({ path: __dirname + '/../saydali-flyer.pdf', format: 'A4', printBackground: true, preferCSSPageSize: true });
  const s = await p.$$('.sheet');
  await s[0].screenshot({ path: __dirname + '/../side-1-restaurant.png' });
  await s[1].screenshot({ path: __dirname + '/../side-2-recipe.png' });
  await b.close();
})();
