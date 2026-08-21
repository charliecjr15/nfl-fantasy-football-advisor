
"""Run target-free batch inference with the validated Version 1 bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import sklearn

from train_models import (
    configured_columns,
    prepare_predictors,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "config" / "inference_settings.toml"
)

EXPECTED_POSITION_MODELS = {
    "QB": "hist_gradient_boosting",
    "RB": "random_forest",
    "WR": "ridge",
    "TE": "ridge",
}

EXPECTED_ESTIMATOR_CLASSES = {
    "hist_gradient_boosting": (
        "HistGradientBoostingRegressor"
    ),
    "random_forest": "RandomForestRegressor",
    "ridge": "Ridge",
}


def parse_arguments() -> argparse.Namespace:
    """Parse smoke-test or general batch-inference arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Verify the Version 1 bundle and generate target-free "
            "fantasy-point projections."
        )
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--smoke-test",
        action="store_true",
        help=(
            "Run the configured target-free historical smoke test."
        ),
    )
    mode.add_argument(
        "--input",
        help=(
            "Path to a future target-free Parquet or CSV feature file."
        ),
    )

    parser.add_argument(
        "--output",
        help=(
            "Prediction output path for general inference. "
            "Required with --input."
        ),
    )
    parser.add_argument(
        "--manifest-output",
        help=(
            "Optional run-manifest path for general inference. "
            "Defaults beside the prediction output."
        ),
    )
    parser.add_argument(
        "--data-split",
        help=(
            "Optional data_split value to filter during general "
            "inference."
        ),
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the inference settings TOML file.",
    )
    parser.add_argument(
        "--confirm-inference",
        required=True,
        help=(
            "Required confirmation token from the inference "
            "configuration."
        ),
    )

    arguments = parser.parse_args()

    if arguments.smoke_test:
        if (
            arguments.output
            or arguments.manifest_output
            or arguments.data_split
        ):
            parser.error(
                "--smoke-test uses configured output paths and "
                "cannot be combined with output overrides."
            )
    elif not arguments.output:
        parser.error("--output is required with --input.")

    return arguments


def print_section(title: str) -> None:
    """Print a readable console section."""

    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def resolve_project_path(path_value: str) -> Path:
    """Resolve a configured path relative to the project root."""

    path = Path(path_value)

    if not path.is_absolute():
        path = PROJECT_ROOT / path

    return path.resolve()


def display_path(path: Path) -> str:
    """Return a stable project-relative path where possible."""

    resolved = path.resolve()

    if resolved.is_relative_to(PROJECT_ROOT):
        return str(
            resolved.relative_to(PROJECT_ROOT)
        ).replace("\\", "/")

    return str(resolved)


