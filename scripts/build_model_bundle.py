"""Build a reproducible bundle of the frozen Version 1 position models."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn

from train_models import (
    build_candidate_pipeline,
    configured_columns,
    prepare_predictors,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "config" / "model_bundle_settings.toml"
)

EXPECTED_POSITION_MODELS = {
    "QB": "hist_gradient_boosting",
    "RB": "random_forest",
    "WR": "ridge",
    "TE": "ridge",
}


def parse_arguments() -> argparse.Namespace:
    """Parse the explicit bundle-build confirmation."""

    parser = argparse.ArgumentParser(
        description=(
            "Refit the frozen Version 1 position models, reproduce "
            "the committed 2025 predictions, and save local artifacts."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the model-bundle settings TOML file.",
    )
    parser.add_argument(
        "--confirm-build",
        required=True,
        help=(
            "Required confirmation token from the bundle "
            "configuration."
        ),
    )
    return parser.parse_args()


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


def load_toml(path: Path) -> dict[str, Any]:
    """Load a UTF-8 TOML file."""

    if not path.exists():
        raise FileNotFoundError(f"Configuration not found: {path}")

    with path.open("rb") as file:
        return tomllib.load(file)


def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 digest without loading the file at once."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def unavailable_key_rows(
    dataframe: pd.DataFrame,
    key_columns: list[str],
) -> int:
    """Count rows with null or blank required key values."""

    unavailable = pd.Series(
        False,
        index=dataframe.index,
        dtype="bool",
    )

    for column in key_columns:
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


def validate_bundle_configuration(
    configuration: dict[str, Any],
    confirmation_token: str,
) -> None:
    """Validate the bundle contract before accessing model data."""

    required_sections = {
        "bundle",
        "lineage",
        "inputs",
        "position_models",
        "quality",
        "output",
    }

    missing_sections = sorted(
        required_sections - set(configuration)
    )

    if missing_sections:
        raise ValueError(
            "Bundle configuration is missing sections: "
            + ", ".join(missing_sections)
        )

    bundle = configuration["bundle"]
    lineage = configuration["lineage"]
    inputs = configuration["inputs"]
    position_models = dict(configuration["position_models"])
    quality = configuration["quality"]
    output = configuration["output"]

    if confirmation_token != bundle["confirmation_token"]:
        raise ValueError("Incorrect bundle-build confirmation token.")

    if bundle["version"] != "v1_evaluated_2025":
        raise ValueError("Unexpected model-bundle version.")

    if bundle["bundle_type"] != "evaluation_reproduction":
        raise ValueError("Unexpected model-bundle type.")

    if list(bundle["fit_splits"]) != [
        "training",
        "validation",
    ]:
        raise ValueError(
            "The evaluated bundle must fit on training and "
            "validation only."
        )

    if bundle["verification_split"] != "test":
        raise ValueError(
            "The evaluated bundle must verify against the test split."
        )

    if bundle["allow_model_reselection"]:
        raise ValueError(
            "Model reselection must remain disabled."
        )

    required_true_flags = [
        "refit_preprocessing",
        "require_clean_worktree",
        "fail_if_output_exists",
        "reload_artifacts_after_write",
    ]

    for flag in required_true_flags:
        if not bundle[flag]:
            raise ValueError(
                f"Required bundle safeguard is disabled: {flag}"
            )

    if position_models != EXPECTED_POSITION_MODELS:
        raise ValueError(
            "Configured position models do not match the frozen "
            "Version 1 mapping."
        )

    expected_lineage_keys = {
        "selection_commit",
        "protocol_commit",
        "evidence_commit",
        "model_settings_sha256",
        "model_data_sha256",
        "final_predictions_sha256",
        "final_run_manifest_sha256",
    }

    if set(lineage) != expected_lineage_keys:
        raise ValueError(
            "Bundle lineage keys do not match the required contract."
        )

    for hash_key in [
        "model_settings_sha256",
        "model_data_sha256",
        "final_predictions_sha256",
        "final_run_manifest_sha256",
    ]:
        configured_hash = str(lineage[hash_key]).lower()

        if (
            len(configured_hash) != 64
            or any(
                character not in "0123456789abcdef"
                for character in configured_hash
            )
        ):
            raise ValueError(
                f"Invalid configured SHA-256 value: {hash_key}"
            )

    expected_input_keys = {
        "model_settings_path",
        "model_data_path",
        "final_predictions_path",
        "final_run_manifest_path",
    }

    if set(inputs) != expected_input_keys:
        raise ValueError(
            "Bundle input keys do not match the required contract."
        )

    expected_output_keys = {
        "artifact_directory",
        "metadata_path",
        "manifest_path",
        "verification_path",
        "artifact_files",
    }

    if set(output) != expected_output_keys:
        raise ValueError(
            "Bundle output keys do not match the required contract."
        )

    artifact_files = dict(output["artifact_files"])

    if set(artifact_files) != set(EXPECTED_POSITION_MODELS):
        raise ValueError(
            "Artifact filenames do not cover all frozen positions."
        )

    if len(set(artifact_files.values())) != len(artifact_files):
        raise ValueError("Artifact filenames must be unique.")

    for filename in artifact_files.values():
        artifact_name = Path(filename)

        if (
            artifact_name.name != filename
            or artifact_name.suffix.lower() != ".joblib"
        ):
            raise ValueError(
                f"Invalid artifact filename: {filename}"
            )

    if list(quality["expected_positions"]) != [
        "QB",
        "RB",
        "WR",
        "TE",
    ]:
        raise ValueError("Unexpected configured position order.")

    if int(quality["expected_fit_rows"]) != 39656:
        raise ValueError("Unexpected development row contract.")

    if int(quality["expected_verification_rows"]) != 6037:
        raise ValueError("Unexpected verification row contract.")

    if int(quality["expected_predictor_features"]) != 102:
        raise ValueError("Unexpected predictor-count contract.")

    if int(quality["expected_artifact_files"]) != 4:
        raise ValueError("Unexpected artifact-count contract.")

    if int(quality["expected_verification_summary_rows"]) != 5:
        raise ValueError(
            "Unexpected verification-summary row contract."
        )

    if float(quality["prediction_absolute_tolerance"]) <= 0:
        raise ValueError(
            "Prediction tolerance must be greater than zero."
        )

    for flag in [
        "require_zero_duplicate_keys",
        "require_zero_missing_predictions",
        "require_exact_source_model_assignments",
    ]:
        if not quality[flag]:
            raise ValueError(
                f"Required quality control is disabled: {flag}"
            )


def run_git_command(*arguments: str) -> str:
    """Run a read-only Git command in the project repository."""

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
    """Require clean Git state and all frozen commits in history."""

    lineage = configuration["lineage"]
    current_commit = run_git_command("rev-parse", "HEAD")
    worktree_status = run_git_command("status", "--porcelain")

    full_commits: dict[str, str] = {}

    for commit_name in [
        "selection_commit",
        "protocol_commit",
        "evidence_commit",
    ]:
        configured_commit = str(lineage[commit_name])
        full_commit = run_git_command(
            "rev-parse",
            configured_commit,
        )

        ancestor_check = subprocess.run(
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

        is_ancestor = ancestor_check.returncode == 0

        print(f"{commit_name}={full_commit}")
        print(f"{commit_name}_is_ancestor={is_ancestor}")

        if not is_ancestor:
            raise ValueError(
                f"{commit_name} is not an ancestor of HEAD."
            )

        full_commits[commit_name] = full_commit

    print(f"current_commit={current_commit}")
    print(f"worktree_clean={worktree_status == ''}")

    if worktree_status:
        raise ValueError(
            "Commit the model-bundle protocol before building "
            "artifacts."
        )

    return current_commit, full_commits


def resolve_input_paths(
    configuration: dict[str, Any],
) -> dict[str, Path]:
    """Resolve all configured bundle inputs."""

    return {
        name: resolve_project_path(path_value)
        for name, path_value
        in configuration["inputs"].items()
    }


def resolve_output_paths(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """Resolve and validate all configured bundle outputs."""

    output = configuration["output"]
    artifact_directory = resolve_project_path(
        output["artifact_directory"]
    )
    metadata_path = resolve_project_path(output["metadata_path"])
    manifest_path = resolve_project_path(output["manifest_path"])
    verification_path = resolve_project_path(
        output["verification_path"]
    )

    models_root = (PROJECT_ROOT / "models").resolve()
    results_root = (PROJECT_ROOT / "results" / "tables").resolve()

    if not artifact_directory.is_relative_to(models_root):
        raise ValueError(
            "Artifact directory must remain under models/."
        )

    if metadata_path.parent != artifact_directory:
        raise ValueError(
            "Bundle metadata must be inside the artifact directory."
        )

    if not manifest_path.is_relative_to(results_root):
        raise ValueError(
            "Bundle manifest must remain under results/tables/."
        )

    if not verification_path.is_relative_to(results_root):
        raise ValueError(
            "Bundle verification must remain under results/tables/."
        )

    artifact_paths = {
        position: artifact_directory / filename
        for position, filename
        in output["artifact_files"].items()
    }

    return {
        "artifact_directory": artifact_directory,
        "metadata": metadata_path,
        "manifest": manifest_path,
        "verification": verification_path,
        "artifacts": artifact_paths,
    }


def ensure_outputs_do_not_exist(
    output_paths: dict[str, Any],
) -> None:
    """Prevent accidental replacement of model-bundle evidence."""

    artifact_directory = output_paths["artifact_directory"]
    configured_paths = [
        artifact_directory,
        output_paths["metadata"],
        output_paths["manifest"],
        output_paths["verification"],
        *output_paths["artifacts"].values(),
    ]

    existing_outputs = sorted(
        {
            str(path.relative_to(PROJECT_ROOT))
            for path in configured_paths
            if path.exists()
        }
    )

    artifact_parent = artifact_directory.parent
    stale_temp_directories = []

    if artifact_parent.exists():
        stale_temp_directories = sorted(
            str(path.relative_to(PROJECT_ROOT))
            for path in artifact_parent.glob(
                f".{artifact_directory.name}.tmp-*"
            )
            if path.exists()
        )

    print(f"existing_bundle_outputs={existing_outputs}")
    print(
        "stale_bundle_temp_directories="
        f"{stale_temp_directories}"
    )

    if existing_outputs:
        raise FileExistsError(
            "Model-bundle outputs already exist. Existing Version 1 "
            "artifacts will not be overwritten."
        )

    if stale_temp_directories:
        raise FileExistsError(
            "A stale temporary bundle directory exists. Review it "
            "before attempting another build."
        )


def validate_input_hashes(
    configuration: dict[str, Any],
    input_paths: dict[str, Path],
) -> dict[str, str]:
    """Reconcile all bundle inputs with frozen SHA-256 values."""

    lineage = configuration["lineage"]
    hash_contract = {
        "model_settings_path": "model_settings_sha256",
        "model_data_path": "model_data_sha256",
        "final_predictions_path": "final_predictions_sha256",
        "final_run_manifest_path": (
            "final_run_manifest_sha256"
        ),
    }

    observed_hashes: dict[str, str] = {}

    for input_name, hash_name in hash_contract.items():
        path = input_paths[input_name]

        if not path.exists():
            raise FileNotFoundError(
                f"Required bundle input not found: {path}"
            )

        observed_hash = sha256_file(path)
        expected_hash = str(lineage[hash_name]).lower()
        hash_matches = observed_hash == expected_hash

        print(f"{input_name}_sha256={observed_hash}")
        print(f"{input_name}_hash_matches={hash_matches}")

        if not hash_matches:
            raise ValueError(
                f"Frozen input hash mismatch: {input_name}"
            )

        observed_hashes[input_name] = observed_hash

    return observed_hashes


def validate_model_settings(
    model_settings: dict[str, Any],
    bundle_configuration: dict[str, Any],
) -> None:
    """Require agreement with the frozen final-evaluation settings."""

    final = model_settings["final_evaluation"]
    bundle = bundle_configuration["bundle"]

    if final["selected_model"] != "position_champion":
        raise ValueError(
            "Frozen model settings do not select position_champion."
        )

    if list(final["fit_splits"]) != list(bundle["fit_splits"]):
        raise ValueError(
            "Bundle fit splits differ from final-evaluation splits."
        )

    if final["evaluation_split"] != bundle[
        "verification_split"
    ]:
        raise ValueError(
            "Bundle verification split differs from the frozen test "
            "split."
        )

    if dict(final["position_models"]) != dict(
        bundle_configuration["position_models"]
    ):
        raise ValueError(
            "Bundle position mapping differs from final evaluation."
        )

    (
        categorical_features,
        numeric_features,
        predictor_features,
        _,
    ) = configured_columns(model_settings)

    expected_predictors = int(
        bundle_configuration["quality"][
            "expected_predictor_features"
        ]
    )

    if len(predictor_features) != expected_predictors:
        raise ValueError(
            "Frozen predictor count does not match bundle contract."
        )

    if len(categorical_features) + len(
        numeric_features
    ) != expected_predictors:
        raise ValueError(
            "Categorical and numeric predictor counts are invalid."
        )


def validate_final_run_manifest(
    manifest_path: Path,
    configuration: dict[str, Any],
    full_commits: dict[str, str],
) -> pd.Series:
    """Validate the committed final-test run manifest."""

    manifest = pd.read_csv(manifest_path)

    duplicate_keys = int(
        manifest["manifest_key"].duplicated().sum()
    )
    missing_keys = int(
        manifest["manifest_key"].isna().sum()
    )
    missing_values = int(
        manifest["manifest_value"].isna().sum()
    )

    print(f"final_manifest_rows={len(manifest):,}")
    print(f"final_manifest_duplicate_keys={duplicate_keys}")
    print(f"final_manifest_missing_keys={missing_keys}")
    print(f"final_manifest_missing_values={missing_values}")

    if duplicate_keys or missing_keys or missing_values:
        raise ValueError(
            "Final-test run manifest contains invalid rows."
        )

    values = manifest.set_index("manifest_key")[
        "manifest_value"
    ]

    required_keys = {
        "protocol_commit",
        "selection_commit",
        "configuration_sha256",
        "input_parquet_sha256",
        "fit_splits",
        "evaluation_split",
        "selected_model",
        "position_models",
        "development_rows",
        "test_rows",
        "test_evaluation_completed_once",
    }

    missing_required_keys = sorted(
        required_keys - set(values.index)
    )

    if missing_required_keys:
        raise ValueError(
            "Final-test manifest is missing keys: "
            + ", ".join(missing_required_keys)
        )

    if values["protocol_commit"] != full_commits[
        "protocol_commit"
    ]:
        raise ValueError(
            "Final-test manifest protocol commit mismatch."
        )

    if values["selection_commit"] != full_commits[
        "selection_commit"
    ]:
        raise ValueError(
            "Final-test manifest selection commit mismatch."
        )

    lineage = configuration["lineage"]

    if values["configuration_sha256"] != lineage[
        "model_settings_sha256"
    ]:
        raise ValueError(
            "Final-test manifest configuration hash mismatch."
        )

    if values["input_parquet_sha256"] != lineage[
        "model_data_sha256"
    ]:
        raise ValueError(
            "Final-test manifest data hash mismatch."
        )

    if values["evaluation_split"] != configuration[
        "bundle"
    ]["verification_split"]:
        raise ValueError(
            "Final-test manifest split mismatch."
        )

    if values["selected_model"] != "position_champion":
        raise ValueError(
            "Final-test manifest selected-model mismatch."
        )

    observed_position_models = json.loads(
        values["position_models"]
    )

    if observed_position_models != dict(
        configuration["position_models"]
    ):
        raise ValueError(
            "Final-test manifest position mapping mismatch."
        )

    if int(values["development_rows"]) != int(
        configuration["quality"]["expected_fit_rows"]
    ):
        raise ValueError(
            "Final-test manifest development row mismatch."
        )

    if int(values["test_rows"]) != int(
        configuration["quality"]["expected_verification_rows"]
    ):
        raise ValueError(
            "Final-test manifest test row mismatch."
        )

    if (
        str(values["test_evaluation_completed_once"]).lower()
        != "true"
    ):
        raise ValueError(
            "Final-test manifest does not record completed evaluation."
        )

    return values


def load_model_data(
    model_data_path: Path,
    model_settings: dict[str, Any],
    bundle_configuration: dict[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load development rows and verification predictors."""

    (
        categorical_features,
        numeric_features,
        _,
        target,
    ) = configured_columns(model_settings)

    required_columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "data_split",
    ]

    selected_columns = list(
        dict.fromkeys(
            list(model_settings["columns"]["metadata"])
            + required_columns
            + categorical_features
            + numeric_features
            + [target]
        )
    )

    bundle = bundle_configuration["bundle"]
    allowed_splits = [
        *list(bundle["fit_splits"]),
        bundle["verification_split"],
    ]

    dataframe = pd.read_parquet(
        model_data_path,
        engine="pyarrow",
        columns=selected_columns,
        filters=[("data_split", "in", allowed_splits)],
    )

    observed_splits = set(
        dataframe["data_split"].dropna().unique()
    )

    if observed_splits != set(allowed_splits):
        raise ValueError(
            "Loaded model-data splits do not match the bundle "
            "contract."
        )

    development = dataframe.loc[
        dataframe["data_split"].isin(bundle["fit_splits"])
    ].copy()

    verification = dataframe.loc[
        dataframe["data_split"].eq(
            bundle["verification_split"]
        )
    ].copy()

    quality = bundle_configuration["quality"]
    key = list(model_settings["columns"]["key"])

    development_duplicates = int(
        development.duplicated(key).sum()
    )
    verification_duplicates = int(
        verification.duplicated(key).sum()
    )
    unavailable_development_keys = unavailable_key_rows(
        development,
        key,
    )
    unavailable_verification_keys = unavailable_key_rows(
        verification,
        key,
    )
    missing_development_targets = int(
        development[target].isna().sum()
    )

    print(f"development_rows={len(development):,}")
    print(f"verification_rows={len(verification):,}")
    print(
        "development_duplicate_keys="
        f"{development_duplicates}"
    )
    print(
        "verification_duplicate_keys="
        f"{verification_duplicates}"
    )
    print(
        "unavailable_development_keys="
        f"{unavailable_development_keys}"
    )
    print(
        "unavailable_verification_keys="
        f"{unavailable_verification_keys}"
    )
    print(
        "missing_development_targets="
        f"{missing_development_targets}"
    )
    print("verification_targets_used_for_fitting=False")
    print("test_metrics_recalculated=False")

    if len(development) != int(quality["expected_fit_rows"]):
        raise ValueError(
            "Development row count does not match bundle contract."
        )

    if len(verification) != int(
        quality["expected_verification_rows"]
    ):
        raise ValueError(
            "Verification row count does not match bundle contract."
        )

    if development_duplicates or verification_duplicates:
        raise ValueError(
            "Duplicate model-data keys were found."
        )

    if (
        unavailable_development_keys
        or unavailable_verification_keys
    ):
        raise ValueError(
            "Unavailable model-data keys were found."
        )

    if missing_development_targets:
        raise ValueError(
            "Development targets contain missing values."
        )

    expected_positions = set(quality["expected_positions"])

    if set(development["position"].unique()) != expected_positions:
        raise ValueError(
            "Development positions do not match bundle contract."
        )

    if set(verification["position"].unique()) != expected_positions:
        raise ValueError(
            "Verification positions do not match bundle contract."
        )

    verification = verification.drop(columns=[target])

    return development, verification


