const { chromium } = require(
  process.env.PLAYWRIGHT_MODULE ||
    "/Users/tejas/.npm/_npx/e41f203b7505f1fb/node_modules/playwright",
);
const fs = require("node:fs");
const path = require("node:path");
const root = path.resolve(__dirname, "../docs/interface-concepts");
const assert = (condition, message) => {
  if (!condition) throw Error(message);
};
(async () => {
  const browser = await chromium.launch({ headless: true, channel: "chrome" });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1050 },
    reducedMotion: "reduce",
  });
  const errors = [],
    requests = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("request", (r) => {
    if (r.url().includes("/api/")) requests.push(r.url());
  });
  const result = {};
  page.setDefaultTimeout(8000);
  try {
    for (const c of ["a", "b", "c"]) {
      console.log("Checking concept", c);
      await page.goto(`http://127.0.0.1:5180/concepts/v1?concept=${c}`);
      await page
        .getByRole("navigation", { name: "Interface concepts" })
        .waitFor();
      await page.screenshot({
        path: path.join(root, `screenshots/${c}-overview.png`),
        fullPage: true,
        animations: "disabled",
        style: ".cl-toast { visibility: hidden !important; }",
      });
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${c} desktop overflow`,
      );
      if (c === "a")
        await page
          .getByRole("button", { name: "Open investigation", exact: true })
          .click();
      if (c === "c")
        await page
          .getByRole("button", { name: "Inspect linked evidence", exact: true })
          .click();
      await page.getByRole("button", { name: /Counterevidence/ }).click();
      await page.getByRole("button", { name: /Temperature and pH/ }).click();
      await page
        .getByRole("dialog")
        .last()
        .getByText("Interpretation limit", { exact: true })
        .waitFor();
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: /Missing/ }).click();
      await page
        .getByRole("button", {
          name: /72-hour assay and actual airflow are unavailable/,
        })
        .click();
      await page
        .getByRole("button", {
          name: "Draft request for missing evidence",
          exact: true,
        })
        .click();
      assert(
        await page
          .getByRole("button", { name: "Request drafted locally" })
          .isDisabled(),
        `${c} missing evidence request`,
      );
      await page.keyboard.press("Escape");
      await page.getByRole("button", { name: /Supporting/ }).click();
      if (c === "b") {
        await page
          .getByRole("button", { name: "Batch table", exact: true })
          .click();
        await page
          .getByRole("cell", { name: "Not posted", exact: true })
          .waitFor();
        await page
          .getByRole("button", { name: "Hypotheses", exact: true })
          .click();
        await page
          .getByRole("heading", { name: "Oxygen sensor drift", exact: true })
          .waitFor();
        await page.getByRole("button", { name: "Trends", exact: true }).click();
      }
      await page.screenshot({
        path: path.join(root, `screenshots/${c}-evidence.png`),
        fullPage: true,
        animations: "disabled",
        style: ".cl-toast { visibility: hidden !important; }",
      });
      await page
        .getByRole("button", { name: "Review next action", exact: true })
        .click();
      const dialog = page.getByRole("dialog").last();
      assert(
        await dialog
          .getByRole("button", { name: "Accept draft for handoff" })
          .isDisabled(),
        `${c} review gate`,
      );
      await dialog
        .getByRole("textbox", { name: "Reviewer name", exact: true })
        .fill("Maya Chen");
      await dialog
        .getByRole("textbox", { name: "Review comment", exact: true })
        .fill(
          "Verify the oxygen reading and actual airflow before any process adjustment. Reassess when the assay arrives.",
        );
      await page.screenshot({
        path: path.join(root, `screenshots/${c}-review.png`),
        fullPage: true,
        animations: "disabled",
        style: ".cl-toast { visibility: hidden !important; }",
      });
      await dialog
        .getByRole("button", { name: "Accept draft for handoff" })
        .click();
      await page
        .getByRole("heading", { name: "Draft accepted for handoff" })
        .waitFor();
      const download = page.waitForEvent("download");
      await page
        .getByRole("button", { name: "Download review packet" })
        .click();
      await (await download).saveAs(path.join(root, `example-review-${c}.md`));
      await page.keyboard.press("Escape");
      if (c === "c") {
        await page.getByRole("button", { name: "Close dialog" }).click();
        await page.getByRole("button", { name: "Dismiss companion" }).click();
        await page.getByRole("button", { name: "Alongside 1" }).click();
        await page
          .getByRole("button", { name: "Shift notes", exact: true })
          .click();
        await page.getByRole("heading", { name: "Shift handover" }).waitFor();
      }
      await page.setViewportSize({ width: 390, height: 844 });
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
        `${c} mobile overflow`,
      );
      await page.screenshot({
        path: path.join(root, `screenshots/${c}-mobile.png`),
        fullPage: true,
        animations: "disabled",
        style: ".cl-toast { visibility: hidden !important; }",
      });
      await page.setViewportSize({ width: 1440, height: 1050 });
      result[c] = {
        sourceInspection: true,
        counterevidence: true,
        missingDataRequest: true,
        reviewGate: true,
        localReceipt: true,
        packetDownload: true,
        responsive: true,
      };
    }
    await page.goto("http://127.0.0.1:5180/concepts/v1");
    await page
      .getByRole("heading", { name: "A little ahead of the unexpected." })
      .waitFor();
    await page.keyboard.press("2");
    await page.getByRole("heading", { name: "Follow the change." }).waitFor();
    await page.keyboard.press("3");
    await page
      .getByRole("heading", { name: "There’s more to this oxygen trend." })
      .waitFor();
    await page.keyboard.press("e");
    await page.getByRole("dialog").waitFor();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "Compare concepts" }).click();
    await page
      .getByRole("heading", { name: "Three ways into the same work." })
      .waitFor();
    await page.keyboard.press("Tab");
    assert(
      await page.evaluate(
        () => document.activeElement.closest('[role="dialog"]') !== null,
      ),
      "Modal traps keyboard focus",
    );
    await page.keyboard.press("Escape");
    assert(
      await page
        .getByRole("button", { name: "Compare concepts" })
        .evaluate((el) => el === document.activeElement),
      "Dialog restores invoking control focus",
    );
    await page.goto("http://127.0.0.1:5180/concepts/v1?concept=b");
    await page
      .getByRole("button", { name: "Review next action", exact: true })
      .click();
    await page
      .getByRole("textbox", { name: "Reviewer name", exact: true })
      .fill("Maya Chen");
    await page
      .getByRole("textbox", { name: "Review comment", exact: true })
      .fill(
        "Add explicit criteria for the independent oxygen check before handoff.",
      );
    await page
      .getByRole("button", { name: "Request changes", exact: true })
      .click();
    await page
      .getByRole("heading", { name: "Changes requested", exact: true })
      .waitFor();
    assert(errors.length === 0, errors.join("\n"));
    assert(requests.length === 0, "Prototype called backend");
    fs.writeFileSync(
      path.join(root, "verification.json"),
      JSON.stringify(
        {
          concepts: result,
          keyboardShortcuts: true,
          comparison: true,
          focusTrapAndRestoration: true,
          requestChanges: true,
          pageErrors: errors,
          backendRequests: requests,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      "All three concept walkthroughs, source and uncertainty inspection, review gates, downloads, keyboard shortcuts and responsive layouts passed. No API calls.",
    );
  } catch (error) {
    await page.screenshot({
      path: path.join(root, "screenshots/failure.png"),
      fullPage: true,
    });
    throw error;
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