def load_toml(path: Path) -> dict[str, Any]:
    """Load a UTF-8 TOML file."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration not found: {path}")

    with path.open("rb") as file:
        return tomllib.load(file)


def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest in bounded blocks."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def unavailable_rows(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> int:
    """Count rows with a null or blank required value."""

    unavailable = pd.Series(
        False,
        index=dataframe.index,
        dtype="bool",
    )

    for column in columns:
        column_unavailable = dataframe[column].isna()

        if (
            pd.api.types.is_object_dtype(dataframe[column])
            or pd.api.types.is_string_dtype(dataframe[column])
        ):
            column_unavailable = (
                column_unavailable
                | dataframe[column]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq("")
            )

        unavailable = unavailable | column_unavailable

    return int(unavailable.sum())


def validate_inference_configuration(
    configuration: dict[str, Any],
    confirmation_token: str,
) -> None:
    """Validate the frozen inference contract."""

    required_sections = {
        "inference",
        "lineage",
        "inputs",
        "position_models",
        "quality",
        "smoke_test",
    }

    missing_sections = sorted(
        required_sections - set(configuration)
    )

    if missing_sections:
        raise ValueError(
            "Inference configuration is missing sections: "
            + ", ".join(missing_sections)
        )

    inference = configuration["inference"]
    lineage = configuration["lineage"]
    inputs = configuration["inputs"]
    position_models = dict(configuration["position_models"])
    quality = configuration["quality"]
    smoke = configuration["smoke_test"]

    if confirmation_token != inference["confirmation_token"]:
        raise ValueError(
            "Incorrect inference confirmation token."
        )

    if inference["version"] != "v1_bundle_inference":
        raise ValueError("Unexpected inference version.")

    if inference["bundle_version"] != "v1_evaluated_2025":
        raise ValueError("Unexpected model-bundle version.")

    if inference["allow_model_reselection"]:
        raise ValueError(
            "Model reselection must remain disabled."
        )

    if inference["load_target_column"]:
        raise ValueError(
            "The inference workflow must not load the target."
        )

    required_true_flags = [
        "preserve_input_order",
        "require_clean_worktree",
        "fail_if_output_exists",
        "verify_artifact_hashes",
        "verify_metadata_hash",
    ]

    for flag in required_true_flags:
        if not inference[flag]:
            raise ValueError(
                f"Required inference safeguard is disabled: {flag}"
            )

    supported_formats = list(
        inference["supported_input_formats"]
    )

    if supported_formats != [".parquet", ".csv"]:
        raise ValueError(
            "Supported input formats do not match the contract."
        )

    if position_models != EXPECTED_POSITION_MODELS:
        raise ValueError(
            "Inference position mapping differs from Version 1."
        )

    expected_lineage_keys = {
        "bundle_protocol_commit",
        "bundle_evidence_commit",
        "bundle_manifest_sha256",
        "bundle_verification_sha256",
        "bundle_metadata_sha256",
        "smoke_input_sha256",
        "reference_predictions_sha256",
    }

    if set(lineage) != expected_lineage_keys:
        raise ValueError(
            "Inference lineage keys do not match the contract."
        )

    for key, value in lineage.items():
        if key.endswith("_sha256"):
            digest = str(value).lower()

            if (
                len(digest) != 64
                or any(
                    character not in "0123456789abcdef"
                    for character in digest
                )
            ):
                raise ValueError(
                    f"Invalid configured SHA-256 value: {key}"
                )

    expected_input_keys = {
        "model_settings_path",
        "bundle_manifest_path",
        "bundle_verification_path",
        "bundle_metadata_path",
    }

    if set(inputs) != expected_input_keys:
        raise ValueError(
            "Inference input keys do not match the contract."
        )

    if int(quality["expected_predictor_features"]) != 102:
        raise ValueError(
            "Unexpected predictor-count contract."
        )

    if int(quality["expected_bundle_manifest_rows"]) != 4:
        raise ValueError(
            "Unexpected bundle-manifest row contract."
        )

    if int(
        quality["expected_bundle_verification_rows"]
    ) != 5:
        raise ValueError(
            "Unexpected bundle-verification row contract."
        )

    if int(quality["expected_artifact_files"]) != 4:
        raise ValueError(
            "Unexpected artifact-count contract."
        )

    expected_positions = ["QB", "RB", "WR", "TE"]

    if list(quality["supported_positions"]) != expected_positions:
        raise ValueError(
            "Supported-position order is incorrect."
        )

    if set(quality["key_columns"]) != {
        "season",
        "week",
        "player_id",
    }:
        raise ValueError("Inference key contract is incorrect.")

    if not set(quality["key_columns"]).issubset(
        quality["required_metadata_columns"]
    ):
        raise ValueError(
            "Key columns must also be required metadata."
        )

    if float(quality["prediction_absolute_tolerance"]) <= 0:
        raise ValueError(
            "Prediction tolerance must be greater than zero."
        )

    for flag in [
        "require_zero_duplicate_keys",
        "require_zero_unavailable_keys",
        "require_zero_missing_predictions",
        "require_finite_predictions",
    ]:
        if not quality[flag]:
            raise ValueError(
                f"Required quality control is disabled: {flag}"
            )

    expected_smoke_keys = {
        "input_path",
        "data_split_column",
        "data_split_value",
        "reference_predictions_path",
        "reference_prediction_column",
        "reference_source_model_column",
        "expected_rows",
        "predictions_path",
        "sample_path",
        "sample_rows",
        "verification_path",
        "run_manifest_path",
    }

    if set(smoke) != expected_smoke_keys:
        raise ValueError(
            "Smoke-test keys do not match the contract."
        )

    if smoke["data_split_value"] != "test":
        raise ValueError(
            "Smoke test must use the frozen test split."
        )

    if int(smoke["expected_rows"]) != 6037:
        raise ValueError(
            "Unexpected smoke-test row contract."
        )

    if int(smoke["sample_rows"]) != 500:
        raise ValueError(
            "Unexpected smoke-test sample contract."
        )

    smoke_outputs = [
        smoke["predictions_path"],
        smoke["sample_path"],
        smoke["verification_path"],
        smoke["run_manifest_path"],
    ]

    if len(set(smoke_outputs)) != len(smoke_outputs):
        raise ValueError(
            "Smoke-test output paths must be unique."
        )


def run_git_command(*arguments: str) -> str:
    """Run a read-only Git command."""

    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


def validate_git_state(
    configuration: dict[str, Any],
) -> tuple[str, dict[str, str]]:
    """Require a clean repository containing bundle commits."""

    current_commit = run_git_command("rev-parse", "HEAD")
    worktree_status = run_git_command("status", "--porcelain")
    full_commits: dict[str, str] = {}

    for commit_key in [
        "bundle_protocol_commit",
        "bundle_evidence_commit",
    ]:
        configured_commit = configuration["lineage"][
            commit_key
        ]
        full_commit = run_git_command(
            "rev-parse",
            str(configured_commit),
        )

        check = subprocess.run(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                full_commit,
                current_commit,
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        is_ancestor = check.returncode == 0

        print(f"{commit_key}={full_commit}")
        print(f"{commit_key}_is_ancestor={is_ancestor}")

        if not is_ancestor:
            raise ValueError(
                f"{commit_key} is not an ancestor of HEAD."
            )

        full_commits[commit_key] = full_commit

    print(f"current_commit={current_commit}")
    print(f"worktree_clean={worktree_status == ''}")

    if worktree_status:
        raise ValueError(
            "Commit the inference protocol before loading models."
        )

    return current_commit, full_commits


def resolve_bundle_paths(
    configuration: dict[str, Any],
) -> dict[str, Path]:
    """Resolve the model settings and bundle-evidence paths."""

    return {
        name: resolve_project_path(path_value)
        for name, path_value
        in configuration["inputs"].items()
    }


def build_run_specification(
    arguments: argparse.Namespace,
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """Resolve smoke-test or general-inference paths."""

    if arguments.smoke_test:
        smoke = configuration["smoke_test"]

        return {
            "mode": "smoke_test",
            "input": resolve_project_path(smoke["input_path"]),
            "output": resolve_project_path(
                smoke["predictions_path"]
            ),
            "manifest": resolve_project_path(
                smoke["run_manifest_path"]
            ),
            "sample": resolve_project_path(
                smoke["sample_path"]
            ),
            "verification": resolve_project_path(
                smoke["verification_path"]
            ),
            "reference": resolve_project_path(
                smoke["reference_predictions_path"]
            ),
            "data_split_column": smoke[
                "data_split_column"
            ],
            "data_split_value": smoke["data_split_value"],
            "expected_rows": int(smoke["expected_rows"]),
            "sample_rows": int(smoke["sample_rows"]),
        }

    input_path = resolve_project_path(arguments.input)
    output_path = resolve_project_path(arguments.output)

    if arguments.manifest_output:
        manifest_path = resolve_project_path(
            arguments.manifest_output
        )
    else:
        manifest_path = output_path.with_name(
            f"{output_path.stem}_manifest.csv"
        )

    return {
        "mode": "general_inference",
        "input": input_path,
        "output": manifest_path.parent / output_path.name,
        "manifest": manifest_path,
        "sample": None,
        "verification": None,
        "reference": None,
        "data_split_column": (
            "data_split" if arguments.data_split else None
        ),
        "data_split_value": arguments.data_split,
        "expected_rows": None,
        "sample_rows": None,
    }


def validate_run_paths(
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
) -> None:
    """Validate input/output path safety and no-overwrite state."""

    input_path = run_specification["input"]

    if not input_path.exists():
        raise FileNotFoundError(
            f"Inference input not found: {input_path}"
        )

    supported_formats = set(
        configuration["inference"][
            "supported_input_formats"
        ]
    )

    if input_path.suffix.lower() not in supported_formats:
        raise ValueError(
            "Inference input must be Parquet or CSV."
        )

    output_path = run_specification["output"]

    if output_path.suffix.lower() not in supported_formats:
        raise ValueError(
            "Prediction output must be Parquet or CSV."
        )

    output_paths = [
        run_specification["output"],
        run_specification["manifest"],
    ]

    for optional_name in ["sample", "verification"]:
        optional_path = run_specification[optional_name]

        if optional_path is not None:
            output_paths.append(optional_path)

    if len(set(output_paths)) != len(output_paths):
        raise ValueError(
            "Inference output paths must be unique."
        )

    for path in output_paths:
        if not path.resolve().is_relative_to(PROJECT_ROOT):
            raise ValueError(
                "Inference outputs must remain inside the project."
            )

        if path.resolve() == input_path.resolve():
            raise ValueError(
                "Inference output cannot overwrite its input."
            )

    existing_outputs = [
        display_path(path)
        for path in output_paths
        if path.exists()
    ]

    print(f"existing_inference_outputs={existing_outputs}")

    if existing_outputs:
        raise FileExistsError(
            "Inference outputs already exist and will not be "
            "overwritten."
        )


def validate_frozen_hashes(
    configuration: dict[str, Any],
    bundle_paths: dict[str, Path],
    run_specification: dict[str, Any],
) -> dict[str, str]:
    """Validate all frozen evidence before model deserialization."""

    hash_contract = {
        "bundle_manifest_path": (
            "bundle_manifest_sha256"
        ),
        "bundle_verification_path": (
            "bundle_verification_sha256"
        ),
        "bundle_metadata_path": (
            "bundle_metadata_sha256"
        ),
    }

    if run_specification["mode"] == "smoke_test":
        hash_contract["smoke_input"] = "smoke_input_sha256"
        hash_contract["reference"] = (
            "reference_predictions_sha256"
        )

    paths = dict(bundle_paths)
    paths["smoke_input"] = run_specification["input"]
    paths["reference"] = run_specification["reference"]

    observed_hashes: dict[str, str] = {}

    for path_name, hash_name in hash_contract.items():
        path = paths[path_name]

        if path is None or not path.exists():
            raise FileNotFoundError(
                f"Frozen inference input not found: {path}"
            )

        observed_hash = sha256_file(path)
        expected_hash = str(
            configuration["lineage"][hash_name]
        ).lower()
        matches = observed_hash == expected_hash

        print(f"{path_name}_sha256={observed_hash}")
        print(f"{path_name}_hash_matches={matches}")

        if not matches:
            raise ValueError(
                f"Frozen hash mismatch: {path_name}"
            )

        observed_hashes[path_name] = observed_hash

    return observed_hashes


def validate_bundle_evidence(
    configuration: dict[str, Any],
    bundle_paths: dict[str, Path],
    full_commits: dict[str, str],
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    pd.DataFrame,
    list[str],
    list[str],
    list[str],
    str,
]:
    """Validate manifests, metadata, schema, and package versions."""

    manifest = pd.read_csv(
        bundle_paths["bundle_manifest_path"]
    )
    verification = pd.read_csv(
        bundle_paths["bundle_verification_path"]
    )

    with bundle_paths["bundle_metadata_path"].open(
        "r",
        encoding="utf-8",
    ) as file:
        metadata = json.load(file)

    expected_manifest_rows = int(
        configuration["quality"][
            "expected_bundle_manifest_rows"
        ]
    )
    expected_verification_rows = int(
        configuration["quality"][
            "expected_bundle_verification_rows"
        ]
    )

    print(f"bundle_manifest_rows={len(manifest):,}")
    print(
        "bundle_verification_rows="
        f"{len(verification):,}"
    )

    if len(manifest) != expected_manifest_rows:
        raise ValueError(
            "Bundle manifest row count is incorrect."
        )

    if len(verification) != expected_verification_rows:
        raise ValueError(
            "Bundle verification row count is incorrect."
        )

    required_manifest_columns = {
        "bundle_version",
        "build_commit",
        "position",
        "algorithm",
        "artifact_path",
        "artifact_sha256",
        "predictor_count",
        "prediction_mismatch_rows",
        "reload_mismatch_rows",
        "verification_status",
        "metadata_path",
        "metadata_sha256",
    }

    missing_manifest_columns = sorted(
        required_manifest_columns - set(manifest.columns)
    )

    if missing_manifest_columns:
        raise ValueError(
            "Bundle manifest is missing columns: "
            + ", ".join(missing_manifest_columns)
        )

    if manifest["position"].duplicated().any():
        raise ValueError(
            "Bundle manifest contains duplicate positions."
        )

    if set(manifest["position"]) != set(
        configuration["quality"]["supported_positions"]
    ):
        raise ValueError(
            "Bundle manifest positions are incorrect."
        )

    observed_mapping = dict(
        zip(
            manifest["position"],
            manifest["algorithm"],
            strict=True,
        )
    )

    if observed_mapping != dict(
        configuration["position_models"]
    ):
        raise ValueError(
            "Bundle manifest model mapping is incorrect."
        )

    if set(manifest["bundle_version"]) != {
        configuration["inference"]["bundle_version"]
    }:
        raise ValueError(
            "Bundle manifest version is incorrect."
        )

    if set(manifest["build_commit"]) != {
        full_commits["bundle_protocol_commit"]
    }:
        raise ValueError(
            "Bundle manifest build commit is incorrect."
        )

    if set(manifest["predictor_count"]) != {
        int(
            configuration["quality"][
                "expected_predictor_features"
            ]
        )
    }:
        raise ValueError(
            "Bundle manifest predictor counts are incorrect."
        )

    if (
        manifest["prediction_mismatch_rows"].sum()
        or manifest["reload_mismatch_rows"].sum()
    ):
        raise ValueError(
            "Bundle manifest contains prediction mismatches."
        )

    if set(manifest["verification_status"]) != {"PASS"}:
        raise ValueError(
            "Bundle manifest contains failed artifacts."
        )

    required_verification_columns = {
        "scope",
        "position",
        "prediction_mismatch_rows",
        "reload_mismatch_rows",
        "verification_status",
    }

    missing_verification_columns = sorted(
        required_verification_columns
        - set(verification.columns)
    )

    if missing_verification_columns:
        raise ValueError(
            "Bundle verification is missing columns: "
            + ", ".join(missing_verification_columns)
        )

    if (
        verification["prediction_mismatch_rows"].sum()
        or verification["reload_mismatch_rows"].sum()
    ):
        raise ValueError(
            "Bundle verification contains mismatches."
        )

    if set(verification["verification_status"]) != {
        "PASS"
    }:
        raise ValueError(
            "Bundle verification contains failed rows."
        )

    metadata_paths = set(manifest["metadata_path"])
    expected_metadata_path = display_path(
        bundle_paths["bundle_metadata_path"]
    )

    if metadata_paths != {expected_metadata_path}:
        raise ValueError(
            "Bundle metadata paths do not reconcile."
        )

    metadata_hashes = set(manifest["metadata_sha256"])
    expected_metadata_hash = configuration["lineage"][
        "bundle_metadata_sha256"
    ]

    if metadata_hashes != {expected_metadata_hash}:
        raise ValueError(
            "Bundle metadata hashes do not reconcile."
        )

    if metadata["bundle_version"] != configuration[
        "inference"
    ]["bundle_version"]:
        raise ValueError(
            "Bundle metadata version is incorrect."
        )

    if metadata["build_commit"] != full_commits[
        "bundle_protocol_commit"
    ]:
        raise ValueError(
            "Bundle metadata build commit is incorrect."
        )

    if metadata["model_reselection_performed"]:
        raise ValueError(
            "Bundle metadata records model reselection."
        )

    if metadata["test_metrics_recalculated"]:
        raise ValueError(
            "Bundle metadata records test metric recalculation."
        )

    metadata_mapping = {
        position: details["algorithm"]
        for position, details
        in metadata["position_models"].items()
    }

    if metadata_mapping != dict(
        configuration["position_models"]
    ):
        raise ValueError(
            "Bundle metadata model mapping is incorrect."
        )

    model_settings_path = bundle_paths[
        "model_settings_path"
    ]
    model_settings_hash = sha256_file(
        model_settings_path
    )
    expected_model_settings_hash = metadata[
        "source_hashes"
    ]["model_settings_path"]

    print(
        "model_settings_sha256="
        f"{model_settings_hash}"
    )
    print(
        "model_settings_hash_matches_bundle="
        f"{model_settings_hash == expected_model_settings_hash}"
    )

    if model_settings_hash != expected_model_settings_hash:
        raise ValueError(
            "Frozen model settings differ from bundle metadata."
        )

    model_settings = load_toml(model_settings_path)

    (
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    ) = configured_columns(model_settings)

    if len(predictor_features) != int(
        configuration["quality"][
            "expected_predictor_features"
        ]
    ):
        raise ValueError(
            "Model-settings predictor count is incorrect."
        )

    if predictor_features != metadata[
        "predictor_features"
    ]:
        raise ValueError(
            "Configured predictors differ from bundle metadata."
        )

    if categorical_features != metadata[
        "categorical_features"
    ]:
        raise ValueError(
            "Categorical features differ from bundle metadata."
        )

    if numeric_features != metadata["numeric_features"]:
        raise ValueError(
            "Numeric features differ from bundle metadata."
        )

    if target in predictor_features:
        raise ValueError(
            "Target is present in the predictor contract."
        )

    if target != metadata["target"]:
        raise ValueError(
            "Target metadata does not match model settings."
        )

    current_packages = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
    }

    print(f"current_packages={current_packages}")
    print(f"bundle_packages={metadata['packages']}")

    if current_packages != metadata["packages"]:
        raise ValueError(
            "Current package versions differ from the serialized "
            "bundle environment."
        )

    return (
        model_settings,
        metadata,
        manifest,
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    )


def validate_artifact_hashes(
    manifest: pd.DataFrame,
) -> dict[str, Path]:
    """Validate artifact paths and hashes before joblib.load."""

    model_root = (
        PROJECT_ROOT / "models" / "v1_evaluated_2025"
    ).resolve()
    artifact_paths: dict[str, Path] = {}
    hash_mismatches = 0

    for row in manifest.itertuples(index=False):
        artifact_path = resolve_project_path(
            row.artifact_path
        )

        if not artifact_path.is_relative_to(model_root):
            raise ValueError(
                "Model artifact is outside the frozen bundle "
                "directory."
            )

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Model artifact not found: {artifact_path}"
            )

        observed_hash = sha256_file(artifact_path)
        hash_matches = observed_hash == row.artifact_sha256

        print(
            f"{row.position}_artifact_sha256="
            f"{observed_hash}"
        )
        print(
            f"{row.position}_artifact_hash_matches="
            f"{hash_matches}"
        )

        if not hash_matches:
            hash_mismatches += 1

        artifact_paths[row.position] = artifact_path

    print(f"artifact_hash_mismatches={hash_mismatches}")

    if hash_mismatches:
        raise ValueError(
            "One or more model artifact hashes do not match."
        )

    if len(artifact_paths) != len(EXPECTED_POSITION_MODELS):
        raise ValueError(
            "Validated artifact count is incorrect."
        )

    return artifact_paths


def load_validated_artifacts(
    artifact_paths: dict[str, Path],
    predictor_features: list[str],
    position_models: dict[str, str],
) -> dict[str, Any]:
    """Deserialize only hash-validated local artifacts."""

    artifacts: dict[str, Any] = {}

    for position, artifact_path in artifact_paths.items():
        pipeline = joblib.load(artifact_path)

        observed_features = list(
            getattr(pipeline, "feature_names_in_", [])
        )

        if observed_features != predictor_features:
            raise ValueError(
                f"{position} artifact feature contract differs "
                "from bundle metadata."
            )

        if "model" not in pipeline.named_steps:
            raise ValueError(
                f"{position} pipeline has no model step."
            )

        algorithm = position_models[position]
        expected_class = EXPECTED_ESTIMATOR_CLASSES[
            algorithm
        ]
        observed_class = pipeline.named_steps[
            "model"
        ].__class__.__name__

        if observed_class != expected_class:
            raise ValueError(
                f"{position} estimator class is incorrect."
            )

        artifacts[position] = pipeline

        print(
            f"{position}_artifact_loaded=True, "
            f"algorithm={algorithm}, "
            f"estimator_class={observed_class}"
        )

    return artifacts


def available_input_columns(path: Path) -> list[str]:
    """Read only an input file's schema or header."""

    if path.suffix.lower() == ".parquet":
        return list(pq.read_schema(path).names)

    if path.suffix.lower() == ".csv":
        return list(pd.read_csv(path, nrows=0).columns)

    raise ValueError("Unsupported inference input format.")


