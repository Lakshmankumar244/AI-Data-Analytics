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
  STAGE.downloading,
  STAGE.processing,
  STAGE.completed,
];

const STAGE_BAR_PERCENT = {
  preparing: 0,
  submitting: 5,
  waiting: 20,
  downloading: 60,
  processing: 80,
  completed: 100,
  failed: 0,
};

const DOWNLOAD_STATES = new Set([
  "READY_TO_DOWNLOAD",
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
  return (module?.bulkJobs ?? []).reduce(
    (highest, job) => Math.max(highest, asCount(job.providerRecordCount)),
    0
  );
}

export function moduleRecordTotal(module) {
  return asCount(module?.expectedRecordCount) || providerRecordCount(module);
}

export function moduleRecordsProcessed(module) {
  return asCount(module?.recordsProcessed);
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
  const total = moduleRecordTotal(module);
  const actual = moduleRecordsProcessed(module);

  if (isDone || module?.status === "COMPLETED") {
    const completedTotal = total || actual;
    return {
      percent: 100,
      scanned: completedTotal,
      estimatedTotal: completedTotal,
    };
  }

  if (!isActive) {
    return { percent: 0, scanned: 0, estimatedTotal: total };
  }

  const stage = deriveModuleStage(module);
  if (actual > 0) {
    const percent = total
      ? Math.min(99, Math.round((actual / total) * 100))
      : STAGE_BAR_PERCENT.processing;
    return { percent, scanned: actual, estimatedTotal: total };
  }

  const percent = STAGE_BAR_PERCENT[stage.id] ?? STAGE_BAR_PERCENT.preparing;
  return {
    percent,
    scanned: total ? Math.round((total * percent) / 100) : 0,
    estimatedTotal: total,
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
