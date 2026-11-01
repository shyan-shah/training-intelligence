/**
 * Visual smoke test. Drives the preview route through every tab in both
 * colour schemes and fails on:
 *
 *   - any console error, which is how the React hydration mismatch caused by
 *     Math.cos differing in its last bit between Node and V8 was found;
 *   - any horizontal overflow, which is how the three-up stat row spilling
 *     past a 390px screen was found;
 *   - a tab that renders nothing.
 *
 * Needs the app running at BASE_URL with the preview route enabled:
 *
 *   npm run build && ENABLE_PREVIEW=1 npm start -- -p 3100
 *   BASE_URL=http://localhost:3100 node scripts/smoke.mjs
 *
 * Set CHROMIUM_PATH to use a Chromium already on the machine instead of one
 * Playwright downloaded.
 */
import { chromium } from "playwright";

const BASE_URL = process.env.BASE_URL ?? "http://localhost:3100";
/** Set when the host already has a Chromium that Playwright did not download
 *  itself, so the script does not need `playwright install` to have run. */
const EXECUTABLE_PATH = process.env.CHROMIUM_PATH || undefined;
const PRIMARY = ["Today", "Week", "Body", "Load"];
const MORE = ["Recovery", "Performance", "Streaks", "Insights"];
const SCHEMES = ["dark", "light"];

const browser = await chromium.launch({
  args: ["--no-sandbox"],
  executablePath: EXECUTABLE_PATH,
});
let failures = 0;

for (const colorScheme of SCHEMES) {
  const ctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    colorScheme,
    isMobile: true,
    hasTouch: true,
  });
  const page = await ctx.newPage();
  const errors = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 200)); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${String(e).slice(0, 200)}`));

  await page.goto(`${BASE_URL}/preview`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1200);

  for (const tab of [...PRIMARY, ...MORE]) {
    errors.length = 0;

    if (tab !== "Today") {
      if (MORE.includes(tab)) {
        await page
          .getByRole("button", { name: /^(More|Recovery|Performance|Streaks|Insights)$/ })
          .last()
          .click();
        await page.waitForTimeout(400);
      }
      await page.getByRole("button", { name: new RegExp(`^${tab}$`) }).last().click();
      await page.waitForTimeout(1500);
    }

    const heading = await page.locator("h1").first().innerText();
    const chars = (await page.locator("main").innerText()).length;
    const hOverflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    );

    const ok = heading === tab && chars > 200 && !hOverflow && errors.length === 0;
    if (!ok) failures += 1;

    console.log(
      `${ok ? "PASS" : "FAIL"} ${colorScheme.padEnd(5)} ${tab.padEnd(12)} ` +
      `chars=${chars} hOverflow=${hOverflow} errors=${errors.length}` +
      (errors.length ? `\n      ${errors[0]}` : ""),
    );
  }

  await ctx.close();
}

await browser.close();
console.log(failures === 0 ? "\nAll tabs clean." : `\n${failures} check(s) failed.`);
process.exit(failures === 0 ? 0 : 1);