def load_inference_input(
    run_specification: dict[str, Any],
    required_metadata: list[str],
    predictor_features: list[str],
    target: str,
) -> tuple[pd.DataFrame, bool, str]:
    """Load only metadata and predictors, never the target."""

    input_path = run_specification["input"]
    input_format = input_path.suffix.lower()
    source_columns = available_input_columns(input_path)
    source_contains_target = target in source_columns

    selected_columns = list(
        dict.fromkeys(
            required_metadata + predictor_features
        )
    )

    if target in selected_columns:
        raise ValueError(
            "Target entered the inference read contract."
        )

    missing_columns = sorted(
        set(selected_columns) - set(source_columns)
    )

    if missing_columns:
        raise ValueError(
            "Inference input is missing required columns: "
            + ", ".join(missing_columns)
        )

    split_column = run_specification[
        "data_split_column"
    ]
    split_value = run_specification["data_split_value"]

    if split_value is not None:
        if split_column not in source_columns:
            raise ValueError(
                "Requested split column is missing from input."
            )

    if input_format == ".parquet":
        filters = None

        if split_value is not None:
            filters = [
                (split_column, "==", split_value)
            ]

        dataframe = pd.read_parquet(
            input_path,
            engine="pyarrow",
            columns=selected_columns,
            filters=filters,
        )
    else:
        csv_columns = list(selected_columns)

        if (
            split_value is not None
            and split_column not in csv_columns
        ):
            csv_columns.append(split_column)

        dataframe = pd.read_csv(
            input_path,
            usecols=csv_columns,
        )

        if split_value is not None:
            dataframe = dataframe.loc[
                dataframe[split_column].eq(split_value)
            ].copy()

            if split_column not in selected_columns:
                dataframe = dataframe.drop(
                    columns=[split_column]
                )

    if target in dataframe.columns:
        raise ValueError(
            "Target was loaded into the inference dataframe."
        )

    dataframe = dataframe.reset_index(drop=True)
    dataframe["_inference_row_order"] = np.arange(
        len(dataframe),
        dtype="int64",
    )

    print(f"source_input_columns={len(source_columns):,}")
    print(f"selected_inference_columns={len(selected_columns):,}")
    print(
        "source_contains_target_column="
        f"{source_contains_target}"
    )
    print(
        "target_column_loaded="
        f"{target in dataframe.columns}"
    )

    return dataframe, source_contains_target, input_format


