"""Promote one validated weekly ranking snapshot to the public app."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_RANKINGS = PROJECT_ROOT / "results" / "public" / "latest_rankings.csv"
PUBLIC_METADATA = PROJECT_ROOT / "results" / "public" / "latest_run.json"
PUBLIC_COMPLETED_RESULTS = (
    PROJECT_ROOT / "results" / "public" / "completed_week_results.csv"
)

REQUIRED_COLUMNS = {
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
    "position_rank",
    "overall_flex_rank",
    "remaining_flex_rank",
    "projected_lineup_slot",
    "lineup_tier",
    "role_eligible",
    "evidence_confidence",
    "injury_context",
    "risk_flags",
    "recommendation_reason",
    "source_as_of_utc",
    "projection_created_at_utc",
    "projection_source_model",
    "model_bundle_version",
    "ranking_version",
}

ALLOWED_TIERS = {
    "PROVISIONAL_STARTER",
    "PROVISIONAL_FLEX",
    "BENCH_DEPTH",
    "ROLE_FILTERED",
}

COMPLETED_RESULTS_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "player_display_name",
    "position",
    "team",
    "opponent",
    "fantasy_points_ppr",
]
ALLOWED_POSITIONS = {"QB", "RB", "WR", "TE"}


def parse_arguments() -> argparse.Namespace:
    """Parse publication inputs."""

    parser = argparse.ArgumentParser(
        description="Publish one validated weekly rankings snapshot."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument("--rankings")
    parser.add_argument("--manifest")
    parser.add_argument(
        "--completed-results",
        help="Validated display-only actual results produced by history refresh.",
    )
    parser.add_argument("--public-rankings", default=str(PUBLIC_RANKINGS))
    parser.add_argument("--public-metadata", default=str(PUBLIC_METADATA))
    parser.add_argument(
        "--public-completed-results",
        default=str(PUBLIC_COMPLETED_RESULTS),
    )
    return parser.parse_args()


def resolve_project_path(value: str) -> Path:
    """Resolve a path relative to the repository."""

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def sha256_file(path: Path) -> str:
    """Hash one file in bounded blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, str]:
    """Load and validate a two-column key-value manifest."""

    if not path.exists():
        raise FileNotFoundError(f"Ranking manifest not found: {path}")
    manifest = pd.read_csv(path, dtype="string", keep_default_na=False)
    if list(manifest.columns) != ["manifest_key", "manifest_value"]:
        raise ValueError("Ranking manifest has an unexpected schema.")
    if manifest["manifest_key"].duplicated().any():
        raise ValueError("Ranking manifest contains duplicate keys.")
    return dict(zip(manifest["manifest_key"], manifest["manifest_value"]))


def as_boolean(series: pd.Series) -> pd.Series:
    """Normalize serialized booleans without treating text as truthy."""

    normalized = series.astype(str).str.strip().str.lower()
    unexpected = sorted(set(normalized) - {"true", "false"})
    if unexpected:
        raise ValueError(f"Unexpected role_eligible values: {unexpected}")
    return normalized.eq("true")


