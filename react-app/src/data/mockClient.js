import connectionFixture from "./fixtures/connection.json";
import scorecardFixture from "./fixtures/scorecard.json";
import userFixture from "./fixtures/user.json";
import trendFixture from "./fixtures/trend.json";
import recordsFixture from "./fixtures/records.json";
import fixPlanFixture from "./fixtures/fix.json";

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Rough per-record timing used to size the mock progress simulation and the
// Setup screen's cost/runtime estimate (D9) - not a real API cost model,
// just enough to make the running screen feel proportional to scope chosen.
const MS_PER_RECORD = 4;

// Mock stand-in for "has this user completed the Zoho OAuth consent flow".
// The real /api/zoho/consent -> Zoho -> callback round trip will set this
// via a real session on the backend; sessionStorage is just the mock's way
// of remembering it across a page load without a server. Delete this whole
// block once the Catalyst backend exists and getConnection() reflects real
// session state instead.
const CONNECTED_KEY = "zoho_mock_connected";

function isMockConnected() {
  return typeof window !== "undefined" && sessionStorage.getItem(CONNECTED_KEY) === "1";
}

// Dev-only convenience: since there's no real backend yet, there's no way
// to actually land on /api/zoho/consent -> Zoho -> callback locally. Run
// `window.__mockConnectZoho()` in the browser console (then reload) to flip
// the mock into a connected state for testing. Not exported from client.js
// - remove entirely once the real backend exists.
if (typeof window !== "undefined") {
  window.__mockConnectZoho = () => {
    sessionStorage.setItem(CONNECTED_KEY, "1");
    console.log("Mock Zoho connection set. Reload the page.");
  };
  window.__mockDisconnectZoho = () => {
    sessionStorage.removeItem(CONNECTED_KEY);
    console.log("Mock Zoho connection cleared. Reload the page.");
  };
}

export async function getConnection() {
  await delay(400);
  return isMockConnected() ? connectionFixture : null;
}

export async function estimateScan(scopeConfig) {
  await delay(150);
  const modules = connectionFixture.accessibleModules.filter((m) =>
    scopeConfig.modules.includes(m.apiName)
  );
  const depthCaps = { quick: 1000, presales: 5000, deep: 20000, full: Infinity };
  const cap = depthCaps[scopeConfig.depth] ?? 5000;
  const recordsInRange = modules.reduce(
    (sum, m) => sum + Math.min(m.recordCount, cap),
    0
  );
  return {
    recordsInRange,
    estimatedApiCalls: Math.ceil(recordsInRange / 200) + modules.length * 2,
    estimatedRuntimeSeconds: Math.round((recordsInRange * MS_PER_RECORD) / 1000),
  };
}

export async function startScan(scopeConfig, onProgress) {
  const scanId = `scan_${Date.now()}`;
  const modules = connectionFixture.accessibleModules.filter((m) =>
    scopeConfig.modules.includes(m.apiName)
  );

  for (const mod of modules) {
    const steps = 5;
    for (let i = 1; i <= steps; i++) {
      await delay(180);
      onProgress?.({
        module: mod.apiName,
        scanned: Math.round((mod.recordCount * i) / steps),
        estimatedTotal: mod.recordCount,
        phase: i < steps ? "extracting" : "classifying",
      });
    }
    onProgress?.({
      module: mod.apiName,
      scanned: mod.recordCount,
      estimatedTotal: mod.recordCount,
      phase: "done",
      complete: true,
    });
  }

  return { scanId };
}

export async function getScorecard(_scanId) {
  await delay(300);
  return scorecardFixture;
}

export async function getUserDetail(_scanId) {
  await delay(250);
  return userFixture;
}

export async function getTrend(_scanId, _grain, _clock) {
  await delay(250);
  return trendFixture;
}

const PAGE_SIZE = 20;

export async function getRecords(_scanId, filters = {}, page = 1) {
  await delay(250);

  let filtered = recordsFixture.records;
  if (filters.states && filters.states.length > 0) {
    filtered = filtered.filter((r) => filters.states.includes(r.state));
  }
  if (filters.modules && filters.modules.length > 0) {
    filtered = filtered.filter((r) => filters.modules.includes(r.module));
  }

  const total = filtered.length;
  const start = (page - 1) * PAGE_SIZE;
  const pageRecords = filtered.slice(start, start + PAGE_SIZE);

  return { total, page, pageSize: PAGE_SIZE, records: pageRecords };
}

export async function getFixPlan(_scanId) {
  await delay(300);
  return fixPlanFixture;
}