def validate_inference_input(
    dataframe: pd.DataFrame,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
    numeric_features: list[str],
    target: str,
) -> None:
    """Validate row grain, metadata, positions, and numeric values."""

    quality = configuration["quality"]
    key = list(quality["key_columns"])
    required_metadata = list(
        quality["required_metadata_columns"]
    )

    duplicate_keys = int(
        dataframe.duplicated(key).sum()
    )
    unavailable_keys = unavailable_rows(
        dataframe,
        key,
    )
    unavailable_metadata = unavailable_rows(
        dataframe,
        required_metadata,
    )

    observed_positions = set(
        dataframe["position"].dropna().unique()
    )
    supported_positions = set(
        quality["supported_positions"]
    )
    unsupported_positions = sorted(
        observed_positions - supported_positions
    )

    numeric_frame = dataframe[
        numeric_features
    ].apply(
        pd.to_numeric,
        errors="raise",
    )
    numeric_values = numeric_frame.to_numpy(
        dtype="float64",
        na_value=np.nan,
    )
    infinite_numeric_values = int(
        np.isinf(numeric_values).sum()
    )

    print(f"inference_rows={len(dataframe):,}")
    print(f"duplicate_inference_keys={duplicate_keys}")
    print(f"unavailable_inference_keys={unavailable_keys}")
    print(
        "unavailable_required_metadata_rows="
        f"{unavailable_metadata}"
    )
    print(f"observed_positions={sorted(observed_positions)}")
    print(f"unsupported_positions={unsupported_positions}")
    print(
        "infinite_numeric_feature_values="
        f"{infinite_numeric_values}"
    )

    if dataframe.empty:
        raise ValueError("Inference input contains no rows.")

    expected_rows = run_specification["expected_rows"]

    if (
        expected_rows is not None
        and len(dataframe) != expected_rows
    ):
        raise ValueError(
            "Smoke-test input row count is incorrect."
        )

    if duplicate_keys:
        raise ValueError(
            "Inference input contains duplicate keys."
        )

    if unavailable_keys:
        raise ValueError(
            "Inference input contains unavailable keys."
        )

    if unavailable_metadata:
        raise ValueError(
            "Inference input contains unavailable required metadata."
        )

    if unsupported_positions:
        raise ValueError(
            "Inference input contains unsupported positions."
        )

    if not observed_positions:
        raise ValueError(
            "Inference input contains no supported positions."
        )

    if (
        run_specification["mode"] == "smoke_test"
        and observed_positions != supported_positions
    ):
        raise ValueError(
            "Smoke test does not contain all expected positions."
        )

    if infinite_numeric_values:
        raise ValueError(
            "Inference input contains infinite numeric features."
        )

    if target in dataframe.columns:
        raise ValueError(
            "Target is present in the validated inference input."
        )


