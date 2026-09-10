"""Reproduce only the pinned public derivative, never publish an arbitrary workbook."""
import argparse
import gzip
import hashlib
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sunbridge.solartrace import BUNDLE_DIR, SOURCE_SHA256, SOURCE_URL, normalize_snapshot, read_workbook


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    bundle = read_workbook(args.input, require_pinned=True)
    snapshot = normalize_snapshot(bundle)
    content = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", filename="", compresslevel=9, mtime=0) as archive:
        archive.write(content)
    compressed = buffer.getvalue()
    manifest = {"schema_version": 1, "dataset_id": "solartrace", "version": "v9-9-2025",
        "completed_on": "2025-09-09", "catalog_updated_on": "2026-03-12",
        "source_url": SOURCE_URL, "source_sha256": SOURCE_SHA256,
        "bundle_sha256": hashlib.sha256(compressed).hexdigest(), "bundle_bytes": len(compressed),
        "uncompressed_bytes": len(content), "license_notice": "NOTICE.txt", "stats": snapshot["stats"],
        "tables": {name: len(rows) - (name != "Information") for name, rows in bundle["tables"].items()}}
    # Generated bulk data only. Human-authored changes belong in the parser/docs.
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    (BUNDLE_DIR / "rows.json.gz").write_bytes(compressed)
    (BUNDLE_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
