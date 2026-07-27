const puppeteerPath = "node_modules/puppeteer";
const fs = require("fs");
async function main() {
  let puppeteer;
  try { puppeteer = require("puppeteer"); } catch (e) {
    try { puppeteer = require("puppeteer-core"); } catch (e2) {
      console.log("no puppeteer");
      // use edge via playwright?
      return;
    }
  }
  const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage();
  const logs = [];
  page.on("console", (m) => logs.push("CONSOLE " + m.type() + " " + m.text()));
  page.on("pageerror", (e) => logs.push("PAGEERROR " + e.message));
  page.on("requestfailed", (r) => logs.push("REQFAIL " + r.url() + " " + (r.failure() && r.failure().errorText)));
  await page.goto("http://127.0.0.1:8900/", { waitUntil: "networkidle0", timeout: 60000 });
  await page.waitForTimeout(2000);
  const info = await page.evaluate(() => {
    return {
      hasVue: typeof window.Vue !== "undefined",
      hasVueRouter: typeof window.VueRouter !== "undefined",
      hasApp: !!document.querySelector("#app"),
      appHTML: (document.querySelector("#app") || {}).innerHTML?.slice(0, 500),
      routerViewChildren: document.querySelector(".app-container")?.innerHTML?.slice(0, 300),
      bodyTheme: document.body.getAttribute("data-theme"),
      navText: Array.from(document.querySelectorAll(".nav-pill, .nav-tab")).map(el => el.textContent),
      errors: window.__errs || null,
    };
  });
  console.log(JSON.stringify(info, null, 2));
  console.log(logs.join("\n"));
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