def generate_predictions(
    dataframe: pd.DataFrame,
    artifacts: dict[str, Any],
    configuration: dict[str, Any],
    categorical_features: list[str],
    numeric_features: list[str],
) -> pd.DataFrame:
    """Route rows by position and generate finite predictions."""

    inference = configuration["inference"]
    position_models = dict(configuration["position_models"])
    prediction_column = inference["prediction_column"]
    source_column = inference["source_model_column"]
    required_metadata = list(
        configuration["quality"][
            "required_metadata_columns"
        ]
    )

    predictions = pd.Series(
        np.nan,
        index=dataframe.index,
        dtype="float64",
    )
    prediction_sources = pd.Series(
        "",
        index=dataframe.index,
        dtype="object",
    )

    for position in configuration["quality"][
        "supported_positions"
    ]:
        position_rows = dataframe.loc[
            dataframe["position"].eq(position)
        ]

        if position_rows.empty:
            continue

        predictors = prepare_predictors(
            position_rows,
            categorical_features,
            numeric_features,
        )
        position_predictions = np.asarray(
            artifacts[position].predict(predictors),
            dtype="float64",
        )

        if not np.isfinite(position_predictions).all():
            raise ValueError(
                f"{position} generated non-finite predictions."
            )

        predictions.loc[position_rows.index] = (
            position_predictions
        )
        prediction_sources.loc[position_rows.index] = (
            position_models[position]
        )

        print(
            f"{position}_prediction_rows="
            f"{len(position_rows):,}, "
            f"algorithm={position_models[position]}"
        )

    output = dataframe[
        required_metadata + ["_inference_row_order"]
    ].copy()
    output[prediction_column] = predictions
    output[source_column] = prediction_sources
    output["model_bundle_version"] = inference[
        "bundle_version"
    ]
    output["inference_version"] = inference["version"]

    missing_predictions = int(
        output[prediction_column].isna().sum()
    )
    infinite_predictions = int(
        np.isinf(output[prediction_column]).sum()
    )
    expected_sources = output["position"].map(
        position_models
    )
    source_mismatches = int(
        output[source_column].ne(expected_sources).sum()
    )

    print(f"generated_prediction_rows={len(output):,}")
    print(
        "missing_generated_predictions="
        f"{missing_predictions}"
    )
    print(
        "infinite_generated_predictions="
        f"{infinite_predictions}"
    )
    print(
        "prediction_source_mismatches="
        f"{source_mismatches}"
    )

    if missing_predictions:
        raise ValueError(
            "Inference generated missing predictions."
        )

    if infinite_predictions:
        raise ValueError(
            "Inference generated infinite predictions."
        )

    if source_mismatches:
        raise ValueError(
            "Inference source-model assignments are incorrect."
        )

    output = (
        output.sort_values(
            "_inference_row_order",
            kind="stable",
        )
        .drop(columns=["_inference_row_order"])
        .reset_index(drop=True)
    )

    return output


