// Walks each interaction concept through the F-2408 scenario and captures screenshots.
// Usage: (cd frontend && npm run dev) then  node frontend/scripts/check_lab.cjs
// PLAYWRIGHT_MODULE may point at any local playwright install.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const fs = require("node:fs");
const path = require("node:path");

const base = process.env.LAB_URL || "http://127.0.0.1:5180";
const out = path.resolve(__dirname, "../docs/interface-concepts/v3/screenshots");
fs.mkdirSync(out, { recursive: true });
const assert = (c, m) => {
  if (!c) throw new Error(m);
};

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  page.setDefaultTimeout(8000);
  const shot = (name, full = false) => page.screenshot({ path: path.join(out, `${name}.png`), fullPage: full });
  const settle = () => page.waitForTimeout(450);

  // A — Work queue
  await page.goto(`${base}/concepts?concept=a`);
  await page.getByText("Assistant is checking the latest BR-04 data").waitFor();
  await shot("a-0-checking");
  await page.getByRole("button", { name: "Titer below reference range", exact: true }).waitFor();
  await settle();
  await shot("a-1-queue");
  await page.getByRole("button", { name: /F-2391 ran at 30 % DO/ }).click();
  await page.getByText("What this does not show").waitFor();
  await settle();
  await shot("a-2-source");
  await page.keyboard.press("Escape");
  await page.keyboard.press("r");
  await page.getByRole("button", { name: /Send to QMS as draft/ }).waitFor();
  await settle();
  await shot("a-3-review");
  await page.getByRole("button", { name: /Send to QMS as draft/ }).click();
  await page.getByText("Draft event created for QA review").waitFor();
  await shot("a-4-receipt");
  await page.getByRole("button", { name: "Done" }).click();
  await page.getByLabel("60 h assay arrives").check({ force: true });
  await settle();
  await shot("a-5-follow-up");
  await page.getByRole("button", { name: "Approve harvest record", exact: true }).click();
  await settle();
  await shot("a-6-routine-item");
  await page.keyboard.press("Meta+k");
  await page.getByPlaceholder(/Search batches, tags, samples/).waitFor();
  await settle();
  await shot("a-7-search");
  await page.keyboard.press("Escape");

  // B — Batch record with the Assistant panel
  await page.goto(`${base}/concepts?concept=b`);
  await page.getByText("Comparing F-2408 titer").waitFor();
  await shot("b-0-checking");
  await page.getByRole("button", { name: "Compare DO, agitation and antifoam" }).waitFor();
  await settle();
  await shot("b-1-summary");
  await page.getByRole("button", { name: "Compare DO, agitation and antifoam" }).click();
  await page.getByText("Opened Trends · 3 pens · reference added").waitFor();
  await page.waitForTimeout(600);
  await shot("b-2-trends");
  await page.getByRole("tab", { name: "Lab results" }).click();
  await settle();
  await shot("b-3-lab");
  await page.getByRole("tab", { name: "Events and alarms" }).click();
  await settle();
  await shot("b-4-events");
  await page.getByRole("tab", { name: /Investigation/ }).click();
  await settle();
  await shot("b-5-investigation");
  await page.getByRole("button", { name: /Contradicts: F-2391/ }).click();
  await page.getByText("What this does not show").waitFor();
  await settle();
  await shot("b-6-source");
  await page.keyboard.press("Escape");
  await page.getByLabel("Ask the Assistant").fill("what should we do next?");
  await page.keyboard.press("Enter");
  await page.getByText("Opened Investigation · proposed actions").waitFor();
  await page.waitForTimeout(600);
  await shot("b-7-plan");
  await page.getByRole("button", { name: /Review plan/ }).first().click();
  await page.getByRole("button", { name: /Send to QMS as draft/ }).waitFor();
  await settle();
  await shot("b-8-review");
  await page.keyboard.press("Escape");

  // C — Embedded companion
  await page.goto(`${base}/concepts?concept=c`);
  await page.getByText("Assistant checking BR-04…").waitFor();
  await shot("c-0-host");
  await page.getByRole("button", { name: /1 finding on this batch/ }).waitFor();
  await settle();
  await shot("c-1-notice");
  await page.getByRole("button", { name: /1 finding on this batch/ }).click();
  await page.getByRole("button", { name: "Show reference on this trend" }).click();
  await settle();
  await shot("c-2-overlay");
  await page.getByRole("button", { name: /BR04.TEMP.PV/ }).click();
  await settle();
  await shot("c-3-context-temp");
  await page.getByRole("button", { name: /BR04.DO.PV/ }).click();
  await page.getByRole("tab", { name: /Evidence/ }).click();
  await page.getByRole("button", { name: /Off-gas analysis is missing/ }).click();
  await settle();
  await shot("c-4-missing-detail");
  await page.getByRole("button", { name: "Back" }).click();
  await page.getByRole("tab", { name: "Next step" }).click();
  await page.getByRole("button", { name: "Draft it in QualityTrack" }).click();
  await settle();
  await shot("c-5-qms-draft");
  for (const cb of await page.getByLabel("I've checked this").all()) await cb.check();
  await page.getByRole("button", { name: /Save draft & route to QA/ }).click();
  await page.getByText("Draft saved · routed to QA").waitFor();
  await shot("c-6-qms-saved");
  await page.getByRole("tab", { name: "PlantView Historian" }).click();
  await page.getByRole("button", { name: "Open batch record" }).click();
  await page.getByRole("button", { name: /Back to the historian/ }).waitFor();
  await settle();
  await shot("c-7-workspace");
  await page.keyboard.press("Escape");

  await page.goto(`${base}/concepts?concept=compare`);
  await page.getByRole("heading", { name: /Three familiar places/ }).waitFor();
  await settle();
  await shot("compare", true);

  // Narrow viewport
  await page.setViewportSize({ width: 390, height: 844 });
  for (const c of ["a", "b", "c"]) {
    await page.goto(`${base}/concepts?concept=${c}&instant`);
    await page.waitForTimeout(900);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${c} mobile horizontal overflow`);
    await shot(`${c}-mobile`);
  }

  await browser.close();
  fs.writeFileSync(path.join(out, "../verification.json"), JSON.stringify({ checkedAt: new Date().toISOString(), errors, interactionsToSource: { a: 2, b: 2, c: 3 } }, null, 2));
  if (errors.length) {
    console.error("Page errors:\n" + errors.join("\n"));
    process.exit(1);
  }
  console.log("All concept walkthroughs passed. Screenshots in", out);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
