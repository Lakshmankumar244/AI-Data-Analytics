const STAGE = {
  preparing: {
    id: "preparing",
    label: "Preparing scan",
    description: "The worker is setting up this scan.",
  },
  submitting: {
    id: "submitting",
    label: "Submitting to CRM",
    description: "The worker is submitting a Bulk Read job to the CRM.",
  },
  waiting: {
    id: "waiting",
    label: "Waiting for CRM",
    description: "The CRM is preparing the export.",
  },
  readyToDownload: {
    id: "readyToDownload",
    label: "Ready to download",
    description: "The CRM export is complete. Download has not started.",
  },
  downloading: {
    id: "downloading",
    label: "Downloading data",
    description: "The worker is downloading the CRM export.",
  },
  processing: {
    id: "processing",
    label: "Processing records",
    description: "The worker is checking extracted records.",
  },
  completed: {
    id: "completed",
    label: "Completed",
    description: "The scan finished. You can open the report.",
  },
  failed: {
    id: "failed",
    label: "Failed",
    description: "The scan stopped and needs attention.",
  },
};

export const STAGE_FLOW = [
  STAGE.preparing,
  STAGE.submitting,
  STAGE.waiting,
  STAGE.readyToDownload,
  STAGE.downloading,
  STAGE.processing,
  STAGE.completed,
];

const STAGE_BAR_PERCENT = {
  preparing: 0,
  submitting: 5,
  waiting: 20,
  readyToDownload: 40,
  downloading: 60,
  processing: 80,
  completed: 100,
  failed: 0,
};

const READY_TO_DOWNLOAD_STATES = new Set(["READY_TO_DOWNLOAD"]);
const DOWNLOAD_STATES = new Set([
  "DOWNLOADING",
  "DOWNLOAD_RETRYABLE",
  "DOWNLOAD_UNKNOWN",
]);
const SUBMIT_STATES = new Set(["PLANNED", "SUBMITTING", "SUBMISSION_UNKNOWN"]);
const WAIT_STATES = new Set(["SUBMITTED", "PROCESSING"]);
const LOCAL_PROCESS_STATES = new Set([
  "DOWNLOADED",
  "PROCESSING_PLANNED",
  "PROCESSED",
]);
const EXPORT_COUNT_STATES = new Set([
  ...READY_TO_DOWNLOAD_STATES,
  ...DOWNLOAD_STATES,
  ...LOCAL_PROCESS_STATES,
]);

function asCount(value) {
  const count = Number(value);
  return Number.isFinite(count) && count > 0 ? count : 0;
}

function firstBulkStatus(module) {
  const jobs = module?.bulkJobs ?? [];
  const pending = jobs.find((job) => String(job.status || "") !== "PROCESSED");
  return String((pending ?? jobs[0])?.status || "");
}

function batchCount(module) {
  return asCount(module?.batches?.total);
}

function providerRecordCount(module) {
  return (module?.bulkJobs ?? []).reduce((highest, job) => {
    const count = Number(job.providerRecordCount);
    return Number.isFinite(count) && count >= 0 ? Math.max(highest, count) : highest;
  }, 0);
}

function exportCountKnown(module) {
  return (module?.bulkJobs ?? []).some((job) => {
    const status = String(job.status || "");
    return EXPORT_COUNT_STATES.has(status) || status === "COMPLETED";
  });
}

export function hasKnownRecordTotal(module) {
  return asCount(module?.expectedRecordCount) > 0 || exportCountKnown(module);
}

export function moduleRecordTotal(module) {
  const expected = asCount(module?.expectedRecordCount);
  if (expected) return expected;
  if (exportCountKnown(module)) return providerRecordCount(module);
  return 0;
}

export function moduleRecordsProcessed(module) {
  return asCount(module?.recordsProcessed);
}

export function moduleRecordsDownloaded(module) {
  return asCount(module?.recordsDownloaded);
}

export function moduleExportRecordCount(module) {
  return providerRecordCount(module);
}

export function activeModuleFromStatus(status) {
  const modules = status?.modules ?? [];
  const pending = modules.filter((module) => module.status !== "COMPLETED");
  return (
    pending.find((module) => module.status !== "PLANNED") ?? pending[0] ?? null
  );
}

