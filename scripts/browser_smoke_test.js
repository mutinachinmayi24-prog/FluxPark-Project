// Cross-engine smoke test: loads /signup in each of Chromium, Firefox, and
// WebKit (Safari's engine), checks the page renders without console errors,
// and confirms the service worker registers successfully.
//
// Real Safari isn't installable on Windows -- WebKit is its actual rendering
// engine, the closest meaningful proxy available without a Mac/iOS device.
//
// Usage: node scripts/browser_smoke_test.js <base_url>

const { chromium, firefox, webkit } = require("playwright");

const baseUrl = process.argv[2] || "http://127.0.0.1:8015";

async function testEngine(name, launcher) {
  const browser = await launcher.launch();
  const page = await browser.newPage();
  const errors = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(String(err)));

  let status = null;
  try {
    const response = await page.goto(`${baseUrl}/signup`, { waitUntil: "load", timeout: 15000 });
    status = response.status();
  } catch (e) {
    await browser.close();
    return { name, ok: false, reason: `navigation failed: ${e.message}` };
  }

  const title = await page.title();

  let swRegistered = false;
  let swReason = "";
  try {
    swRegistered = await page.evaluate(async () => {
      if (!("serviceWorker" in navigator)) return false;
      const reg = await navigator.serviceWorker.register("/service-worker.js");
      await navigator.serviceWorker.ready;
      return !!reg;
    });
  } catch (e) {
    swReason = e.message;
  }

  await browser.close();
  return {
    name,
    ok: status === 200 && errors.length === 0,
    httpStatus: status,
    title,
    consoleErrors: errors,
    serviceWorkerRegistered: swRegistered,
    serviceWorkerError: swReason,
  };
}

(async () => {
  const results = [];
  results.push(await testEngine("Chromium (Chrome/Edge engine)", chromium));
  results.push(await testEngine("Firefox (Gecko)", firefox));
  results.push(await testEngine("WebKit (Safari engine)", webkit));

  console.log(JSON.stringify(results, null, 2));
})();