def load_reference_predictions(
    predictions_path: Path,
    model_settings: dict[str, Any],
    bundle_configuration: dict[str, Any],
    verification: pd.DataFrame,
) -> pd.DataFrame:
    """Load and validate committed position-champion predictions."""

    key = list(model_settings["columns"]["key"])
    selected_model = model_settings["final_evaluation"][
        "selected_model"
    ]
    prediction_column = f"prediction_{selected_model}"
    source_column = f"{selected_model}_source_model"

    required_columns = list(
        dict.fromkeys(
            key
            + [
                "position",
                "data_split",
                prediction_column,
                source_column,
            ]
        )
    )

    reference = pd.read_csv(
        predictions_path,
        usecols=required_columns,
    )

    duplicate_keys = int(reference.duplicated(key).sum())
    unavailable_keys = unavailable_key_rows(reference, key)
    missing_predictions = int(
        reference[prediction_column].isna().sum()
    )
    infinite_predictions = int(
        np.isinf(
            pd.to_numeric(
                reference[prediction_column],
                errors="raise",
            )
        ).sum()
    )

    expected_rows = int(
        bundle_configuration["quality"][
            "expected_verification_rows"
        ]
    )
    expected_split = bundle_configuration["bundle"][
        "verification_split"
    ]

    expected_sources = reference["position"].map(
        bundle_configuration["position_models"]
    )
    source_mismatches = int(
        reference[source_column].ne(expected_sources).sum()
    )

    verification_keys = verification[
        key + ["position"]
    ].drop_duplicates()
    reference_keys = reference[
        key + ["position"]
    ].drop_duplicates()

    key_reconciliation = verification_keys.merge(
        reference_keys,
        on=key + ["position"],
        how="outer",
        indicator=True,
        validate="one_to_one",
    )

    unmatched_keys = int(
        key_reconciliation["_merge"].ne("both").sum()
    )

    print(f"reference_prediction_rows={len(reference):,}")
    print(f"reference_duplicate_keys={duplicate_keys}")
    print(f"reference_unavailable_keys={unavailable_keys}")
    print(
        "reference_missing_predictions="
        f"{missing_predictions}"
    )
    print(
        "reference_infinite_predictions="
        f"{infinite_predictions}"
    )
    print(
        "reference_source_model_mismatches="
        f"{source_mismatches}"
    )
    print(
        "reference_verification_key_mismatches="
        f"{unmatched_keys}"
    )

    if len(reference) != expected_rows:
        raise ValueError(
            "Reference prediction row count is incorrect."
        )

    if duplicate_keys or unavailable_keys:
        raise ValueError(
            "Reference predictions contain invalid keys."
        )

    if missing_predictions or infinite_predictions:
        raise ValueError(
            "Reference predictions contain invalid values."
        )

    if set(reference["data_split"].unique()) != {
        expected_split
    }:
        raise ValueError(
            "Reference prediction split is incorrect."
        )

    if source_mismatches:
        raise ValueError(
            "Reference source-model assignments do not match the "
            "frozen mapping."
        )

    if unmatched_keys:
        raise ValueError(
            "Reference and verification keys do not reconcile."
        )

    return reference


