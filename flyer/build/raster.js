const { chromium } = require('playwright');
(async () => {
  const b = await chromium.launch({args:['--disable-gpu']});
  const p = await b.newPage({ viewport: { width: 840, height: 860 }, deviceScaleFactor: 2.5 });
  await p.setContent(`<html><body style="margin:0;background:transparent"><img src="file://${__dirname}/plov.svg" width="840" height="860"></body></html>`);
  await p.goto('file://' + __dirname + '/t.html');
  await p.screenshot({ path: __dirname + '/plov.png', omitBackground: true, clip:{x:0,y:0,width:840,height:860} });
  await b.close();
})();
