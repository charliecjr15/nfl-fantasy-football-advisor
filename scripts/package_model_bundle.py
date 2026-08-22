"""Create a hash-verified release archive for cloud inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_DIRECTORY = PROJECT_ROOT / "models" / "v1_evaluated_2025"
MANIFEST_PATH = PROJECT_ROOT / "results" / "tables" / "model_bundle_manifest.csv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "dist" / "model_bundle_v1_evaluated_2025.zip"
)


def parse_arguments() -> argparse.Namespace:
    """Parse archive options."""

    parser = argparse.ArgumentParser(
        description="Package the evaluated model bundle for a GitHub release."
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    """Hash one file in bounded blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_bundle() -> list[Path]:
    """Reconcile the local artifacts with tracked evidence."""

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(f"Bundle manifest not found: {MANIFEST_PATH}")
    manifest = pd.read_csv(MANIFEST_PATH, dtype="string")
    required = {"position", "artifact_path", "artifact_sha256"}
    missing = sorted(required - set(manifest.columns))
    if missing:
        raise ValueError(f"Bundle manifest is missing columns: {missing}")
    files: list[Path] = []
    for row in manifest.itertuples(index=False):
        artifact = PROJECT_ROOT / str(row.artifact_path)
        if not artifact.exists():
            raise FileNotFoundError(f"Model artifact not found: {artifact}")
        if sha256_file(artifact) != str(row.artifact_sha256):
            raise ValueError(f"Model artifact hash mismatch: {artifact}")
        files.append(artifact)

    metadata = BUNDLE_DIRECTORY / "bundle_metadata.json"
    if not metadata.exists():
        raise FileNotFoundError(f"Bundle metadata not found: {metadata}")
    with metadata.open("r", encoding="utf-8") as file_handle:
        payload = json.load(file_handle)
    if payload.get("bundle_version") != "v1_evaluated_2025":
        raise ValueError("Unexpected model bundle version.")
    return [metadata, *files]


def write_deterministic_zip(files: list[Path], output: Path) -> None:
    """Write a stable archive with the expected models/ extraction layout."""

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.stem}.tmp{output.suffix}")
    with zipfile.ZipFile(
        temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(files, key=lambda item: item.name):
            archive_name = f"v1_evaluated_2025/{path.name}"
            info = zipfile.ZipInfo(archive_name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    os.replace(temporary, output)


def main() -> None:
    """Validate and package the release bundle."""

    arguments = parse_arguments()
    output = Path(arguments.output)
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output = output.resolve()
    files = validate_bundle()
    write_deterministic_zip(files, output)
    digest = sha256_file(output)
    checksum_path = output.with_suffix(f"{output.suffix}.sha256")
    checksum_path.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    print(f"bundle_files={len(files)}")
    print(f"bundle_archive={output}")
    print(f"bundle_archive_sha256={digest}")
    print(f"checksum_file={checksum_path}")
    print("bundle_packaging_status=PASS")


if __name__ == "__main__":
    main()
