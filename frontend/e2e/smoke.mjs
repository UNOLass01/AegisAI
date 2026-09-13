/** AegisAI frontend smoke test (Playwright).
 *
 * Requires the full stack: `docker compose up --build -d`
 * (backend :8000, frontend :5173, prometheus :9090).
 * Browsers: `npx playwright install chromium` (one time).
 * Run: `npm run e2e`.
 *
 * Visits every page, asserts real data renders, submits an investigation
 * through the UI, and fails on any page error or console error.
 */
import { chromium } from "playwright";

const FRONTEND = process.env.E2E_FRONTEND ?? "http://localhost:5173";

const failures = [];
const check = (name, condition, extra = "") => {
  if (condition) {
    console.log(`  ok   ${name}`);
  } else {
    console.log(`  FAIL ${name} ${extra}`);
    failures.push(name);
  }
};

const browser = await chromium.launch();
const page = await browser.newPage();
page.on("pageerror", (err) => failures.push(`pageerror: ${err.message}`));
page.on("console", (msg) => {
  if (msg.type() === "error") {
    failures.push(`console.error: ${msg.text().slice(0, 200)}`);
  }
});

async function gotoNav(id, marker) {
  await page.click(`[data-testid="nav-${id}"]`);
  await page.waitForSelector(`[data-testid="${marker}"]`, { timeout: 30000 });
}

await page.goto(FRONTEND, { waitUntil: "networkidle" });

// Overview: metrics + timeline + sparkline.
await page.waitForSelector('[data-testid="page-overview"]', { timeout: 30000 });
await page.waitForSelector('[data-testid="overview-metrics"]');
check("overview metrics panel", true);
const metricValues = await page.locator("#root .metric .value").allTextContents();
check("overview has 4 metric readouts", metricValues.length === 4, JSON.stringify(metricValues));
await page.waitForSelector('[data-testid="overview-timeline"]');
const timelineRows = await page.locator('[data-testid="overview-timeline"] .row').count();
check("overview timeline has seeded investigation", timelineRows >= 1);
await page.waitForTimeout(12000);
check(
  "overview sparkline draws after polls",
  (await page.locator('[data-testid="overview-sparkline"] polyline').count()) === 1
);

// Models: rows + expandable deltas.
await gotoNav("models", "models-list");
for (const version of ["v1", "v2", "v3"]) {
  check(`models row ${version}`, (await page.locator(`[data-testid="model-row-${version}"]`).count()) === 1);
}
await page.click('[data-testid="model-row-v2"]');
await page.waitForSelector('[data-testid="model-detail-v2"]');
const deltaText = await page.locator('[data-testid="model-detail-v2"]').textContent();
check("models v2 detail shows deltas", /[+-]\d+\.\d+/.test(deltaText ?? ""));

// Incidents: list + markdown detail.
await gotoNav("incidents", "incidents-list");
check("incidents row 011", (await page.locator('[data-testid="incident-row-011"]').count()) === 1);
await page.click('[data-testid="incident-row-011"]');
await page.waitForSelector('[data-testid="incident-detail"]');
const incidentText = await page.locator('[data-testid="incident-detail"]').textContent();
check("incident 011 detail renders write-up", (incidentText ?? "").includes("transaction_amount"));

// Investigations: submit through the UI, see verdict + evidence + trace.
await gotoNav("investigations", "investigation-form");
await page.fill('[data-testid="investigation-input"]', "Why did precision drop after we shipped v2?");
await page.click('[data-testid="investigation-submit"]');
await page.waitForSelector('[data-testid="investigation-detail"]', { timeout: 180000 });
const verdict = await page.locator('[data-testid="root-cause"]').textContent();
check("investigation verdict mentions drift", /drift/i.test(verdict ?? ""), verdict ?? "");
check("confidence gauge renders", (await page.locator('[data-testid="confidence-gauge"]').count()) === 1);
check("evidence timeline renders", (await page.locator('[data-testid="evidence-timeline"] .ev-step').count()) >= 4);
check("trace strip renders pills", (await page.locator('[data-testid="trace-strip"] .trace-pill').count()) === 7);
check(
  "recommended actions listed",
  (await page.locator('[data-testid="recommended-actions"] li').count()) >= 2
);

// Evaluation: scorecard + chart + table.
await gotoNav("evaluation", "evaluation-scorecard");
const scorecard = await page.locator('[data-testid="evaluation-scorecard"]').textContent();
check("evaluation scorecard shows accuracy", /Root cause accuracy/.test(scorecard ?? ""));
check("evaluation table has rows", (await page.locator('[data-testid^="eval-row-"]').count()) >= 1);

// System health: charts load from Prometheus (or show explicit errors, never blank).
await gotoNav("health", "health-chart-latency");
check(
  "latency chart draws p50/p95 series",
  (await page.locator('[data-testid="health-chart-latency"] path').count()) >= 2
);
for (const id of ["errors", "tokens", "cost"]) {
  await page.waitForSelector(`[data-testid="health-chart-${id}"]`, { timeout: 30000 });
  const panel = await page.locator(`[data-testid="health-chart-${id}"]`).textContent();
  const ok = /no data in range|Prometheus unreachable/.test(panel ?? "") || (panel ?? "").length > 40;
  check(`health chart ${id} draws or explains itself`, ok);
}

await browser.close();

const consoleFailures = failures.filter((f) => f.startsWith("console.error") || f.startsWith("pageerror"));
if (failures.length > 0) {
  console.log(`\n${failures.length} failure(s):`);
  for (const failure of failures) {
    console.log(` - ${failure}`);
  }
  process.exit(1);
}
console.log(`\nE2E OK (including ${consoleFailures.length} console/page errors: none).`);