def load_smoke_reference(
    reference_path: Path,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Load only keys and committed predictions, not outcomes."""

    smoke = configuration["smoke_test"]
    key = list(configuration["quality"]["key_columns"])
    prediction_column = smoke[
        "reference_prediction_column"
    ]
    source_column = smoke[
        "reference_source_model_column"
    ]

    selected_columns = list(
        dict.fromkeys(
            key
            + [
                "position",
                prediction_column,
                source_column,
            ]
        )
    )

    reference = pd.read_csv(
        reference_path,
        usecols=selected_columns,
    )

    duplicate_keys = int(reference.duplicated(key).sum())
    unavailable_keys = unavailable_rows(reference, key)
    missing_predictions = int(
        reference[prediction_column].isna().sum()
    )

    print(f"smoke_reference_rows={len(reference):,}")
    print(
        "smoke_reference_duplicate_keys="
        f"{duplicate_keys}"
    )
    print(
        "smoke_reference_unavailable_keys="
        f"{unavailable_keys}"
    )
    print(
        "smoke_reference_missing_predictions="
        f"{missing_predictions}"
    )
    print("smoke_reference_target_loaded=False")

    if len(reference) != int(smoke["expected_rows"]):
        raise ValueError(
            "Smoke reference row count is incorrect."
        )

    if duplicate_keys or unavailable_keys:
        raise ValueError(
            "Smoke reference contains invalid keys."
        )

    if missing_predictions:
        raise ValueError(
            "Smoke reference contains missing predictions."
        )

    expected_sources = reference["position"].map(
        configuration["position_models"]
    )

    if reference[source_column].ne(expected_sources).any():
        raise ValueError(
            "Smoke reference source-model mapping is incorrect."
        )

    return reference


def build_smoke_verification(
    predictions: pd.DataFrame,
    reference: pd.DataFrame,
    configuration: dict[str, Any],
) -> pd.DataFrame:
    """Compare target-free inference with committed predictions."""

    quality = configuration["quality"]
    smoke = configuration["smoke_test"]
    inference = configuration["inference"]
    key = list(quality["key_columns"])
    join_columns = key + ["position"]
    prediction_column = inference["prediction_column"]
    source_column = inference["source_model_column"]
    reference_prediction = smoke[
        "reference_prediction_column"
    ]
    reference_source = smoke[
        "reference_source_model_column"
    ]
    tolerance = float(
        quality["prediction_absolute_tolerance"]
    )

    joined = predictions.merge(
        reference,
        on=join_columns,
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    unmatched_rows = int(joined["_merge"].ne("both").sum())

    print(f"smoke_reference_unmatched_rows={unmatched_rows}")

    if unmatched_rows:
        raise ValueError(
            "Inference and reference keys do not reconcile."
        )

    joined["absolute_difference"] = (
        joined[prediction_column]
        - joined[reference_prediction]
    ).abs()

    rows: list[dict[str, Any]] = []

    for position in quality["supported_positions"]:
        group = joined.loc[
            joined["position"].eq(position)
        ]

        mismatch_rows = int(
            group["absolute_difference"].gt(
                tolerance
            ).sum()
        )
        source_mismatch_rows = int(
            group[source_column].ne(
                group[reference_source]
            ).sum()
        )

        rows.append(
            {
                "scope": "position",
                "position": position,
                "algorithm": configuration[
                    "position_models"
                ][position],
                "row_count": len(group),
                "prediction_mismatch_rows": (
                    mismatch_rows
                ),
                "source_model_mismatch_rows": (
                    source_mismatch_rows
                ),
                "maximum_absolute_difference": float(
                    group["absolute_difference"].max()
                ),
                "mean_absolute_difference": float(
                    group["absolute_difference"].mean()
                ),
                "verification_status": (
                    "PASS"
                    if (
                        mismatch_rows == 0
                        and source_mismatch_rows == 0
                    )
                    else "FAIL"
                ),
            }
        )

    overall_mismatches = int(
        joined["absolute_difference"].gt(
            tolerance
        ).sum()
    )
    overall_source_mismatches = int(
        joined[source_column].ne(
            joined[reference_source]
        ).sum()
    )

    rows.append(
        {
            "scope": "overall",
            "position": "ALL",
            "algorithm": "position_champion",
            "row_count": len(joined),
            "prediction_mismatch_rows": (
                overall_mismatches
            ),
            "source_model_mismatch_rows": (
                overall_source_mismatches
            ),
            "maximum_absolute_difference": float(
                joined["absolute_difference"].max()
            ),
            "mean_absolute_difference": float(
                joined["absolute_difference"].mean()
            ),
            "verification_status": (
                "PASS"
                if (
                    overall_mismatches == 0
                    and overall_source_mismatches == 0
                )
                else "FAIL"
            ),
        }
    )

    verification = pd.DataFrame(rows)

    if len(verification) != 5:
        raise ValueError(
            "Smoke verification row count is incorrect."
        )

    if (
        verification["prediction_mismatch_rows"].sum()
        or verification[
            "source_model_mismatch_rows"
        ].sum()
    ):
        raise ValueError(
            "Smoke-test inference does not reproduce the "
            "committed predictions."
        )

    if set(verification["verification_status"]) != {
        "PASS"
    }:
        raise ValueError(
            "Smoke-test verification contains failed rows."
        )

    return verification


def atomic_write_csv(
    dataframe: pd.DataFrame,
    path: Path,
) -> None:
    """Write a CSV through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )

    try:
        dataframe.to_csv(
            temporary_path,
            index=False,
            lineterminator="\n",
        )
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_table(
    dataframe: pd.DataFrame,
    path: Path,
) -> None:
    """Write a Parquet or CSV output atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(
        f".{path.name}.{uuid.uuid4().hex}.tmp"
    )

    try:
        if path.suffix.lower() == ".parquet":
            dataframe.to_parquet(
                temporary_path,
                engine="pyarrow",
                index=False,
            )
        elif path.suffix.lower() == ".csv":
            dataframe.to_csv(
                temporary_path,
                index=False,
                lineterminator="\n",
            )
        else:
            raise ValueError(
                "Unsupported prediction output format."
            )

        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def read_prediction_output(path: Path) -> pd.DataFrame:
    """Reopen a written prediction file."""

    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(
            path,
            engine="pyarrow",
        )

    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)

    raise ValueError("Unsupported prediction output format.")


def build_run_manifest(
    run_timestamp_utc: str,
    current_commit: str,
    full_commits: dict[str, str],
    configuration_path: Path,
    configuration: dict[str, Any],
    run_specification: dict[str, Any],
    input_format: str,
    input_hash: str,
    source_contains_target: bool,
    predictions: pd.DataFrame,
    artifact_manifest: pd.DataFrame,
    smoke_verification: pd.DataFrame | None,
    output_hashes: dict[str, str],
) -> pd.DataFrame:
    """Build a key-value inference run manifest."""

    inference = configuration["inference"]
    position_counts = {
        str(position): int(count)
        for position, count
        in predictions.groupby("position").size().items()
    }
    artifact_hashes = {
        row.position: row.artifact_sha256
        for row in artifact_manifest.itertuples(
            index=False
        )
    }

    if smoke_verification is None:
        reference_performed = False
        reference_mismatches: str | int = "NOT_APPLICABLE"
        maximum_difference: str | float = "NOT_APPLICABLE"
        sample_path = "NOT_APPLICABLE"
        sample_hash = "NOT_APPLICABLE"
        verification_path = "NOT_APPLICABLE"
        verification_hash = "NOT_APPLICABLE"
    else:
        reference_performed = True
        overall = smoke_verification.loc[
            smoke_verification["scope"].eq("overall")
        ].iloc[0]
        reference_mismatches = int(
            overall["prediction_mismatch_rows"]
        )
        maximum_difference = float(
            overall["maximum_absolute_difference"]
        )
        sample_path = display_path(
            run_specification["sample"]
        )
        sample_hash = output_hashes["sample"]
        verification_path = display_path(
            run_specification["verification"]
        )
        verification_hash = output_hashes[
            "verification"
        ]

    rows = [
        ("run_timestamp_utc", run_timestamp_utc),
        ("run_mode", run_specification["mode"]),
        ("inference_commit", current_commit),
        (
            "bundle_protocol_commit",
            full_commits["bundle_protocol_commit"],
        ),
        (
            "bundle_evidence_commit",
            full_commits["bundle_evidence_commit"],
        ),
        (
            "inference_configuration_sha256",
            sha256_file(configuration_path),
        ),
        (
            "bundle_manifest_sha256",
            configuration["lineage"][
                "bundle_manifest_sha256"
            ],
        ),
        (
            "bundle_verification_sha256",
            configuration["lineage"][
                "bundle_verification_sha256"
            ],
        ),
        (
            "bundle_metadata_sha256",
            configuration["lineage"][
                "bundle_metadata_sha256"
            ],
        ),
        ("inference_version", inference["version"]),
        ("model_bundle_version", inference["bundle_version"]),
        ("input_path", display_path(run_specification["input"])),
        ("input_sha256", input_hash),
        ("input_format", input_format),
        (
            "data_split_filter",
            (
                run_specification["data_split_value"]
                if run_specification["data_split_value"]
                is not None
                else "NONE"
            ),
        ),
        ("input_rows", len(predictions)),
        ("output_rows", len(predictions)),
        (
            "position_row_counts",
            json.dumps(
                position_counts,
                sort_keys=True,
            ),
        ),
        (
            "position_models",
            json.dumps(
                dict(configuration["position_models"]),
                sort_keys=True,
            ),
        ),
        (
            "artifact_sha256",
            json.dumps(
                artifact_hashes,
                sort_keys=True,
            ),
        ),
        (
            "predictor_count",
            int(
                configuration["quality"][
                    "expected_predictor_features"
                ]
            ),
        ),
        (
            "source_contains_target_column",
            str(source_contains_target).lower(),
        ),
        ("target_column_loaded", "false"),
        ("model_fitting_performed", "false"),
        ("model_reselection_performed", "false"),
        (
            "reference_verification_performed",
            str(reference_performed).lower(),
        ),
        (
            "reference_prediction_mismatch_rows",
            reference_mismatches,
        ),
        (
            "maximum_reference_prediction_difference",
            maximum_difference,
        ),
        (
            "predictions_path",
            display_path(run_specification["output"]),
        ),
        ("predictions_sha256", output_hashes["predictions"]),
        ("sample_path", sample_path),
        ("sample_sha256", sample_hash),
        ("verification_path", verification_path),
        ("verification_sha256", verification_hash),
        ("prediction_column", inference["prediction_column"]),
        ("source_model_column", inference["source_model_column"]),
    ]

    return pd.DataFrame(
        rows,
        columns=["manifest_key", "manifest_value"],
    )


def write_inference_outputs(
    predictions: pd.DataFrame,
    smoke_verification: pd.DataFrame | None,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
    configuration_path: Path,
    current_commit: str,
    full_commits: dict[str, str],
    input_format: str,
    input_hash: str,
    source_contains_target: bool,
    artifact_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Write predictions and compact inference evidence."""

    atomic_write_table(
        predictions,
        run_specification["output"],
    )

    output_hashes = {
        "predictions": sha256_file(
            run_specification["output"]
        )
    }

    if smoke_verification is not None:
        sample = (
            predictions.sort_values(
                [
                    "season",
                    "week",
                    "position",
                    "player_id",
                ],
                kind="stable",
            )
            .head(run_specification["sample_rows"])
            .reset_index(drop=True)
        )

        atomic_write_csv(
            sample,
            run_specification["sample"],
        )
        atomic_write_csv(
            smoke_verification,
            run_specification["verification"],
        )

        output_hashes["sample"] = sha256_file(
            run_specification["sample"]
        )
        output_hashes["verification"] = sha256_file(
            run_specification["verification"]
        )

        print(
            f"Wrote {display_path(run_specification['sample'])}: "
            f"{len(sample):,} rows"
        )
        print(
            "Wrote "
            f"{display_path(run_specification['verification'])}: "
            f"{len(smoke_verification):,} rows"
        )

    run_timestamp_utc = datetime.now(
        timezone.utc
    ).isoformat()

    manifest = build_run_manifest(
        run_timestamp_utc,
        current_commit,
        full_commits,
        configuration_path,
        configuration,
        run_specification,
        input_format,
        input_hash,
        source_contains_target,
        predictions,
        artifact_manifest,
        smoke_verification,
        output_hashes,
    )

    atomic_write_csv(
        manifest,
        run_specification["manifest"],
    )

    print(
        f"Wrote {display_path(run_specification['output'])}: "
        f"{len(predictions):,} rows"
    )
    print(
        f"Wrote {display_path(run_specification['manifest'])}: "
        f"{len(manifest):,} rows"
    )

    return manifest