export function deriveModuleStage(module) {
  if (!module) return STAGE.preparing;
  const moduleStatus = String(module.status || "");
  const bulkStatus = firstBulkStatus(module);

  if (moduleStatus === "COMPLETED") return STAGE.completed;
  if (
    moduleStatus === "FAILED_TERMINAL" ||
    bulkStatus === "FAILED_TERMINAL" ||
    moduleStatus === "PAUSED_RETRYABLE"
  ) {
    return STAGE.failed;
  }

  if (
    READY_TO_DOWNLOAD_STATES.has(bulkStatus) ||
    READY_TO_DOWNLOAD_STATES.has(moduleStatus)
  ) {
    return STAGE.readyToDownload;
  }

  if (DOWNLOAD_STATES.has(bulkStatus) || DOWNLOAD_STATES.has(moduleStatus)) {
    return STAGE.downloading;
  }

  // Local processing starts after the export file exists. Zoho also uses
  // PROCESSING while the CRM is still building that file, so batches are the
  // signal that this is worker-side record processing.
  if (
    LOCAL_PROCESS_STATES.has(bulkStatus) ||
    LOCAL_PROCESS_STATES.has(moduleStatus) ||
    (bulkStatus === "PROCESSING" && batchCount(module) > 0)
  ) {
    return STAGE.processing;
  }

  if (SUBMIT_STATES.has(bulkStatus)) return STAGE.submitting;

  if (
    WAIT_STATES.has(bulkStatus) ||
    moduleStatus === "SUBMITTED" ||
    moduleStatus === "EXTRACTING" ||
    (moduleStatus === "PROCESSING" && batchCount(module) === 0)
  ) {
    return STAGE.waiting;
  }

  return STAGE.preparing;
}

export function moduleDisplayProgress(module, { isActive = false, isDone = false } = {}) {
  const known = hasKnownRecordTotal(module);
  const total = moduleRecordTotal(module);
  const processed = moduleRecordsProcessed(module);
  const downloaded = moduleRecordsDownloaded(module);
  const stage = deriveModuleStage(module);
  const isDownloadStage =
    stage.id === STAGE.readyToDownload.id || stage.id === STAGE.downloading.id;
  const actual = isDownloadStage ? downloaded : processed;

  if (isDone || module?.status === "COMPLETED") {
    const completedTotal = known ? total : processed || downloaded;
    return {
      percent: 100,
      scanned: completedTotal,
      estimatedTotal: known ? completedTotal : null,
      hasKnownTotal: known || completedTotal > 0,
    };
  }

  if (!isActive) {
    return {
      percent: 0,
      scanned: 0,
      estimatedTotal: known ? total : null,
      hasKnownTotal: known,
    };
  }

  if (actual > 0) {
    const percent =
      known && total
        ? Math.min(99, Math.round((actual / total) * 100))
        : STAGE_BAR_PERCENT[stage.id] ?? STAGE_BAR_PERCENT.processing;
    return {
      percent,
      scanned: actual,
      estimatedTotal: known ? total : null,
      hasKnownTotal: known,
    };
  }

  return {
    percent: STAGE_BAR_PERCENT[stage.id] ?? STAGE_BAR_PERCENT.preparing,
    scanned: 0,
    estimatedTotal: known ? total : null,
    hasKnownTotal: known,
  };
}

export function moduleBarPercent(module, options) {
  return moduleDisplayProgress(module, options).percent;
}

export function deriveScanStage(status) {
  const scanStatus = String(status?.status || "");
  if (scanStatus === "COMPLETED") return STAGE.completed;
  if (scanStatus === "FAILED_TERMINAL" || scanStatus === "PAUSED_RETRYABLE") {
    return STAGE.failed;
  }

  const active = activeModuleFromStatus(status);
  if (active) return deriveModuleStage(active);

  if (["CREATED", "AUTH_VALIDATING", "DISCOVERING"].includes(scanStatus)) {
    return STAGE.preparing;
  }
  if (scanStatus === "PLANNED") return STAGE.preparing;
  if (scanStatus === "EXTRACTING") return STAGE.waiting;
  if (scanStatus === "PROCESSING") return STAGE.processing;
  return STAGE.preparing;
}

export function progressFromStatus(status) {
  const modules = status?.modules ?? [];
  const completedModules = modules.filter(
    (module) => module.status === "COMPLETED"
  ).length;
  const plannedModules = Math.max(
    asCount(status?.plannedModuleCount),
    modules.length
  );
  const recordsProcessed = modules.reduce(
    (total, module) => total + moduleRecordsProcessed(module),
    0
  );
  const recordsTotal = modules.reduce(
    (total, module) => total + moduleRecordTotal(module),
    0
  );
  const exportRecords = modules.reduce(
    (total, module) => total + moduleExportRecordCount(module),
    0
  );
  return {
    completedModules,
    plannedModules,
    recordsProcessed,
    recordsTotal,
    exportRecords,
  };
}

export { STAGE };
