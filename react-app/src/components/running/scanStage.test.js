import { describe, expect, it } from "vitest";
import {
  deriveModuleStage,
  deriveScanStage,
  moduleDisplayProgress,
  moduleRecordsDownloaded,
} from "./scanStage";

function accountReadyToDownload({
  recordsDownloaded = 0,
  recordsProcessed = 0,
  providerRecordCount = 5,
} = {}) {
  return {
    moduleApiName: "Account",
    status: "READY_TO_DOWNLOAD",
    expectedRecordCount: providerRecordCount,
    recordsDownloaded,
    recordsProcessed,
    bulkJobs: [
      {
        bulkJobId: "bulk_account",
        status: "READY_TO_DOWNLOAD",
        providerRecordCount,
      },
    ],
  };
}

describe("scanStage READY_TO_DOWNLOAD mapping", () => {
  it("labels READY_TO_DOWNLOAD as ready to download, not downloading", () => {
    const module = accountReadyToDownload();
    const stage = deriveModuleStage(module);
    expect(stage.id).toBe("readyToDownload");
    expect(stage.label).toBe("Ready to download");
    expect(
      deriveScanStage({
        status: "EXTRACTING",
        modules: [module],
      }).label
    ).toBe("Ready to download");
  });

  it("does not fabricate 3/5 from stage percent when nothing is downloaded", () => {
    const module = accountReadyToDownload({
      recordsDownloaded: 0,
      recordsProcessed: 0,
      providerRecordCount: 5,
    });
    expect(moduleRecordsDownloaded(module)).toBe(0);
    const progress = moduleDisplayProgress(module, { isActive: true });
    expect(progress.scanned).toBe(0);
    expect(progress.estimatedTotal).toBe(5);
    expect(progress.hasKnownTotal).toBe(true);
    expect(progress.scanned).not.toBe(3);
  });

  it("uses recordsDownloaded for download progress, not recordsProcessed or provider count", () => {
    const progress = moduleDisplayProgress(
      accountReadyToDownload({
        recordsDownloaded: 3,
        recordsProcessed: 0,
        providerRecordCount: 5,
      }),
      { isActive: true }
    );
    expect(progress.scanned).toBe(3);
    expect(progress.estimatedTotal).toBe(5);
  });

  it("keeps DOWNLOADING as downloading data and still uses recordsDownloaded", () => {
    const module = {
      moduleApiName: "Account",
      status: "DOWNLOADING",
      expectedRecordCount: 5,
      recordsDownloaded: 0,
      recordsProcessed: 0,
      bulkJobs: [
        {
          status: "DOWNLOADING",
          providerRecordCount: 5,
        },
      ],
    };
    expect(deriveModuleStage(module).label).toBe("Downloading data");
    const progress = moduleDisplayProgress(module, { isActive: true });
    expect(progress.scanned).toBe(0);
    expect(progress.estimatedTotal).toBe(5);
  });
});
