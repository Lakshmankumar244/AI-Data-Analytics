// Matches bulk_read/submit.py (50 credits per Bulk Read job) and
// bulk_read/download.py (1 credit per result download). Status polls also
// cost 1 credit each and are not counted here because poll count is unknown.
const BULK_SUBMIT_CREDITS = 50;
const BULK_DOWNLOAD_CREDITS = 1;

function runtimeBand(moduleCount) {
  if (moduleCount <= 0) {
    return { minSeconds: 0, maxSeconds: 0 };
  }
  // Envelope from the pipeline shape, not a measured timer: one Bulk Read job
  // per module. Record counts are unknown until Bulk Read completes, so this
  // range is module-based rather than a clock.
  const minSeconds = 60 * moduleCount;
  const maxSeconds = 60 * moduleCount * 5;
  return { minSeconds, maxSeconds };
}

export function buildScanEstimate(scopeConfig, accessibleModules = []) {
  const selectedNames = new Set(scopeConfig?.modules ?? []);
  const selected = (Array.isArray(accessibleModules) ? accessibleModules : []).filter(
    (module) => selectedNames.has(module.apiName)
  );
  const moduleCount = selected.length;
  const estimatedApiCredits =
    moduleCount * (BULK_SUBMIT_CREDITS + BULK_DOWNLOAD_CREDITS);
  const runtime = runtimeBand(moduleCount);

  return {
    recordsInRange: null,
    recordsKnown: false,
    estimatedApiCredits,
    estimatedApiCalls: estimatedApiCredits,
    estimatedRuntimeMinSeconds: runtime.minSeconds,
    estimatedRuntimeMaxSeconds: runtime.maxSeconds,
  };
}
