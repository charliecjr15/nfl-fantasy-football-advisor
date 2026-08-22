"""Build provisional weekly position and FLEX rankings."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = (
    PROJECT_ROOT / "config" / "weekly_rankings_settings.toml"
)

TEAM_ALIASES = {
    "AZ": "ARI",
    "ARZ": "ARI",
    "JAC": "JAX",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
}

ROSTER_CONFIG_KEYS = {
    "QB": "quarterbacks",
    "RB": "running_backs",
    "WR": "wide_receivers",
    "TE": "tight_ends",
}


def parse_arguments() -> argparse.Namespace:
    """Parse an explicit season-week ranking build."""

    parser = argparse.ArgumentParser(
        description=(
            "Build provisional weekly fantasy rankings from a frozen "
            "target-free projection run."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to the weekly ranking settings TOML file.",
    )
    parser.add_argument(
        "--confirm-build",
        required=True,
        help="Required confirmation token from the configuration.",
    )
    return parser.parse_args()


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
        return str(resolved.relative_to(PROJECT_ROOT)).replace("\\", "/")
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


def run_git_command(*arguments: str) -> str:
    """Run a Git command in the project repository."""

    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def require_clean_worktree(configuration: dict[str, Any]) -> str:
    """Require a committed protocol before creating evidence."""

    if configuration["rankings"]["require_clean_worktree"]:
        status = run_git_command("status", "--porcelain")
        if status:
            raise ValueError(
                "The worktree must be clean before ranking evidence is "
                "created. Commit the protocol or remove unrelated changes."
            )
    return run_git_command("rev-parse", "HEAD")


def unavailable_rows(
    dataframe: pd.DataFrame,
    columns: list[str],
) -> int:
    """Count rows with a null or blank required value."""

    unavailable = pd.Series(False, index=dataframe.index, dtype="bool")
    for column in columns:
        missing = dataframe[column].isna()
        if (
            pd.api.types.is_object_dtype(dataframe[column])
            or pd.api.types.is_string_dtype(dataframe[column])
        ):
            missing = (
                missing
                | dataframe[column]
                .fillna("")
                .astype(str)
                .str.strip()
                .eq("")
            )
        unavailable = unavailable | missing
    return int(unavailable.sum())


def load_key_value_manifest(path: Path) -> dict[str, str]:
    """Load a two-column key-value CSV manifest."""

    if not path.exists():
        raise FileNotFoundError(f"Manifest not found: {path}")
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    if list(frame.columns) != ["manifest_key", "manifest_value"]:
        raise ValueError(f"Unexpected manifest schema: {path}")
    if frame["manifest_key"].duplicated().any():
        raise ValueError(f"Duplicate manifest keys: {path}")
    return dict(zip(frame["manifest_key"], frame["manifest_value"]))


def format_template(
    template: str,
    season: int,
    week: int,
) -> str:
    """Render a configured season-week path template."""

    return template.format(season=season, week=f"{week:02d}")


def build_run_paths(
    configuration: dict[str, Any],
    season: int,
    week: int,
) -> dict[str, Path]:
    """Resolve every input and output path for one run."""

    paths: dict[str, Path] = {}
    for section in ("inputs", "outputs"):
        for key, value in configuration[section].items():
            if key == "league_settings_path":
                rendered = value
            else:
                rendered = format_template(value, season, week)
            paths[key] = resolve_project_path(rendered)
    return paths


def validate_configuration(
    configuration: dict[str, Any],
    confirmation_token: str,
) -> None:
    """Validate ranking settings and the explicit build token."""

    required_sections = {
        "rankings",
        "inputs",
        "outputs",
        "role_eligibility",
        "confidence",
        "quality",
    }
    missing = sorted(required_sections - set(configuration))
    if missing:
        raise ValueError(
            "Ranking configuration is missing sections: "
            + ", ".join(missing)
        )

    rankings = configuration["rankings"]
    if confirmation_token != rankings["confirmation_token"]:
        raise ValueError("The ranking build confirmation token is incorrect.")
    if rankings["injury_context_status"] != (
        "SOURCE_UNAVAILABLE_FOR_2026_AT_BUILD"
    ):
        raise ValueError(
            "Version 1 requires the unavailable injury source to remain "
            "explicit rather than inferred as healthy."
        )

    positions = list(configuration["quality"]["supported_positions"])
    if set(configuration["role_eligibility"]) != set(positions):
        raise ValueError("Role-eligibility thresholds are incomplete.")
    if any(
        int(configuration["role_eligibility"][position]) < 1
        for position in positions
    ):
        raise ValueError("Depth-rank thresholds must be positive integers.")


def validate_input_hashes(
    paths: dict[str, Path],
    feature_manifest: dict[str, str],
    inference_manifest: dict[str, str],
) -> dict[str, str]:
    """Reconcile live inputs with their frozen manifests."""

    required_files = [
        "predictions_template",
        "features_template",
        "depth_snapshot_template",
        "feature_manifest_template",
        "inference_manifest_template",
        "league_settings_path",
    ]
    missing = [key for key in required_files if not paths[key].exists()]
    if missing:
        raise FileNotFoundError(
            "Required ranking inputs do not exist: " + ", ".join(missing)
        )

    actual = {
        "predictions": sha256_file(paths["predictions_template"]),
        "features": sha256_file(paths["features_template"]),
        "depth_snapshot": sha256_file(paths["depth_snapshot_template"]),
    }
    feature_sources = json.loads(feature_manifest["source_sha256"])

    expected = {
        "predictions": inference_manifest["predictions_sha256"],
        "features_from_inference": inference_manifest["input_sha256"],
        "features_from_builder": feature_manifest["features_sha256"],
        "depth_snapshot": feature_sources["depth_chart"],
    }
    if actual["predictions"] != expected["predictions"]:
        raise ValueError("Prediction hash differs from inference evidence.")
    if actual["features"] != expected["features_from_inference"]:
        raise ValueError("Feature hash differs from inference input evidence.")
    if actual["features"] != expected["features_from_builder"]:
        raise ValueError("Feature hash differs from builder evidence.")
    if actual["depth_snapshot"] != expected["depth_snapshot"]:
        raise ValueError("Depth snapshot hash differs from feature evidence.")
    return actual


def validate_frame_keys(
    dataframe: pd.DataFrame,
    key_columns: list[str],
    label: str,
) -> None:
    """Validate one-to-one player-game keys."""

    unavailable = unavailable_rows(dataframe, key_columns)
    duplicates = int(dataframe.duplicated(key_columns).sum())
    if unavailable:
        raise ValueError(f"{label} has {unavailable} unavailable key rows.")
    if duplicates:
        raise ValueError(f"{label} has {duplicates} duplicate key rows.")


def load_projection_context(
    paths: dict[str, Path],
    configuration: dict[str, Any],
    season: int,
    week: int,
) -> pd.DataFrame:
    """Load and reconcile predictions with their future features."""

    quality = configuration["quality"]
    metadata = list(quality["required_metadata_columns"])
    feature_columns = list(quality["required_feature_columns"])
    prediction = str(quality["prediction_column"])
    source_model = str(quality["source_model_column"])
    target = "target_fantasy_points_ppr"

    predictions = pd.read_parquet(paths["predictions_template"])
    features = pd.read_parquet(
        paths["features_template"],
        columns=metadata + feature_columns,
    )
    if target in predictions.columns or target in features.columns:
        raise ValueError("The ranking workflow must remain target-free.")

    required_predictions = set(metadata + [prediction, source_model])
    missing_predictions = sorted(
        required_predictions - set(predictions.columns)
    )
    if missing_predictions:
        raise ValueError(
            "Prediction input is missing columns: "
            + ", ".join(missing_predictions)
        )

    key_columns = ["season", "week", "game_id", "player_id"]
    validate_frame_keys(predictions, key_columns, "Predictions")
    validate_frame_keys(features, key_columns, "Features")
    if not np.isfinite(predictions[prediction].to_numpy()).all():
        raise ValueError("Predictions contain missing or infinite values.")

    context = predictions.merge(
        features,
        on=metadata,
        how="inner",
        validate="one_to_one",
    )
    if len(context) != len(predictions) or len(context) != len(features):
        raise ValueError("Prediction-to-feature reconciliation dropped rows.")
    if not context["season"].eq(season).all():
        raise ValueError("Prediction rows do not match the requested season.")
    if not context["week"].eq(week).all():
        raise ValueError("Prediction rows do not match the requested week.")

    supported = set(quality["supported_positions"])
    observed = set(context["position"].unique())
    if observed != supported:
        raise ValueError(
            f"Observed positions {sorted(observed)} do not match "
            f"{sorted(supported)}."
        )
    return context


def load_current_depth(
    path: Path,
    as_of_utc: str,
    supported_positions: list[str],
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """Select the last depth snapshot per team at the frozen cutoff."""

    columns = [
        "dt",
        "team",
        "gsis_id",
        "pos_abb",
        "pos_slot",
        "pos_rank",
    ]
    depth = pd.read_parquet(path, columns=columns)
    depth["team"] = depth["team"].replace(TEAM_ALIASES)
    depth["depth_timestamp"] = pd.to_datetime(depth["dt"], utc=True)
    cutoff = pd.Timestamp(as_of_utc)
    if cutoff.tzinfo is None:
        raise ValueError("The source cutoff must be timezone aware.")
    depth = depth.loc[depth["depth_timestamp"].le(cutoff)].copy()
    if depth.empty:
        raise ValueError("No depth snapshot exists at the source cutoff.")

    latest = depth.groupby("team")["depth_timestamp"].transform("max")
    depth = depth.loc[
        depth["depth_timestamp"].eq(latest)
        & depth["pos_abb"].isin(supported_positions)
        & depth["gsis_id"].notna()
    ].copy()
    depth = (
        depth.sort_values(
            ["team", "gsis_id", "pos_rank", "pos_slot"],
            kind="stable",
        )
        .drop_duplicates(["team", "gsis_id"], keep="first")
        .reset_index(drop=True)
    )
    return depth, depth["depth_timestamp"].max()


def attach_depth_context(
    context: pd.DataFrame,
    depth: pd.DataFrame,
    require_all_matches: bool,
) -> pd.DataFrame:
    """Attach one current depth row to every projected player."""

    columns = [
        "team",
        "gsis_id",
        "pos_abb",
        "pos_slot",
        "pos_rank",
        "depth_timestamp",
    ]
    ranked = context.merge(
        depth[columns],
        left_on=["team", "player_id"],
        right_on=["team", "gsis_id"],
        how="left",
        validate="one_to_one",
    )
    missing = int(ranked["depth_timestamp"].isna().sum())
    if require_all_matches and missing:
        raise ValueError(f"{missing} projected rows lack depth context.")
    ranked["depth_position_matches_model_position"] = (
        ranked["pos_abb"].notna()
        & ranked["position"].eq(ranked["pos_abb"])
    )
    return ranked


def assign_deterministic_rank(
    dataframe: pd.DataFrame,
    mask: pd.Series,
    group_column: str | None,
    score_column: str,
) -> pd.Series:
    """Rank selected rows by score descending and player ID ascending."""

    output = pd.Series(pd.NA, index=dataframe.index, dtype="Int64")
    selected = dataframe.loc[mask].copy()
    sort_columns = (
        [group_column, score_column, "player_id"]
        if group_column
        else [score_column, "player_id"]
    )
    ascending = [True, False, True] if group_column else [False, True]
    selected = selected.sort_values(
        sort_columns,
        ascending=ascending,
        kind="stable",
    )
    if group_column:
        ranks = selected.groupby(group_column).cumcount() + 1
    else:
        ranks = pd.Series(
            range(1, len(selected) + 1),
            index=selected.index,
        )
    output.loc[selected.index] = ranks.astype("int64")
    return output


def assign_confidence(
    dataframe: pd.DataFrame,
    settings: dict[str, Any],
) -> pd.Series:
    """Label historical-evidence strength without implying certainty."""

    high = (
        dataframe["prior_games_count"].ge(
            settings["high_minimum_prior_games"]
        )
        & dataframe["days_since_previous_game"].le(
            settings["high_maximum_days_since_previous_game"]
        )
    )
    if settings["require_previous_snap_record_for_high"]:
        high = high & dataframe["has_previous_snap_record"].eq(1)

    medium = (
        dataframe["prior_games_count"].ge(
            settings["medium_minimum_prior_games"]
        )
        & dataframe["days_since_previous_game"].le(
            settings["medium_maximum_days_since_previous_game"]
        )
    )
    confidence = pd.Series("LOW", index=dataframe.index, dtype="string")
    confidence.loc[medium] = "MEDIUM"
    confidence.loc[high] = "HIGH"
    return confidence


def assign_rankings(
    dataframe: pd.DataFrame,
    configuration: dict[str, Any],
    league_settings: dict[str, Any],
) -> pd.DataFrame:
    """Apply depth eligibility, position demand, and FLEX demand."""

    rankings = dataframe.copy()
    quality = configuration["quality"]
    score = str(quality["prediction_column"])
    positions = list(quality["supported_positions"])
    role_caps = {
        position: int(configuration["role_eligibility"][position])
        for position in positions
    }
    team_count = int(league_settings["league"]["team_count"])
    starter_counts = {
        position: team_count
        * int(
            league_settings["roster"][ROSTER_CONFIG_KEYS[position]]
        )
        for position in positions
    }
    flex_count = team_count * int(league_settings["roster"]["flex"])

    rankings["raw_position_rank"] = assign_deterministic_rank(
        rankings,
        pd.Series(True, index=rankings.index),
        "position",
        score,
    )
    rankings["depth_position_matches_model_position"] = (
        rankings["pos_abb"].notna()
        & rankings["position"].eq(rankings["pos_abb"])
    )
    rankings["role_eligible"] = rankings.apply(
        lambda row: bool(
            pd.notna(row["pos_rank"])
            and row["depth_position_matches_model_position"]
            and int(row["pos_rank"]) <= role_caps[row["position"]]
        ),
        axis=1,
    )
    rankings["position_rank"] = assign_deterministic_rank(
        rankings,
        rankings["role_eligible"],
        "position",
        score,
    )

    base_starter = pd.Series(False, index=rankings.index, dtype="bool")
    for position, required in starter_counts.items():
        eligible_count = int(
            rankings.loc[
                rankings["role_eligible"]
                & rankings["position"].eq(position)
            ].shape[0]
        )
        if eligible_count < required:
            raise ValueError(
                f"Only {eligible_count} role-eligible {position} rows "
                f"exist for {required} required starter slots."
            )
        base_starter = base_starter | (
            rankings["position"].eq(position)
            & rankings["role_eligible"]
            & rankings["position_rank"].le(required)
        )
    rankings["base_position_starter"] = base_starter

    flex_positions = set(
        league_settings["roster"]["flex_eligible_positions"]
    )
    flex_eligible = (
        rankings["position"].isin(flex_positions)
        & rankings["role_eligible"]
    )
    rankings["overall_flex_rank"] = assign_deterministic_rank(
        rankings,
        flex_eligible,
        None,
        score,
    )
    remaining_flex = flex_eligible & ~base_starter
    rankings["remaining_flex_rank"] = assign_deterministic_rank(
        rankings,
        remaining_flex,
        None,
        score,
    )
    projected_flex = remaining_flex & rankings["remaining_flex_rank"].le(
        flex_count
    )

    rankings["projected_lineup_slot"] = "BENCH_DEPTH"
    rankings.loc[~rankings["role_eligible"], "projected_lineup_slot"] = (
        "ROLE_FILTERED"
    )
    rankings.loc[base_starter, "projected_lineup_slot"] = rankings.loc[
        base_starter, "position"
    ]
    rankings.loc[projected_flex, "projected_lineup_slot"] = "FLEX"

    rankings["lineup_tier"] = "BENCH_DEPTH"
    rankings.loc[~rankings["role_eligible"], "lineup_tier"] = (
        "ROLE_FILTERED"
    )
    rankings.loc[base_starter, "lineup_tier"] = "PROVISIONAL_STARTER"
    rankings.loc[projected_flex, "lineup_tier"] = "PROVISIONAL_FLEX"

    rankings["evidence_confidence"] = assign_confidence(
        rankings,
        configuration["confidence"],
    )
    rankings["display_projected_fantasy_points_ppr"] = rankings[
        score
    ].clip(lower=float(configuration["rankings"]["display_projection_floor"]))
    rankings["injury_context"] = configuration["rankings"][
        "injury_context_status"
    ]

    def flags(row: pd.Series) -> str:
        row_flags = ["INJURY_CONTEXT_UNAVAILABLE"]
        if not row["role_eligible"]:
            row_flags.append("OUTSIDE_DEPTH_ELIGIBILITY")
        if not row["depth_position_matches_model_position"]:
            row_flags.append("DEPTH_POSITION_MISMATCH")
        if row["prior_games_count"] == 0:
            row_flags.append("NO_PRIOR_GAMES")
        elif row["prior_games_count"] < configuration["confidence"][
            "medium_minimum_prior_games"
        ]:
            row_flags.append("LIMITED_HISTORY")
        if (
            pd.notna(row["days_since_previous_game"])
            and row["days_since_previous_game"]
            > configuration["confidence"][
                "medium_maximum_days_since_previous_game"
            ]
        ):
            row_flags.append("STALE_HISTORY")
        if row[score] < configuration["rankings"][
            "display_projection_floor"
        ]:
            row_flags.append("RAW_PROJECTION_BELOW_DISPLAY_FLOOR")
        return ";".join(row_flags)

    rankings["risk_flags"] = rankings.apply(flags, axis=1)
    rankings["recommendation_reason"] = rankings.apply(
        lambda row: (
            f"Raw {row[score]:.2f} PPR; "
            f"{row['position']} raw rank {int(row['raw_position_rank'])}; "
            f"depth slot {int(row['pos_slot'])}, rank "
            f"{int(row['pos_rank'])}; {int(row['prior_games_count'])} "
            "prior games; injury context unavailable."
        ),
        axis=1,
    )

    expected_starters = sum(starter_counts.values()) + flex_count
    selected = rankings["lineup_tier"].isin(
        ["PROVISIONAL_STARTER", "PROVISIONAL_FLEX"]
    )
    if int(selected.sum()) != expected_starters:
        raise ValueError(
            f"Expected {expected_starters} projected starters but found "
            f"{int(selected.sum())}."
        )
    return rankings


def finalize_output(
    rankings: pd.DataFrame,
    configuration: dict[str, Any],
    feature_manifest: dict[str, str],
    inference_manifest: dict[str, str],
) -> pd.DataFrame:
    """Select stable reader-facing columns and deterministic order."""

    rankings = rankings.copy()
    rankings["source_as_of_utc"] = feature_manifest["as_of_utc"]
    rankings["projection_created_at_utc"] = inference_manifest[
        "run_timestamp_utc"
    ]
    rankings["model_bundle_version"] = inference_manifest[
        "model_bundle_version"
    ]
    rankings["ranking_version"] = configuration["rankings"]["version"]
    rankings = rankings.rename(
        columns={
            "pos_abb": "depth_position",
            "pos_slot": "depth_slot",
            "pos_rank": "depth_rank",
        }
    )

    columns = [
        "season",
        "week",
        "game_id",
        "game_date",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "projected_fantasy_points_ppr",
        "display_projected_fantasy_points_ppr",
        "raw_position_rank",
        "position_rank",
        "overall_flex_rank",
        "remaining_flex_rank",
        "projected_lineup_slot",
        "lineup_tier",
        "role_eligible",
        "depth_position_matches_model_position",
        "depth_position",
        "depth_slot",
        "depth_rank",
        "evidence_confidence",
        "prior_games_count",
        "prior_games_current_season",
        "days_since_previous_game",
        "fantasy_points_ppr_avg_last_5_games",
        "opportunities_avg_last_5_games",
        "offense_pct_avg_last_5_games",
        "injury_context",
        "risk_flags",
        "recommendation_reason",
        "source_as_of_utc",
        "projection_created_at_utc",
        "projection_source_model",
        "model_bundle_version",
        "ranking_version",
    ]
    slot_order = {
        "QB": 1,
        "RB": 2,
        "WR": 3,
        "TE": 4,
        "FLEX": 5,
        "BENCH_DEPTH": 6,
        "ROLE_FILTERED": 7,
    }
    rankings["_slot_order"] = rankings["projected_lineup_slot"].map(
        slot_order
    )
    rankings = rankings.sort_values(
        [
            "_slot_order",
            "position",
            "projected_fantasy_points_ppr",
            "player_id",
        ],
        ascending=[True, True, False, True],
        kind="stable",
    )
    return rankings[columns].reset_index(drop=True)


def atomic_write_parquet(dataframe: pd.DataFrame, path: Path) -> None:
    """Write Parquet through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        dataframe.to_parquet(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    """Write CSV through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        dataframe.to_csv(temporary, index=False, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    """Write indented JSON through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def ensure_outputs_available(
    paths: dict[str, Path],
    fail_if_exists: bool,
) -> None:
    """Prevent replacement of prior ranking evidence."""

    output_keys = [
        "rankings_parquet_template",
        "rankings_csv_template",
        "manifest_template",
        "report_artifact_template",
    ]
    existing = [
        display_path(paths[key])
        for key in output_keys
        if paths[key].exists()
    ]
    if fail_if_exists and existing:
        raise FileExistsError(
            "Ranking outputs already exist and cannot be replaced: "
            + ", ".join(existing)
        )


def build_manifest(
    rankings: pd.DataFrame,
    configuration: dict[str, Any],
    configuration_path: Path,
    paths: dict[str, Path],
    input_hashes: dict[str, str],
    ranking_commit: str,
    run_timestamp: str,
    maximum_depth_timestamp: pd.Timestamp,
) -> pd.DataFrame:
    """Build key-value lineage and quality evidence."""

    selected = rankings["lineup_tier"].isin(
        ["PROVISIONAL_STARTER", "PROVISIONAL_FLEX"]
    )
    rows: list[tuple[str, Any]] = [
        ("run_timestamp_utc", run_timestamp),
        ("ranking_commit", ranking_commit),
        ("ranking_version", configuration["rankings"]["version"]),
        (
            "ranking_configuration_sha256",
            sha256_file(configuration_path),
        ),
        ("prediction_input_sha256", input_hashes["predictions"]),
        ("feature_input_sha256", input_hashes["features"]),
        ("depth_snapshot_sha256", input_hashes["depth_snapshot"]),
        ("maximum_depth_timestamp", maximum_depth_timestamp.isoformat()),
        ("output_rows", len(rankings)),
        ("output_columns", len(rankings.columns)),
        ("candidate_teams", rankings["team"].nunique()),
        ("candidate_games", rankings["game_id"].nunique()),
        (
            "position_counts",
            json.dumps(
                rankings["position"].value_counts().sort_index().to_dict(),
                sort_keys=True,
            ),
        ),
        (
            "role_eligible_counts",
            json.dumps(
                rankings.loc[rankings["role_eligible"], "position"]
                .value_counts()
                .sort_index()
                .to_dict(),
                sort_keys=True,
            ),
        ),
        ("projected_lineup_rows", int(selected.sum())),
        (
            "projected_lineup_slot_counts",
            json.dumps(
                rankings.loc[selected, "projected_lineup_slot"]
                .value_counts()
                .sort_index()
                .to_dict(),
                sort_keys=True,
            ),
        ),
        (
            "projected_lineup_confidence_counts",
            json.dumps(
                rankings.loc[selected, "evidence_confidence"]
                .value_counts()
                .sort_index()
                .to_dict(),
                sort_keys=True,
            ),
        ),
        (
            "raw_negative_projection_rows",
            int(rankings["projected_fantasy_points_ppr"].lt(0).sum()),
        ),
        (
            "depth_position_mismatch_rows",
            int(
                (~rankings[
                    "depth_position_matches_model_position"
                ]).sum()
            ),
        ),
        (
            "display_floored_projection_rows",
            int(
                rankings["display_projected_fantasy_points_ppr"].ne(
                    rankings["projected_fantasy_points_ppr"]
                ).sum()
            ),
        ),
        ("injury_report_rows", 0),
        (
            "injury_context_status",
            configuration["rankings"]["injury_context_status"],
        ),
        (
            "duplicate_keys",
            int(
                rankings.duplicated(
                    ["season", "week", "player_id"]
                ).sum()
            ),
        ),
        (
            "unavailable_keys",
            unavailable_rows(rankings, ["season", "week", "player_id"]),
        ),
        (
            "rankings_parquet_path",
            display_path(paths["rankings_parquet_template"]),
        ),
        (
            "rankings_parquet_sha256",
            sha256_file(paths["rankings_parquet_template"]),
        ),
        (
            "rankings_csv_path",
            display_path(paths["rankings_csv_template"]),
        ),
        (
            "rankings_csv_sha256",
            sha256_file(paths["rankings_csv_template"]),
        ),
        ("ranking_status", "PASS_WITH_INJURY_CAVEAT"),
    ]
    return pd.DataFrame(rows, columns=["manifest_key", "manifest_value"])


def json_rows(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a bounded dataframe to strict JSON-safe row dictionaries."""

    safe = dataframe.copy()
    for column in safe.columns:
        if pd.api.types.is_datetime64_any_dtype(safe[column]):
            safe[column] = safe[column].astype("string")
    safe = safe.astype(object).where(pd.notna(safe), None)
    return json.loads(safe.to_json(orient="records", force_ascii=False))


def build_report_artifact(
    rankings: pd.DataFrame,
    configuration: dict[str, Any],
    paths: dict[str, Path],
    run_timestamp: str,
) -> dict[str, Any]:
    """Create the canonical portable-report artifact payload."""

    selected = rankings.loc[
        rankings["lineup_tier"].isin(
            ["PROVISIONAL_STARTER", "PROVISIONAL_FLEX"]
        )
    ].copy()
    role_eligible = int(rankings["role_eligible"].sum())
    negative_rows = int(
        rankings["projected_fantasy_points_ppr"].lt(0).sum()
    )
    confidence_counts = (
        selected["evidence_confidence"].value_counts().to_dict()
    )
    all_high = confidence_counts == {"HIGH": len(selected)}

    cutline_rows: list[dict[str, Any]] = []
    for position in ["QB", "RB", "WR", "TE"]:
        position_selected = selected.loc[
            selected["projected_lineup_slot"].eq(position)
        ]
        position_eligible = rankings.loc[
            rankings["position"].eq(position)
            & rankings["role_eligible"]
        ]
        cutline_rows.extend(
            [
                {
                    "position": position,
                    "series": "Highest projection",
                    "projected_points": round(
                        float(
                            position_eligible[
                                "projected_fantasy_points_ppr"
                            ].max()
                        ),
                        2,
                    ),
                },
                {
                    "position": position,
                    "series": "Starter cutline",
                    "projected_points": round(
                        float(
                            position_selected[
                                "projected_fantasy_points_ppr"
                            ].min()
                        ),
                        2,
                    ),
                },
            ]
        )

    detail_columns = [
        "player_display_name",
        "position",
        "team",
        "opponent",
        "projected_fantasy_points_ppr",
        "position_rank",
        "projected_lineup_slot",
        "depth_rank",
        "evidence_confidence",
        "risk_flags",
    ]
    details = selected.sort_values(
        ["projected_fantasy_points_ppr", "player_id"],
        ascending=[False, True],
        kind="stable",
    )[detail_columns]

    source_id = "weekly_rankings_output"
    rankings_csv_path = display_path(paths["rankings_csv_template"])
    source = {
        "id": source_id,
        "label": "Frozen 2026 Week 1 weekly rankings",
        "path": rankings_csv_path,
        "query": {
            "engine": "duckdb",
            "language": "sql",
            "sql": (
                "SELECT * FROM read_csv_auto("
                f"'{rankings_csv_path}', header = true)"
            ),
            "description": (
                "Loads the reviewed ranking output produced by the Python "
                "league-demand and depth-eligibility workflow."
            ),
            "executed_at": run_timestamp,
            "tables_used": [
                display_path(paths["predictions_template"]),
                display_path(paths["features_template"]),
                display_path(paths["depth_snapshot_template"]),
                display_path(paths["league_settings_path"]),
            ],
            "filters": [
                "Season 2026, Week 1",
                "Positions QB, RB, WR, and TE",
                "Depth eligibility QB 1, RB 1-3, WR 1-3, TE 1-2",
                "12-team full-PPR lineup demand",
            ],
            "metric_definitions": [
                "Projected lineup rows are 72 fixed-position starters plus 12 FLEX players.",
                "Display projection is the raw model projection floored at zero; raw projection remains available.",
                "Evidence confidence uses prior games, days since last game, and prior snap coverage.",
            ],
        },
    }

    high_sentence = (
        "All 84 projected lineup rows meet the configured high historical-"
        "evidence threshold."
        if all_high
        else "Projected lineup rows span multiple historical-evidence levels."
    )
    leader_lines = []
    for position in ["QB", "RB", "WR", "TE"]:
        leaders = (
            selected.loc[selected["position"].eq(position)]
            .sort_values(
                ["projected_fantasy_points_ppr", "player_id"],
                ascending=[False, True],
                kind="stable",
            )
            .head(5)
        )
        formatted = ", ".join(
            f"{row.player_display_name} "
            f"({row.projected_fantasy_points_ppr:.2f})"
            for row in leaders.itertuples()
        )
        leader_lines.append(f"- **{position}:** {formatted}")
    leaders_markdown = "\n".join(leader_lines)
    starter_cutline_chart_rows = [
        row for row in cutline_rows if row["series"] == "Starter cutline"
    ]
    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "2026 Week 1 Projection Rankings",
            "description": (
                "Provisional 12-team full-PPR position and FLEX rankings "
                "from the frozen Version 1 model bundle."
            ),
            "generatedAt": run_timestamp,
            "cards": [
                {
                    "id": "candidate_count",
                    "description": "Active-roster, depth-matched QB/RB/WR/TE candidates scored by the frozen bundle.",
                    "dataset": "summary",
                    "sourceId": source_id,
                    "metrics": [
                        {
                            "label": "Projected candidates",
                            "field": "candidate_rows",
                            "format": "number",
                        }
                    ],
                },
                {
                    "id": "role_eligible_count",
                    "description": "Candidates inside the configured depth-rank eligibility limits.",
                    "dataset": "summary",
                    "sourceId": source_id,
                    "metrics": [
                        {
                            "label": "Role-eligible players",
                            "field": "role_eligible_rows",
                            "format": "number",
                        }
                    ],
                },
                {
                    "id": "lineup_count",
                    "description": "Twelve complete league lineups: fixed position demand plus FLEX.",
                    "dataset": "summary",
                    "sourceId": source_id,
                    "metrics": [
                        {
                            "label": "Projected lineup slots",
                            "field": "projected_lineup_rows",
                            "format": "number",
                        }
                    ],
                },
                {
                    "id": "negative_count",
                    "description": "Raw ridge outputs below zero; display values are floored without altering the raw score.",
                    "dataset": "summary",
                    "sourceId": source_id,
                    "metrics": [
                        {
                            "label": "Raw negative projections",
                            "field": "raw_negative_rows",
                            "format": "number",
                        }
                    ],
                },
            ],
            "charts": [
                {
                    "id": "starter_cutlines",
                    "title": "Starter cutline by position",
                    "subtitle": "Final fixed-position starter in a 12-team full-PPR player pool.",
                    "type": "bar",
                    "dataset": "starter_cutline_chart",
                    "sourceId": source_id,
                    "valueFormat": "number",
                    "encodings": {
                        "x": {
                            "field": "position",
                            "type": "nominal",
                            "label": "Position",
                        },
                        "y": {
                            "field": "projected_points",
                            "type": "quantitative",
                            "label": "Projected full-PPR points",
                            "format": "number",
                        },
                    },
                    "yAxisTitle": "Projected full-PPR points",
                    "maxRows": 4,
                }
            ],
            "tables": [],
            "sources": [
                {
                    "id": source_id,
                    "label": source["label"],
                    "path": source["path"],
                }
            ],
            "blocks": [
                {
                    "id": "title",
                    "type": "markdown",
                    "body": "# 2026 Week 1 Projection Rankings",
                },
                {
                    "id": "executive_summary",
                    "type": "markdown",
                    "sourceId": source_id,
                    "body": (
                        "## Executive Summary\n\n"
                        "- **Use these as provisional ranking signals, not final start/sit calls.** "
                        "The frozen model scored 808 candidates, and the decision layer narrowed them to 84 projected lineup slots for a 12-team full-PPR league.\n"
                        f"- **Current role evidence removes conditional-appearance traps.** {role_eligible} players remain after position-specific depth limits; high-scoring deep backups do not displace current role players.\n"
                        f"- **Historical evidence is strong for the selected player pool.** {high_sentence}\n"
                        "- **Availability remains unresolved.** The public 2026 injury feed was unavailable at build time, so every selected row carries an injury-context warning."
                    ),
                },
                {
                    "id": "pool_takeaway",
                    "type": "markdown",
                    "sourceId": source_id,
                    "body": (
                        "## The decision layer narrows a broad model pool\n\n"
                        "The bundle predicts fantasy points conditional on a player appearing, so raw ranking alone can elevate backups. Depth eligibility separates model potential from current lineup plausibility. The resulting 84-player pool exactly fills 12 QB, 24 RB, 24 WR, 12 TE, and 12 FLEX slots."
                    ),
                },
                {
                    "id": "metrics",
                    "type": "metric-strip",
                    "cardIds": [
                        "candidate_count",
                        "role_eligible_count",
                        "lineup_count",
                        "negative_count",
                    ],
                },
                {
                    "id": "cutline_takeaway",
                    "type": "markdown",
                    "body": (
                        "## Position cutlines should guide comparisons within a role\n\n"
                        "Compare players against the starter threshold for their own position, not against one universal point target. The chart shows the final fixed-position starter cutline; FLEX is assigned afterward from the remaining RB, WR, and TE pool."
                    ),
                },
                {
                    "id": "cutline_chart",
                    "type": "chart",
                    "chartId": "starter_cutlines",
                },
                {
                    "id": "position_leaders",
                    "type": "markdown",
                    "sourceId": source_id,
                    "body": (
                        "## The current leaders are a shortlist, not a locked lineup\n\n"
                        "Top five role-eligible raw projections by position:\n\n"
                        f"{leaders_markdown}\n\n"
                        "The tracked CSV preserves all 808 candidates and the full 84-player projected lineup pool. Before kickoff, injury status, late depth changes, and confirmed availability can still move or remove players."
                    ),
                },
                {
                    "id": "next_steps",
                    "type": "markdown",
                    "body": (
                        "## Recommended next steps\n\n"
                        "1. Add and freeze a 2026 injury/availability source when official Week 1 reports become available.\n"
                        "2. Refresh the candidate, feature, inference, and ranking chain under a new timestamped version rather than replacing this snapshot.\n"
                        "3. Calibrate projection floors and ceilings on a separate historical residual set before presenting uncertainty ranges.\n"
                        "4. Backtest the role filter and projected lineup tiers once 2026 outcomes arrive."
                    ),
                },
                {
                    "id": "questions",
                    "type": "markdown",
                    "body": (
                        "## Further questions\n\n"
                        "- Which injury source can be frozen reliably before each game's kickoff?\n"
                        "- Should external consensus rankings be added as a benchmark rather than a model input?\n"
                        "- How should waiver recommendations incorporate league ownership data that is not currently available?"
                    ),
                },
                {
                    "id": "caveats",
                    "type": "markdown",
                    "body": (
                        "## Caveats and assumptions\n\n"
                        "The projections are uncertain and conditional on appearance. Depth charts are a public preseason snapshot and may not reflect final game-day roles. No 2026 injury report was available. Three raw TE predictions are below zero because of stale-history extrapolation; their user-facing display values may be floored at zero while the raw scores remain preserved. Week 1 outcomes are not yet available, so this report validates structure and reasonableness, not forecast accuracy."
                    ),
                },
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": run_timestamp,
            "status": "ready",
            "datasets": {
                "summary": [
                    {
                        "candidate_rows": len(rankings),
                        "role_eligible_rows": role_eligible,
                        "projected_lineup_rows": len(selected),
                        "raw_negative_rows": negative_rows,
                    }
                ],
                "starter_cutlines": cutline_rows,
                "starter_cutline_chart": starter_cutline_chart_rows,
                "projected_lineup": json_rows(details),
            },
        },
        "sources": [source],
        "package_info": {
            "root": "nfl-fantasy-football-advisor",
            "manifestPath": display_path(paths["report_artifact_template"]),
            "snapshotPath": display_path(paths["report_artifact_template"]),
        },
    }


def main() -> None:
    """Run the protected weekly ranking workflow."""

    arguments = parse_arguments()
    config_path = resolve_project_path(arguments.config)
    configuration = load_toml(config_path)
    validate_configuration(configuration, arguments.confirm_build)
    league_settings = load_toml(
        resolve_project_path(configuration["inputs"]["league_settings_path"])
    )
    ranking_commit = require_clean_worktree(configuration)
    paths = build_run_paths(configuration, arguments.season, arguments.week)
    ensure_outputs_available(
        paths,
        configuration["rankings"]["fail_if_output_exists"],
    )

    feature_manifest = load_key_value_manifest(
        paths["feature_manifest_template"]
    )
    inference_manifest = load_key_value_manifest(
        paths["inference_manifest_template"]
    )
    input_hashes = validate_input_hashes(
        paths,
        feature_manifest,
        inference_manifest,
    )
    context = load_projection_context(
        paths,
        configuration,
        arguments.season,
        arguments.week,
    )
    depth, maximum_depth_timestamp = load_current_depth(
        paths["depth_snapshot_template"],
        feature_manifest["as_of_utc"],
        list(configuration["quality"]["supported_positions"]),
    )
    context = attach_depth_context(
        context,
        depth,
        configuration["quality"]["require_all_depth_matches"],
    )
    rankings = assign_rankings(context, configuration, league_settings)
    rankings = finalize_output(
        rankings,
        configuration,
        feature_manifest,
        inference_manifest,
    )

    if rankings["team"].nunique() != configuration["quality"][
        "expected_team_count"
    ]:
        raise ValueError("Ranking candidates do not cover all 32 teams.")
    if rankings["game_id"].nunique() != configuration["quality"][
        "expected_game_count"
    ]:
        raise ValueError("Ranking candidates do not cover all 16 games.")
    validate_frame_keys(
        rankings,
        ["season", "week", "game_id", "player_id"],
        "Rankings",
    )

    run_timestamp = datetime.now(timezone.utc).isoformat()
    atomic_write_parquet(
        rankings,
        paths["rankings_parquet_template"],
    )
    atomic_write_csv(rankings, paths["rankings_csv_template"])
    manifest = build_manifest(
        rankings,
        configuration,
        config_path,
        paths,
        input_hashes,
        ranking_commit,
        run_timestamp,
        maximum_depth_timestamp,
    )
    atomic_write_csv(manifest, paths["manifest_template"])
    artifact = build_report_artifact(
        rankings,
        configuration,
        paths,
        run_timestamp,
    )
    atomic_write_json(artifact, paths["report_artifact_template"])

    reopened = pd.read_parquet(paths["rankings_parquet_template"])
    if len(reopened) != len(rankings):
        raise ValueError("Reopened ranking output has the wrong row count.")
    if sha256_file(paths["rankings_csv_template"]) != dict(
        zip(manifest["manifest_key"], manifest["manifest_value"])
    )["rankings_csv_sha256"]:
        raise ValueError("Reopened ranking CSV hash does not match evidence.")

    selected = rankings["lineup_tier"].isin(
        ["PROVISIONAL_STARTER", "PROVISIONAL_FLEX"]
    )
    print(f"ranking_rows={len(rankings):,}")
    print(f"role_eligible_rows={int(rankings['role_eligible'].sum()):,}")
    print(f"projected_lineup_rows={int(selected.sum()):,}")
    print(
        "projected_lineup_slots="
        + json.dumps(
            rankings.loc[selected, "projected_lineup_slot"]
            .value_counts()
            .sort_index()
            .to_dict(),
            sort_keys=True,
        )
    )
    print(
        "projected_lineup_confidence="
        + json.dumps(
            rankings.loc[selected, "evidence_confidence"]
            .value_counts()
            .sort_index()
            .to_dict(),
            sort_keys=True,
        )
    )
    print(
        "raw_negative_projection_rows="
        f"{int(rankings['projected_fantasy_points_ppr'].lt(0).sum())}"
    )
    print("injury_report_rows=0")
    print("target_column_loaded=False")
    print("ranking_status=PASS_WITH_INJURY_CAVEAT")
    print(
        "rankings_csv=" + display_path(paths["rankings_csv_template"])
    )
    print(
        "report_artifact="
        + display_path(paths["report_artifact_template"])
    )


if __name__ == "__main__":
    main()