def reference_values_for_position(
    reference: pd.DataFrame,
    verification_position: pd.DataFrame,
    key: list[str],
    prediction_column: str,
) -> np.ndarray:
    """Align committed predictions to verification-row order."""

    reference_position = reference.loc[
        reference["position"].eq(
            verification_position["position"].iloc[0]
        )
    ]

    reference_series = reference_position.set_index(key)[
        prediction_column
    ]
    verification_index = pd.MultiIndex.from_frame(
        verification_position[key]
    )

    aligned = reference_series.reindex(verification_index)

    if aligned.isna().any():
        raise ValueError(
            "Reference predictions could not be aligned."
        )

    return aligned.to_numpy(dtype="float64")


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


def write_json(
    payload: dict[str, Any],
    path: Path,
) -> None:
    """Write deterministic, readable JSON."""

    with path.open(
        "w",
        encoding="utf-8",
        newline="\n",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        file.write("\n")


def build_bundle(
    development: pd.DataFrame,
    verification: pd.DataFrame,
    reference: pd.DataFrame,
    model_settings: dict[str, Any],
    bundle_configuration: dict[str, Any],
    bundle_configuration_path: Path,
    output_paths: dict[str, Any],
    current_commit: str,
    full_commits: dict[str, str],
    observed_hashes: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fit, reproduce, reload, and save all frozen pipelines."""

    (
        categorical_features,
        numeric_features,
        predictor_features,
        target,
    ) = configured_columns(model_settings)

    key = list(model_settings["columns"]["key"])
    selected_model = model_settings["final_evaluation"][
        "selected_model"
    ]
    prediction_column = f"prediction_{selected_model}"
    tolerance = float(
        bundle_configuration["quality"][
            "prediction_absolute_tolerance"
        ]
    )
    position_models = dict(
        bundle_configuration["position_models"]
    )

    artifact_directory = output_paths["artifact_directory"]
    artifact_parent = artifact_directory.parent
    artifact_parent.mkdir(parents=True, exist_ok=True)

    temporary_directory = Path(
        tempfile.mkdtemp(
            prefix=f".{artifact_directory.name}.tmp-",
            dir=artifact_parent,
        )
    ).resolve()

    if (
        temporary_directory.parent != artifact_parent
        or not temporary_directory.name.startswith(
            f".{artifact_directory.name}.tmp-"
        )
    ):
        raise ValueError(
            "Temporary artifact directory failed its safety check."
        )

    verification_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    metadata_positions: dict[str, dict[str, Any]] = {}

    all_reference_differences: list[np.ndarray] = []
    all_reload_differences: list[np.ndarray] = []
    total_start = time.perf_counter()

    try:
        for position in bundle_configuration["quality"][
            "expected_positions"
        ]:
            algorithm = position_models[position]
            position_development = development.loc[
                development["position"].eq(position)
            ].copy()
            position_verification = verification.loc[
                verification["position"].eq(position)
            ].copy()

            if (
                position_development.empty
                or position_verification.empty
            ):
                raise ValueError(
                    f"Bundle data is missing rows for {position}."
                )

            development_predictors = prepare_predictors(
                position_development,
                categorical_features,
                numeric_features,
            )
            verification_predictors = prepare_predictors(
                position_verification,
                categorical_features,
                numeric_features,
            )
            expected_predictions = (
                reference_values_for_position(
                    reference,
                    position_verification,
                    key,
                    prediction_column,
                )
            )

            pipeline = build_candidate_pipeline(
                algorithm,
                model_settings,
            )

            position_start = time.perf_counter()

            pipeline.fit(
                development_predictors,
                position_development[target],
            )

            reproduced_predictions = np.asarray(
                pipeline.predict(verification_predictors),
                dtype="float64",
            )

            fit_predict_seconds = (
                time.perf_counter() - position_start
            )

            if not np.isfinite(reproduced_predictions).all():
                raise ValueError(
                    f"{position} produced non-finite predictions."
                )

            reference_difference = np.abs(
                reproduced_predictions - expected_predictions
            )
            prediction_mismatch_rows = int(
                np.count_nonzero(
                    reference_difference > tolerance
                )
            )

            if prediction_mismatch_rows:
                raise ValueError(
                    f"{position} failed committed-prediction "
                    "reproduction."
                )

            artifact_filename = bundle_configuration["output"][
                "artifact_files"
            ][position]
            temporary_artifact_path = (
                temporary_directory / artifact_filename
            )

            joblib.dump(
                pipeline,
                temporary_artifact_path,
                compress=3,
            )

            reloaded_pipeline = joblib.load(
                temporary_artifact_path
            )
            reloaded_predictions = np.asarray(
                reloaded_pipeline.predict(
                    verification_predictors
                ),
                dtype="float64",
            )

            reload_difference = np.abs(
                reloaded_predictions - expected_predictions
            )
            reload_mismatch_rows = int(
                np.count_nonzero(
                    reload_difference > tolerance
                )
            )

            if reload_mismatch_rows:
                raise ValueError(
                    f"{position} reloaded artifact failed "
                    "prediction reproduction."
                )

            artifact_hash = sha256_file(
                temporary_artifact_path
            )
            final_artifact_path = output_paths["artifacts"][
                position
            ]

            maximum_reference_difference = float(
                reference_difference.max()
            )
            mean_reference_difference = float(
                reference_difference.mean()
            )
            maximum_reload_difference = float(
                reload_difference.max()
            )

            verification_rows.append(
                {
                    "scope": "position",
                    "position": position,
                    "algorithm": algorithm,
                    "fit_rows": len(position_development),
                    "verification_rows": len(
                        position_verification
                    ),
                    "prediction_mismatch_rows": (
                        prediction_mismatch_rows
                    ),
                    "maximum_absolute_difference": (
                        maximum_reference_difference
                    ),
                    "mean_absolute_difference": (
                        mean_reference_difference
                    ),
                    "reload_mismatch_rows": (
                        reload_mismatch_rows
                    ),
                    "maximum_reload_difference": (
                        maximum_reload_difference
                    ),
                    "verification_status": "PASS",
                }
            )

            manifest_rows.append(
                {
                    "bundle_name": bundle_configuration[
                        "bundle"
                    ]["name"],
                    "bundle_version": bundle_configuration[
                        "bundle"
                    ]["version"],
                    "build_commit": current_commit,
                    "position": position,
                    "algorithm": algorithm,
                    "artifact_path": str(
                        final_artifact_path.relative_to(
                            PROJECT_ROOT
                        )
                    ).replace("\\", "/"),
                    "artifact_sha256": artifact_hash,
                    "fit_rows": len(position_development),
                    "verification_rows": len(
                        position_verification
                    ),
                    "predictor_count": len(
                        predictor_features
                    ),
                    "prediction_mismatch_rows": (
                        prediction_mismatch_rows
                    ),
                    "maximum_absolute_difference": (
                        maximum_reference_difference
                    ),
                    "reload_mismatch_rows": (
                        reload_mismatch_rows
                    ),
                    "maximum_reload_difference": (
                        maximum_reload_difference
                    ),
                    "verification_status": "PASS",
                }
            )

            metadata_positions[position] = {
                "algorithm": algorithm,
                "artifact_file": artifact_filename,
                "artifact_sha256": artifact_hash,
                "fit_rows": len(position_development),
                "verification_rows": len(
                    position_verification
                ),
                "fit_predict_seconds": round(
                    fit_predict_seconds,
                    6,
                ),
                "maximum_absolute_difference": (
                    maximum_reference_difference
                ),
                "maximum_reload_difference": (
                    maximum_reload_difference
                ),
            }

            all_reference_differences.append(
                reference_difference
            )
            all_reload_differences.append(
                reload_difference
            )

            print(
                f"{position} {algorithm}: "
                f"fit_rows={len(position_development):,}, "
                f"verification_rows="
                f"{len(position_verification):,}, "
                f"maximum_difference="
                f"{maximum_reference_difference:.12g}, "
                f"seconds={fit_predict_seconds:.1f}"
            )

        combined_reference_difference = np.concatenate(
            all_reference_differences
        )
        combined_reload_difference = np.concatenate(
            all_reload_differences
        )

        overall_prediction_mismatches = int(
            np.count_nonzero(
                combined_reference_difference > tolerance
            )
        )
        overall_reload_mismatches = int(
            np.count_nonzero(
                combined_reload_difference > tolerance
            )
        )

        verification_rows.append(
            {
                "scope": "overall",
                "position": "ALL",
                "algorithm": selected_model,
                "fit_rows": len(development),
                "verification_rows": len(verification),
                "prediction_mismatch_rows": (
                    overall_prediction_mismatches
                ),
                "maximum_absolute_difference": float(
                    combined_reference_difference.max()
                ),
                "mean_absolute_difference": float(
                    combined_reference_difference.mean()
                ),
                "reload_mismatch_rows": (
                    overall_reload_mismatches
                ),
                "maximum_reload_difference": float(
                    combined_reload_difference.max()
                ),
                "verification_status": "PASS",
            }
        )

        total_seconds = time.perf_counter() - total_start
        created_at_utc = datetime.now(
            timezone.utc
        ).isoformat()

        metadata_payload = {
            "bundle_name": bundle_configuration["bundle"][
                "name"
            ],
            "bundle_version": bundle_configuration["bundle"][
                "version"
            ],
            "bundle_type": bundle_configuration["bundle"][
                "bundle_type"
            ],
            "created_at_utc": created_at_utc,
            "build_commit": current_commit,
            "selection_commit": full_commits[
                "selection_commit"
            ],
            "protocol_commit": full_commits[
                "protocol_commit"
            ],
            "evidence_commit": full_commits[
                "evidence_commit"
            ],
            "fit_splits": list(
                bundle_configuration["bundle"]["fit_splits"]
            ),
            "verification_split": bundle_configuration[
                "bundle"
            ]["verification_split"],
            "selected_model": selected_model,
            "model_reselection_performed": False,
            "test_metrics_recalculated": False,
            "development_rows": len(development),
            "verification_rows": len(verification),
            "target": target,
            "categorical_features": categorical_features,
            "numeric_features": numeric_features,
            "predictor_features": predictor_features,
            "predictor_count": len(predictor_features),
            "prediction_absolute_tolerance": tolerance,
            "bundle_configuration_sha256": sha256_file(
                bundle_configuration_path
            ),
            "source_hashes": observed_hashes,
            "packages": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pandas": pd.__version__,
                "scikit_learn": sklearn.__version__,
                "joblib": joblib.__version__,
            },
            "position_models": metadata_positions,
            "total_fit_and_verification_seconds": round(
                total_seconds,
                6,
            ),
        }

        temporary_metadata_path = (
            temporary_directory
            / output_paths["metadata"].name
        )
        write_json(
            metadata_payload,
            temporary_metadata_path,
        )
        metadata_hash = sha256_file(
            temporary_metadata_path
        )

        manifest = pd.DataFrame(manifest_rows)
        manifest["metadata_path"] = str(
            output_paths["metadata"].relative_to(PROJECT_ROOT)
        ).replace("\\", "/")
        manifest["metadata_sha256"] = metadata_hash

        verification_summary = pd.DataFrame(
            verification_rows
        )

        expected_artifacts = int(
            bundle_configuration["quality"][
                "expected_artifact_files"
            ]
        )
        expected_verification_summaries = int(
            bundle_configuration["quality"][
                "expected_verification_summary_rows"
            ]
        )

        if len(manifest) != expected_artifacts:
            raise ValueError(
                "Bundle manifest row count is incorrect."
            )

        if (
            len(verification_summary)
            != expected_verification_summaries
        ):
            raise ValueError(
                "Bundle verification row count is incorrect."
            )

        if (
            verification_summary[
                "prediction_mismatch_rows"
            ].sum()
            or verification_summary[
                "reload_mismatch_rows"
            ].sum()
        ):
            raise ValueError(
                "Bundle verification contains mismatches."
            )

        temporary_directory.rename(artifact_directory)
        temporary_directory = None

        atomic_write_csv(
            manifest,
            output_paths["manifest"],
        )
        atomic_write_csv(
            verification_summary,
            output_paths["verification"],
        )

        return manifest, verification_summary

    finally:
        if (
            temporary_directory is not None
            and temporary_directory.exists()
        ):
            if (
                temporary_directory.parent != artifact_parent
                or not temporary_directory.name.startswith(
                    f".{artifact_directory.name}.tmp-"
                )
            ):
                raise RuntimeError(
                    "Refusing to remove an unsafe temporary path."
                )

            shutil.rmtree(temporary_directory)


def reopen_and_validate_outputs(
    manifest: pd.DataFrame,
    verification_summary: pd.DataFrame,
    development: pd.DataFrame,
    verification: pd.DataFrame,
    reference: pd.DataFrame,
    model_settings: dict[str, Any],
    bundle_configuration: dict[str, Any],
    output_paths: dict[str, Any],
) -> None:
    """Reopen written evidence and reproduce predictions again."""

    written_manifest = pd.read_csv(output_paths["manifest"])
    written_verification = pd.read_csv(
        output_paths["verification"]
    )

    with output_paths["metadata"].open(
        "r",
        encoding="utf-8",
    ) as file:
        written_metadata = json.load(file)

    expected_artifacts = int(
        bundle_configuration["quality"][
            "expected_artifact_files"
        ]
    )
    expected_verification_rows = int(
        bundle_configuration["quality"][
            "expected_verification_summary_rows"
        ]
    )

    print(f"written_manifest_rows={len(written_manifest):,}")
    print(
        "written_verification_summary_rows="
        f"{len(written_verification):,}"
    )
    print(
        "written_metadata_bundle_version="
        f"{written_metadata.get('bundle_version')}"
    )

    if len(written_manifest) != expected_artifacts:
        raise ValueError(
            "Written bundle manifest row count is incorrect."
        )

    if len(written_verification) != expected_verification_rows:
        raise ValueError(
            "Written verification row count is incorrect."
        )

    if not written_manifest.equals(manifest):
        raise ValueError(
            "Written bundle manifest does not match memory."
        )

    if not written_verification.equals(
        verification_summary
    ):
        numeric_columns = [
            "maximum_absolute_difference",
            "mean_absolute_difference",
            "maximum_reload_difference",
        ]

        nonnumeric_columns = [
            column
            for column in verification_summary.columns
            if column not in numeric_columns
        ]

        if not written_verification[
            nonnumeric_columns
        ].equals(
            verification_summary[nonnumeric_columns]
        ):
            raise ValueError(
                "Written verification labels do not match memory."
            )

        for column in numeric_columns:
            if not np.allclose(
                written_verification[column],
                verification_summary[column],
                rtol=0.0,
                atol=1e-15,
                equal_nan=True,
            ):
                raise ValueError(
                    "Written verification values do not match memory."
                )

    if (
        written_metadata.get("bundle_version")
        != bundle_configuration["bundle"]["version"]
    ):
        raise ValueError(
            "Written bundle metadata version is incorrect."
        )

    (
        categorical_features,
        numeric_features,
        _,
        _,
    ) = configured_columns(model_settings)

    key = list(model_settings["columns"]["key"])
    selected_model = model_settings["final_evaluation"][
        "selected_model"
    ]
    prediction_column = f"prediction_{selected_model}"
    tolerance = float(
        bundle_configuration["quality"][
            "prediction_absolute_tolerance"
        ]
    )

    final_mismatch_rows = 0
    artifact_hash_mismatches = 0

    for position in bundle_configuration["quality"][
        "expected_positions"
    ]:
        artifact_path = output_paths["artifacts"][position]

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Written artifact not found: {artifact_path}"
            )

        manifest_row = written_manifest.loc[
            written_manifest["position"].eq(position)
        ]

        if len(manifest_row) != 1:
            raise ValueError(
                f"Manifest row is invalid for {position}."
            )

        expected_hash = manifest_row.iloc[0][
            "artifact_sha256"
        ]
        observed_hash = sha256_file(artifact_path)

        if observed_hash != expected_hash:
            artifact_hash_mismatches += 1

        reloaded_pipeline = joblib.load(artifact_path)
        position_verification = verification.loc[
            verification["position"].eq(position)
        ]
        verification_predictors = prepare_predictors(
            position_verification,
            categorical_features,
            numeric_features,
        )
        expected_predictions = reference_values_for_position(
            reference,
            position_verification,
            key,
            prediction_column,
        )
        observed_predictions = np.asarray(
            reloaded_pipeline.predict(
                verification_predictors
            ),
            dtype="float64",
        )
        difference = np.abs(
            observed_predictions - expected_predictions
        )
        final_mismatch_rows += int(
            np.count_nonzero(difference > tolerance)
        )

    print(
        "written_artifact_hash_mismatches="
        f"{artifact_hash_mismatches}"
    )
    print(
        "written_prediction_reproduction_mismatches="
        f"{final_mismatch_rows}"
    )

    if artifact_hash_mismatches:
        raise ValueError(
            "Written model artifact hashes do not reconcile."
        )

    if final_mismatch_rows:
        raise ValueError(
            "Written artifacts do not reproduce committed "
            "predictions."
        )


def main() -> None:
    """Run the frozen Version 1 model-bundle build."""

    arguments = parse_arguments()
    configuration_path = Path(arguments.config).resolve()
    configuration = load_toml(configuration_path)

    validate_bundle_configuration(
        configuration,
        arguments.confirm_build,
    )

    input_paths = resolve_input_paths(configuration)
    output_paths = resolve_output_paths(configuration)

    print_section("NFL FANTASY VERSION 1 MODEL BUNDLE")

    print(f"Configuration: {configuration_path}")
    print(
        "Bundle version: "
        f"{configuration['bundle']['version']}"
    )
    print(
        "Bundle type: "
        f"{configuration['bundle']['bundle_type']}"
    )
    print(
        "Position models: "
        f"{dict(configuration['position_models'])}"
    )
    print(
        "Fit splits: "
        f"{list(configuration['bundle']['fit_splits'])}"
    )
    print(
        "Verification split: "
        f"{configuration['bundle']['verification_split']}"
    )
    print("Model reselection permitted: False")

    print_section("BUNDLE BUILD GUARDS")

    ensure_outputs_do_not_exist(output_paths)
    current_commit, full_commits = validate_git_state(
        configuration
    )

    print_section("FROZEN INPUT RECONCILIATION")

    observed_hashes = validate_input_hashes(
        configuration,
        input_paths,
    )
    model_settings = load_toml(
        input_paths["model_settings_path"]
    )
    validate_model_settings(
        model_settings,
        configuration,
    )
    validate_final_run_manifest(
        input_paths["final_run_manifest_path"],
        configuration,
        full_commits,
    )

    print_section("LOADING BUNDLE DATA")

    development, verification = load_model_data(
        input_paths["model_data_path"],
        model_settings,
        configuration,
    )
    reference = load_reference_predictions(
        input_paths["final_predictions_path"],
        model_settings,
        configuration,
        verification,
    )

    print_section("FITTING AND REPRODUCING FROZEN MODELS")

    manifest, verification_summary = build_bundle(
        development,
        verification,
        reference,
        model_settings,
        configuration,
        configuration_path,
        output_paths,
        current_commit,
        full_commits,
        observed_hashes,
    )

    print()
    print(
        verification_summary.to_string(
            index=False
        )
    )

    print_section("REOPENING WRITTEN MODEL BUNDLE")

    reopen_and_validate_outputs(
        manifest,
        verification_summary,
        development,
        verification,
        reference,
        model_settings,
        configuration,
        output_paths,
    )

    print_section("VERSION 1 MODEL BUNDLE COMPLETE")

    print("frozen_input_hashes=PASS")
    print("development_refit_quality=PASS")
    print("committed_prediction_reproduction=PASS")
    print("artifact_reload_quality=PASS")
    print("model_reselection_performed=False")
    print("test_metrics_recalculated=False")
    print("model_bundle_status=PASS")


if __name__ == "__main__":
    main()