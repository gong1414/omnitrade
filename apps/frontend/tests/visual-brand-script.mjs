#!/usr/bin/env node
/**
 * One-off Playwright script — no webServer, talks straight to the live
 * container on :3000. Runs with `node tests/visual-brand-script.mjs`.
 */
import { chromium } from "@playwright/test";

const BASE = "http://localhost:3000/dashboard";
const OUT = "/Users/daoyu/Desktop";

const scenarios = [
  { name: "zh-light", locale: "zh", theme: "light" },
  { name: "en-light", locale: "en", theme: "light" },
  { name: "zh-dark", locale: "zh", theme: "dark" },
  { name: "en-dark", locale: "en", theme: "dark" },
];

async function settle(page) {
  try {
    await page.waitForLoadState("networkidle", { timeout: 5000 });
  } catch {}
  await page.waitForTimeout(400);
}

(async () => {
  const browser = await chromium.launch();
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1050 },
  });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(`console.error: ${msg.text()}`);
  });

  for (const s of scenarios) {
    // Priming visit so we can write to localStorage on the right origin.
    await page.goto(BASE);
    await page.evaluate(
      ({ locale, theme }) => {
        window.localStorage.setItem("omnitrade.locale", locale);
        window.localStorage.setItem("theme", theme);
      },
      s,
    );
    await page.reload();
    await settle(page);

    const feedVisible = await page.locator("[data-testid='reasoning-feed']").isVisible();
    if (!feedVisible) {
      console.log(`FAIL ${s.name}: reasoning-feed not visible`);
      continue;
    }

    const file = `${OUT}/omnitrade-brand-${s.name}.png`;
    await page.screenshot({ path: file, fullPage: true });
    console.log(`OK ${s.name} -> ${file}`);
  }

  // Round-trip locale toggle test
  await page.goto(BASE);
  await page.evaluate(() => window.localStorage.removeItem("omnitrade.locale"));
  await page.reload();
  await settle(page);
  const accountCard = page.locator("[data-testid='account-card']");
  const initialText = await accountCard.innerText();
  const startsWithZh = initialText.includes("金库");
  console.log(`default locale ${startsWithZh ? "is zh (金库 present)" : "is NOT zh"}`);

  await page.getByRole("button", { name: "EN" }).click();
  await settle(page);
  const enText = await accountCard.innerText();
  console.log(`EN toggle → account card has "Vault": ${enText.includes("Vault")}`);

  if (errors.length) {
    console.log("\n--- browser errors ---");
    errors.forEach((e) => console.log(e));
  } else {
    console.log("\nno browser errors.");
  }

  await browser.close();
})().catch((err) => {
  console.error(err);
  process.exit(1);
});