def validate_publication(
    rankings_path: Path,
    manifest_path: Path,
    season: int,
    week: int,
) -> tuple[pd.DataFrame, dict[str, str], dict[str, Any]]:
    """Validate source lineage, grain, content, and publication status."""

    if not rankings_path.exists():
        raise FileNotFoundError(f"Ranking CSV not found: {rankings_path}")
    manifest = load_manifest(manifest_path)
    required_manifest = {
        "run_timestamp_utc",
        "ranking_version",
        "output_rows",
        "candidate_teams",
        "candidate_games",
        "projected_lineup_rows",
        "injury_context_status",
        "duplicate_keys",
        "unavailable_keys",
        "rankings_csv_sha256",
        "ranking_status",
    }
    missing_manifest = sorted(required_manifest - set(manifest))
    if missing_manifest:
        raise ValueError(
            "Ranking manifest is missing keys: " + ", ".join(missing_manifest)
        )
    if not manifest["ranking_status"].startswith("PASS"):
        raise ValueError("Only a PASS ranking snapshot can be published.")
    if manifest["duplicate_keys"] != "0" or manifest["unavailable_keys"] != "0":
        raise ValueError("Ranking evidence reports invalid keys.")
    observed_hash = sha256_file(rankings_path)
    if observed_hash != manifest["rankings_csv_sha256"]:
        raise ValueError("Ranking CSV hash differs from its manifest.")

    rankings = pd.read_csv(rankings_path, low_memory=False)
    missing_columns = sorted(REQUIRED_COLUMNS - set(rankings.columns))
    if missing_columns:
        raise ValueError(
            "Ranking CSV is missing public columns: "
            + ", ".join(missing_columns)
        )
    if "target_fantasy_points_ppr" in rankings.columns:
        raise ValueError("Observed target outcomes cannot be published.")
    if len(rankings) != int(manifest["output_rows"]):
        raise ValueError("Ranking row count differs from its manifest.")
    if set(pd.to_numeric(rankings["season"], errors="raise")) != {season}:
        raise ValueError("Ranking CSV contains an unexpected season.")
    if set(pd.to_numeric(rankings["week"], errors="raise")) != {week}:
        raise ValueError("Ranking CSV contains an unexpected week.")

    key_columns = ["season", "week", "game_id", "player_id"]
    if rankings[key_columns].isna().any(axis=1).any():
        raise ValueError("Ranking CSV contains unavailable public keys.")
    if rankings.duplicated(key_columns).any():
        raise ValueError("Ranking CSV contains duplicate public keys.")
    unexpected_tiers = sorted(
        set(rankings["lineup_tier"].dropna()) - ALLOWED_TIERS
    )
    if unexpected_tiers:
        raise ValueError(f"Unexpected lineup tiers: {unexpected_tiers}")

    role_eligible = as_boolean(rankings["role_eligible"])
    selected = rankings["lineup_tier"].isin(
        ["PROVISIONAL_STARTER", "PROVISIONAL_FLEX"]
    )
    if not role_eligible.loc[selected].all():
        raise ValueError("A published lineup row is not role eligible.")
    if int(selected.sum()) != int(manifest["projected_lineup_rows"]):
        raise ValueError("Published lineup count differs from its manifest.")
    numeric_projection = pd.to_numeric(
        rankings["display_projected_fantasy_points_ppr"], errors="coerce"
    )
    if numeric_projection.isna().any() or numeric_projection.lt(0).any():
        raise ValueError("Display projections must be finite and nonnegative.")

    summary = {
        "row_count": len(rankings),
        "role_eligible_rows": int(role_eligible.sum()),
        "projected_lineup_rows": int(selected.sum()),
        "team_count": int(rankings["team"].nunique()),
        "game_count": int(rankings["game_id"].nunique()),
        "source_as_of_utc": str(rankings["source_as_of_utc"].iloc[0]),
        "model_bundle_version": str(
            rankings["model_bundle_version"].iloc[0]
        ),
    }
    if summary["team_count"] != int(manifest["candidate_teams"]):
        raise ValueError("Published team coverage differs from the manifest.")
    if summary["game_count"] != int(manifest["candidate_games"]):
        raise ValueError("Published game coverage differs from the manifest.")
    return rankings, manifest, summary


