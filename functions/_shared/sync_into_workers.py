"""Copy shared source into independently deployed Catalyst functions.

Catalyst zips each function directory on its own. This script:

- puts `_shared/worker` inside both Job Function trees as `shared/`
- puts `_shared/salesforce` modules into the HTTP function and Salesforce
  worker `salesforce/` packages (not the Zoho worker)
- puts Zoho Bulk Read / connection / profiler modules into the HTTP function
  and Zoho worker (not the Salesforce worker)
"""

from __future__ import annotations

import filecmp
import shutil
from pathlib import Path


SHARED_ROOT = Path(__file__).resolve().parent
SHARED_WORKER = SHARED_ROOT / "worker"
SHARED_SALESFORCE = SHARED_ROOT / "salesforce"
FUNCTIONS_ROOT = SHARED_ROOT.parent
WORKER_PACKAGES = (
    FUNCTIONS_ROOT / "ai_data_analytics_worker" / "shared",
    FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker" / "shared",
)
SALESFORCE_FILES = (
    "client.py",
    "describe.py",
    "bulk_query.py",
    "bulk_results.py",
    "owner_resolution.py",
)
SALESFORCE_PACKAGES = (
    FUNCTIONS_ROOT / "ai_data_analytics_function" / "salesforce",
    FUNCTIONS_ROOT / "ai_data_analytics_salesforce_worker" / "salesforce",
)
ZOHO_WORKER = FUNCTIONS_ROOT / "ai_data_analytics_worker"
HTTP_FUNCTION = FUNCTIONS_ROOT / "ai_data_analytics_function"
ZOHO_PACKAGES = (
    HTTP_FUNCTION,
    ZOHO_WORKER,
)
ZOHO_SHARED_FILES = (
    ("zoho", ("client.py", "user_directory.py")),
    (
        "bulk_read",
        (
            "prepare.py",
            "submit.py",
            "status.py",
            "download.py",
            "request_builder.py",
        ),
    ),
    ("connections", ("token.py", "access.py")),
    ("orchestration", ("choose.py",)),
    ("common", ("profiler.py",)),
)


def sync_shared_worker():
    if not SHARED_WORKER.is_dir():
        raise FileNotFoundError(f"Shared worker source missing: {SHARED_WORKER}")
    copied = []
    for dest in WORKER_PACKAGES:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            SHARED_WORKER,
            dest,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        copied.append(dest)
    return copied


def sync_shared_salesforce():
    if not SHARED_SALESFORCE.is_dir():
        raise FileNotFoundError(
            f"Shared Salesforce source missing: {SHARED_SALESFORCE}"
        )
    copied = []
    for dest in SALESFORCE_PACKAGES:
        dest.mkdir(parents=True, exist_ok=True)
        for name in SALESFORCE_FILES:
            source = SHARED_SALESFORCE / name
            if not source.is_file():
                raise FileNotFoundError(f"Shared Salesforce module missing: {source}")
            target = dest / name
            shutil.copy2(source, target)
            copied.append(target)
    return copied


def sync_shared_zoho():
    copied = []
    for package, names in ZOHO_SHARED_FILES:
        source_dir = SHARED_ROOT / package
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Shared {package} source missing: {source_dir}")
        for dest_root in ZOHO_PACKAGES:
            dest_dir = dest_root / package
            dest_dir.mkdir(parents=True, exist_ok=True)
            for name in names:
                source = source_dir / name
                if not source.is_file():
                    raise FileNotFoundError(
                        f"Shared {package} module missing: {source}"
                    )
                target = dest_dir / name
                shutil.copy2(source, target)
                copied.append(target)
    return copied


def sync_shared_source():
    return {
        "worker": sync_shared_worker(),
        "salesforce": sync_shared_salesforce(),
        "zoho": sync_shared_zoho(),
    }


def packaged_copies_match_source():
    mismatches = []
    for dest in WORKER_PACKAGES:
        comparison = filecmp.dircmp(SHARED_WORKER, dest, ignore=["__pycache__"])
        mismatches.extend(_dir_mismatches(comparison, dest))
    for dest in SALESFORCE_PACKAGES:
        for name in SALESFORCE_FILES:
            source = SHARED_SALESFORCE / name
            target = dest / name
            if not target.is_file():
                mismatches.append(f"missing from {dest}: {name}")
            elif source.read_bytes() != target.read_bytes():
                mismatches.append(f"differs in {dest}: {name}")
    for dest_root in ZOHO_PACKAGES:
        for package, names in ZOHO_SHARED_FILES:
            for name in names:
                source = SHARED_ROOT / package / name
                target = dest_root / package / name
                if not target.is_file():
                    mismatches.append(f"missing from {dest_root}: {package}/{name}")
                elif source.read_bytes() != target.read_bytes():
                    mismatches.append(f"differs in {dest_root}: {package}/{name}")
    return mismatches


def _dir_mismatches(comparison, dest):
    found = []
    for name in comparison.left_only:
        if name == "__pycache__":
            continue
        found.append(f"missing from {dest}: {name}")
    for name in comparison.right_only:
        if name == "__pycache__":
            continue
        found.append(f"extra in {dest}: {name}")
    for name in comparison.diff_files:
        found.append(f"differs in {dest}: {name}")
    for name, nested in comparison.subdirs.items():
        if name == "__pycache__":
            continue
        found.extend(_dir_mismatches(nested, dest / name))
    return found


if __name__ == "__main__":
    result = sync_shared_source()
    for dest in result["worker"]:
        print(f"packaged shared worker into {dest}")
    for dest in result["salesforce"]:
        print(f"packaged shared Salesforce module into {dest}")
    for dest in result["zoho"]:
        print(f"packaged shared Zoho module into {dest}")