def reopen_and_validate_outputs(
    predictions: pd.DataFrame,
    smoke_verification: pd.DataFrame | None,
    run_manifest: pd.DataFrame,
    run_specification: dict[str, Any],
    configuration: dict[str, Any],
    reference: pd.DataFrame | None,
    target: str,
) -> None:
    """Reopen written inference artifacts and validate them."""

    written_predictions = read_prediction_output(
        run_specification["output"]
    )
    written_manifest = pd.read_csv(
        run_specification["manifest"]
    )

    prediction_column = configuration["inference"][
        "prediction_column"
    ]
    source_column = configuration["inference"][
        "source_model_column"
    ]
    key = list(configuration["quality"]["key_columns"])

    duplicate_keys = int(
        written_predictions.duplicated(key).sum()
    )
    missing_predictions = int(
        written_predictions[prediction_column].isna().sum()
    )
    infinite_predictions = int(
        np.isinf(
            written_predictions[prediction_column]
        ).sum()
    )
    source_mismatches = int(
        written_predictions[source_column].ne(
            written_predictions["position"].map(
                configuration["position_models"]
            )
        ).sum()
    )

    print(
        "written_prediction_rows="
        f"{len(written_predictions):,}"
    )
    print(
        "written_prediction_duplicate_keys="
        f"{duplicate_keys}"
    )
    print(
        "written_missing_predictions="
        f"{missing_predictions}"
    )
    print(
        "written_infinite_predictions="
        f"{infinite_predictions}"
    )
    print(
        "written_source_model_mismatches="
        f"{source_mismatches}"
    )
    print(
        "written_target_column_present="
        f"{target in written_predictions.columns}"
    )
    print(f"written_manifest_rows={len(written_manifest):,}")

    if len(written_predictions) != len(predictions):
        raise ValueError(
            "Written prediction row count is incorrect."
        )

    if duplicate_keys:
        raise ValueError(
            "Written predictions contain duplicate keys."
        )

    if missing_predictions or infinite_predictions:
        raise ValueError(
            "Written predictions contain invalid values."
        )

    if source_mismatches:
        raise ValueError(
            "Written prediction sources are incorrect."
        )

    if target in written_predictions.columns:
        raise ValueError(
            "Written predictions contain the target."
        )

    if written_manifest[
        "manifest_key"
    ].duplicated().any():
        raise ValueError(
            "Written run manifest contains duplicate keys."
        )

    if set(written_manifest["manifest_key"]) != set(
        run_manifest["manifest_key"]
    ):
        raise ValueError(
            "Written run-manifest keys are incorrect."
        )

    manifest_values = written_manifest.set_index(
        "manifest_key"
    )["manifest_value"]

    if (
        manifest_values["predictions_sha256"]
        != sha256_file(run_specification["output"])
    ):
        raise ValueError(
            "Written prediction hash does not reconcile."
        )

    if manifest_values["target_column_loaded"] != "false":
        raise ValueError(
            "Run manifest does not confirm target exclusion."
        )

    if manifest_values["model_fitting_performed"] != "false":
        raise ValueError(
            "Run manifest incorrectly records model fitting."
        )

    if (
        manifest_values["model_reselection_performed"]
        != "false"
    ):
        raise ValueError(
            "Run manifest incorrectly records model reselection."
        )

    if smoke_verification is not None:
        written_sample = pd.read_csv(
            run_specification["sample"]
        )
        written_verification = pd.read_csv(
            run_specification["verification"]
        )

        if len(written_sample) != run_specification[
            "sample_rows"
        ]:
            raise ValueError(
                "Written smoke sample row count is incorrect."
            )

        if target in written_sample.columns:
            raise ValueError(
                "Written smoke sample contains the target."
            )

        if len(written_verification) != 5:
            raise ValueError(
                "Written smoke verification row count is incorrect."
            )

        if set(
            written_verification["verification_status"]
        ) != {"PASS"}:
            raise ValueError(
                "Written smoke verification contains failed rows."
            )

        reopened_verification = build_smoke_verification(
            written_predictions,
            reference,
            configuration,
        )

        if (
            reopened_verification[
                "prediction_mismatch_rows"
            ].sum()
            or reopened_verification[
                "source_model_mismatch_rows"
            ].sum()
        ):
            raise ValueError(
                "Reopened smoke predictions do not reconcile."
            )

        print(
            "written_smoke_sample_rows="
            f"{len(written_sample):,}"
        )
        print(
            "written_smoke_verification_rows="
            f"{len(written_verification):,}"
        )
        print(
            "written_reference_prediction_mismatches=0"
        )