def validate_completed_results(
    path: Path,
    season: int,
    week: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Validate observed results kept separate from projection inputs."""

    if not path.exists():
        raise FileNotFoundError(f"Completed-results CSV not found: {path}")
    completed = pd.read_csv(path, low_memory=False)
    if list(completed.columns) != COMPLETED_RESULTS_COLUMNS:
        raise ValueError("Completed-results CSV has an unexpected schema.")
    if completed.empty:
        raise ValueError("Completed-results CSV is empty.")
    if "target_fantasy_points_ppr" in completed.columns:
        raise ValueError("Model target names cannot appear in public results.")

    integer_seasons = pd.to_numeric(completed["season"], errors="raise")
    integer_weeks = pd.to_numeric(completed["week"], errors="raise")
    if not set(integer_seasons).issubset({season - 1, season}):
        raise ValueError("Completed results contain an unexpected season.")
    current = integer_seasons.eq(season)
    if (integer_weeks.loc[current] >= week).any():
        raise ValueError(
            "Completed results include the projection week or a future week."
        )
    if integer_weeks.lt(1).any() or integer_weeks.gt(18).any():
        raise ValueError("Completed results contain an invalid week.")
    previous_weeks = set(integer_weeks.loc[integer_seasons.eq(season - 1)])
    current_weeks = set(integer_weeks.loc[current])
    if previous_weeks != set(range(1, 19)):
        raise ValueError("Completed results do not cover the prior season.")
    if current_weeks != set(range(1, week)):
        raise ValueError(
            "Completed results do not cover every prior current-season week."
        )

    key_columns = ["season", "week", "game_id", "player_id"]
    display_columns = key_columns + [
        "game_date",
        "player_display_name",
        "position",
        "team",
        "opponent",
    ]
    if completed[display_columns].isna().any(axis=1).any():
        raise ValueError("Completed results contain unavailable display fields.")
    blank = completed[display_columns].astype(str).apply(
        lambda column: column.str.strip().eq("")
    )
    if blank.any(axis=1).any():
        raise ValueError("Completed results contain blank display fields.")
    if completed.duplicated(key_columns).any():
        raise ValueError("Completed results contain duplicate player-game keys.")
    unexpected_positions = sorted(
        set(completed["position"].astype(str)) - ALLOWED_POSITIONS
    )
    if unexpected_positions:
        raise ValueError(
            f"Completed results contain unexpected positions: {unexpected_positions}"
        )
    pd.to_datetime(completed["game_date"], errors="raise")
    actual_points = pd.to_numeric(
        completed["fantasy_points_ppr"], errors="coerce"
    )
    if actual_points.isna().any() or not actual_points.map(math.isfinite).all():
        raise ValueError("Completed PPR points must be finite.")

    latest = completed.sort_values(
        ["season", "week"], ascending=[False, False], kind="stable"
    ).iloc[0]
    summary = {
        "completed_results_rows": len(completed),
        "completed_results_latest_season": int(latest["season"]),
        "completed_results_latest_week": int(latest["week"]),
    }
    return completed, summary


def atomic_copy(source: Path, destination: Path) -> None:
    """Copy a validated file atomically."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.stem}.tmp{destination.suffix}")
    shutil.copyfile(source, temporary)
    os.replace(temporary, destination)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    """Write public metadata atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    with temporary.open("w", encoding="utf-8", newline="\n") as file_handle:
        json.dump(payload, file_handle, indent=2, sort_keys=True)
        file_handle.write("\n")
    os.replace(temporary, path)


def publish(
    rankings_path: Path,
    manifest_path: Path,
    public_rankings: Path,
    public_metadata: Path,
    season: int,
    week: int,
    completed_results_path: Path | None = None,
    public_completed_results: Path | None = None,
) -> dict[str, Any]:
    """Validate and atomically promote one snapshot."""

    _, manifest, summary = validate_publication(
        rankings_path, manifest_path, season, week
    )
    completed_summary: dict[str, Any] = {}
    completed_hash: str | None = None
    if completed_results_path is not None:
        if public_completed_results is None:
            raise ValueError("A public completed-results path is required.")
        _, completed_summary = validate_completed_results(
            completed_results_path, season, week
        )
        completed_hash = sha256_file(completed_results_path)
        completed_summary = {
            **completed_summary,
            "completed_results_sha256": completed_hash,
            "completed_results_path": display_path(public_completed_results),
        }
    if public_rankings.exists() and public_metadata.exists():
        try:
            existing_payload = json.loads(
                public_metadata.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError):
            existing_payload = None
        unchanged_fields = {
            "publication_status": manifest["ranking_status"],
            "season": season,
            "week": week,
            "ranking_version": manifest["ranking_version"],
            "ranking_run_timestamp_utc": manifest["run_timestamp_utc"],
            "injury_context_status": manifest["injury_context_status"],
            "rankings_sha256": manifest["rankings_csv_sha256"],
            **summary,
            **completed_summary,
        }
        completed_unchanged = (
            completed_results_path is None
            or (
                public_completed_results is not None
                and public_completed_results.exists()
                and sha256_file(public_completed_results) == completed_hash
            )
        )
        if (
            isinstance(existing_payload, dict)
            and sha256_file(public_rankings) == manifest["rankings_csv_sha256"]
            and completed_unchanged
            and all(
                existing_payload.get(key) == value
                for key, value in unchanged_fields.items()
            )
        ):
            return existing_payload

    atomic_copy(rankings_path, public_rankings)
    if completed_results_path is not None:
        if public_completed_results is None:
            raise ValueError("A public completed-results path is required.")
        atomic_copy(completed_results_path, public_completed_results)
    payload = {
        "publication_version": "v2_public_snapshot",
        "publication_status": manifest["ranking_status"],
        "published_at_utc": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "week": week,
        "ranking_version": manifest["ranking_version"],
        "ranking_run_timestamp_utc": manifest["run_timestamp_utc"],
        "injury_context_status": manifest["injury_context_status"],
        "rankings_sha256": manifest["rankings_csv_sha256"],
        "rankings_path": display_path(public_rankings),
        "archive_rankings_path": display_path(rankings_path),
        "archive_manifest_path": display_path(manifest_path),
        **summary,
        **completed_summary,
    }
    atomic_write_json(payload, public_metadata)
    if sha256_file(public_rankings) != payload["rankings_sha256"]:
        raise ValueError("Public copy hash does not match validated rankings.")
    if (
        completed_results_path is not None
        and public_completed_results is not None
        and sha256_file(public_completed_results) != completed_hash
    ):
        raise ValueError("Public completed-results copy has an invalid hash.")
    return payload


def main() -> None:
    """Publish the requested season-week snapshot."""

    arguments = parse_arguments()
    rankings_path = resolve_project_path(
        arguments.rankings
        or (
            "results/tables/weekly_rankings_"
            f"{arguments.season}_week_{arguments.week:02d}.csv"
        )
    )
    manifest_path = resolve_project_path(
        arguments.manifest
        or (
            "results/tables/weekly_rankings_"
            f"{arguments.season}_week_{arguments.week:02d}_manifest.csv"
        )
    )
    public_rankings = resolve_project_path(arguments.public_rankings)
    public_metadata = resolve_project_path(arguments.public_metadata)
    completed_results_path = (
        resolve_project_path(arguments.completed_results)
        if arguments.completed_results
        else None
    )
    public_completed_results = resolve_project_path(
        arguments.public_completed_results
    )
    payload = publish(
        rankings_path,
        manifest_path,
        public_rankings,
        public_metadata,
        arguments.season,
        arguments.week,
        completed_results_path,
        public_completed_results,
    )
    print(f"published_season={payload['season']}")
    print(f"published_week={payload['week']}")
    print(f"published_rows={payload['row_count']:,}")
    print(f"publication_status={payload['publication_status']}")
    print(f"public_rankings={display_path(public_rankings)}")
    if completed_results_path is not None:
        print(
            "public_completed_results="
            f"{display_path(public_completed_results)}"
        )
    print(f"public_metadata={display_path(public_metadata)}")


if __name__ == "__main__":
    main()
