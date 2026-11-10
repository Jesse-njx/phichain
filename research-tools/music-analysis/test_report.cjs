/* Optional headless UI smoke test. Never opens a user-facing browser window. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');

(async () => {
  if (!process.argv[2]) throw new Error('Pass the generated index.html path');
  const browser = await chromium.launch({headless: true, args: ['--mute-audio'],
    ...(process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ? {executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE} : {})});
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'note-report-test-'));
  try {
    const page = await browser.newPage({viewport: {width: 1360, height: 1000}, acceptDownloads: true});
    const errors = [], remoteRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {if (/^https?:/.test(request.url())) remoteRequests.push(request.url());});
    await page.goto(pathToFileURL(path.resolve(process.argv[2])).href);
    await page.waitForFunction(() => document.querySelector('#audio').readyState >= 1);
    assert.match(await page.locator('#summary').innerText(), /selected/);
    assert.ok(await page.locator('#notes input[type=checkbox]').count() > 0);
    await page.locator('#window').selectOption('0');
    await page.locator('#filter').selectOption('all');
    const first = page.locator('#notes input[type=checkbox]').first();
    const original = await first.isChecked();
    await first.setChecked(!original);
    const strength = page.locator('#notes input[type=number]').first();
    await strength.fill('23');
    await strength.dispatchEvent('change');
    assert.match(await page.locator('#dirty').innerText(), /changed/);
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#exportReview').click()]);
    const destination = path.join(temp, 'review.json');
    await download.saveAs(destination);
    const review = JSON.parse(fs.readFileSync(destination, 'utf8'));
    assert.ok(review.source_sha256 && review.analysis_id);
    assert.ok(review.decisions.some(n => n.selected === !original && n.intensity === 23));
    await page.locator('#audioMode').selectOption('with-hits.wav');
    await page.waitForFunction(() => document.querySelector('#audio').readyState >= 1);
    await page.locator('#speed').selectOption('0.75');
    assert.equal(await page.locator('#audio').evaluate(a => a.playbackRate), 0.75);
    await page.locator('#overview').focus();
    await page.keyboard.press('ArrowRight');
    assert.ok(await page.locator('#audio').evaluate(a => a.currentTime) >= 4.9);
    await page.setViewportSize({width: 390, height: 844});
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Mobile document overflows');
    assert.deepEqual(errors, []);
    assert.deepEqual(remoteRequests, []);
    console.log(JSON.stringify({passed: true, checks: ['render', 'selection', 'intensity', 'review download', 'audio switch', 'speed', 'keyboard seek', 'mobile width', 'no external requests', 'no script errors']}));
  } finally {
    await browser.close();
    fs.rmSync(temp, {recursive: true, force: true});
  }
})().catch(error => {console.error(error); process.exitCode = 1;});