def main() -> None:
    """Run target-free Version 1 bundle inference."""

    arguments = parse_arguments()
    configuration_path = Path(arguments.config).resolve()
    configuration = load_toml(configuration_path)

    validate_inference_configuration(
        configuration,
        arguments.confirm_inference,
    )

    bundle_paths = resolve_bundle_paths(configuration)
    run_specification = build_run_specification(
        arguments,
        configuration,
    )

    print_section("NFL FANTASY VERSION 1 BUNDLE INFERENCE")

    print(f"Configuration: {configuration_path}")
    print(
        "Inference version: "
        f"{configuration['inference']['version']}"
    )
    print(
        "Model bundle: "
        f"{configuration['inference']['bundle_version']}"
    )
    print(f"Run mode: {run_specification['mode']}")
    print(
        f"Input: {display_path(run_specification['input'])}"
    )
    print(
        f"Output: {display_path(run_specification['output'])}"
    )
    print("Target loading permitted: False")
    print("Model fitting permitted: False")
    print("Model reselection permitted: False")

    print_section("INFERENCE EXECUTION GUARDS")

    validate_run_paths(
        run_specification,
        configuration,
    )
    current_commit, full_commits = validate_git_state(
        configuration
    )

    print_section("BUNDLE EVIDENCE AND HASH VALIDATION")

    observed_hashes = validate_frozen_hashes(
        configuration,
        bundle_paths,
        run_specification,
    )

    (
        model_settings,
        metadata,
        artifact_manifest,
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    ) = validate_bundle_evidence(
        configuration,
        bundle_paths,
        full_commits,
    )

    artifact_paths = validate_artifact_hashes(
        artifact_manifest
    )

    print_section("LOADING HASH-VALIDATED LOCAL MODELS")

    artifacts = load_validated_artifacts(
        artifact_paths,
        predictor_features,
        dict(configuration["position_models"]),
    )

    print_section("LOADING TARGET-FREE INFERENCE INPUT")

    dataframe, source_contains_target, input_format = (
        load_inference_input(
            run_specification,
            list(
                configuration["quality"][
                    "required_metadata_columns"
                ]
            ),
            predictor_features,
            target,
        )
    )

    validate_inference_input(
        dataframe,
        run_specification,
        configuration,
        numeric_features,
        target,
    )

    print_section("GENERATING VERSION 1 PROJECTIONS")

    predictions = generate_predictions(
        dataframe,
        artifacts,
        configuration,
        categorical_features,
        numeric_features,
    )

    reference = None
    smoke_verification = None

    if run_specification["mode"] == "smoke_test":
        print_section(
            "RECONCILING TARGET-FREE SMOKE PREDICTIONS"
        )

        reference = load_smoke_reference(
            run_specification["reference"],
            configuration,
        )
        smoke_verification = build_smoke_verification(
            predictions,
            reference,
            configuration,
        )

        print()
        print(
            smoke_verification.to_string(
                index=False
            )
        )

    print_section("WRITING INFERENCE OUTPUTS")

    input_hash = sha256_file(run_specification["input"])
    run_manifest = write_inference_outputs(
        predictions,
        smoke_verification,
        run_specification,
        configuration,
        configuration_path,
        current_commit,
        full_commits,
        input_format,
        input_hash,
        source_contains_target,
        artifact_manifest,
    )

    print_section("REOPENING WRITTEN INFERENCE OUTPUTS")

    reopen_and_validate_outputs(
        predictions,
        smoke_verification,
        run_manifest,
        run_specification,
        configuration,
        reference,
        target,
    )

    print_section("VERSION 1 BUNDLE INFERENCE COMPLETE")

    print("bundle_hash_validation=PASS")
    print("artifact_hash_validation=PASS")
    print("target_free_input_contract=PASS")
    print("prediction_completeness=PASS")

    if smoke_verification is not None:
        print("smoke_reference_reconciliation=PASS")
    else:
        print("smoke_reference_reconciliation=NOT_APPLICABLE")

    print("model_fitting_performed=False")
    print("model_reselection_performed=False")
    print("inference_status=PASS")


if __name__ == "__main__":
    main()