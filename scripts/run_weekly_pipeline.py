"""Orchestrate one protected weekly projection and publication run."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import nflreadpy as nfl
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAYER_HISTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "runtime_history"
    / "player_game_history.parquet"
)
OPPONENT_HISTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "runtime_history"
    / "opponent_position_week_history.parquet"
)
COMPLETED_RESULTS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "runtime_history"
    / "completed_week_results.csv"
)
PUBLIC_COMPLETED_RESULTS = (
    PROJECT_ROOT / "results" / "public" / "completed_week_results.csv"
)


def parse_arguments() -> argparse.Namespace:
    """Parse weekly orchestration options."""

    parser = argparse.ArgumentParser(
        description=(
            "Refresh completed history, build target-week features, score "
            "the frozen bundle, rank players, and publish the validated app "
            "snapshot."
        )
    )
    parser.add_argument("--season", type=int, required=True)
    week = parser.add_mutually_exclusive_group(required=True)
    week.add_argument("--week", type=int)
    week.add_argument(
        "--auto-week",
        action="store_true",
        help="Resolve the current/upcoming regular-season week from schedule.",
    )
    parser.add_argument(
        "--as-of",
        help="UTC-aware ISO-8601 source cutoff; defaults to the run start.",
    )
    parser.add_argument(
        "--history-source-mode",
        choices=["download", "existing"],
        default="download",
    )
    parser.add_argument(
        "--publish-existing",
        action="store_true",
        help=(
            "Skip all scoring stages and promote an already validated weekly "
            "ranking snapshot."
        ),
    )
    arguments = parser.parse_args()
    if arguments.week is not None and not 1 <= arguments.week <= 18:
        parser.error("--week must be between 1 and 18.")
    return arguments


def run_git(*arguments: str) -> str:
    """Run one read-only Git command."""

    completed = subprocess.run(
        ["git", *arguments],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def require_clean_start() -> str:
    """Freeze one committed revision before generated outputs appear."""

    status = run_git("status", "--porcelain")
    if status:
        raise RuntimeError(
            "The weekly pipeline must start from a clean worktree. Commit "
            "application and pipeline changes before running it."
        )
    return run_git("rev-parse", "HEAD")


def parse_as_of(raw_value: str | None) -> datetime:
    """Return an aware UTC cutoff."""

    if raw_value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--as-of must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def resolve_target_week(season: int, as_of: datetime) -> int:
    """Choose the regular-season week still containing an unplayed date."""

    schedule = nfl.load_schedules(season).to_pandas()
    required = {"season", "game_type", "week", "gameday"}
    missing = sorted(required - set(schedule.columns))
    if missing:
        raise ValueError(f"Schedule is missing columns: {missing}")
    schedule = schedule.loc[
        schedule["season"].eq(season)
        & schedule["game_type"].astype(str).str.upper().eq("REG")
    ].copy()
    schedule["gameday"] = pd.to_datetime(
        schedule["gameday"], errors="raise"
    ).dt.date
    eligible = schedule.loc[schedule["gameday"] >= as_of.date()]
    if eligible.empty:
        raise ValueError(
            f"No current or upcoming regular-season week remains for {season}."
        )
    target_week = int(eligible["week"].min())
    print(f"auto_resolved_week={target_week}")
    return target_week


def run_command(arguments: list[str]) -> None:
    """Run one pipeline stage and stream its output."""

    relative = [
        str(Path(value).relative_to(PROJECT_ROOT))
        if Path(value).is_absolute()
        and Path(value).resolve().is_relative_to(PROJECT_ROOT)
        else value
        for value in arguments
    ]
    print("\n> " + " ".join(relative), flush=True)
    subprocess.run(arguments, cwd=PROJECT_ROOT, check=True)


def publish_command(
    season: int,
    week: int,
    completed_results: Path | None = None,
) -> list[str]:
    """Return the validated-publication command."""

    command = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "publish_latest.py"),
        "--season",
        str(season),
        "--week",
        str(week),
    ]
    if completed_results is not None:
        command.extend(
            ["--completed-results", str(completed_results)]
        )
    return command


def output_paths(season: int, week: int) -> dict[str, Path]:
    """Return the immutable paths shared by weekly stages."""

    prefix = f"{season}_week_{week:02d}"
    return {
        "features": (
            PROJECT_ROOT
            / "data"
            / "processed"
            / "future_features"
            / f"{prefix}_features.parquet"
        ),
        "predictions": (
            PROJECT_ROOT
            / "data"
            / "processed"
            / "inference"
            / f"{prefix}_projections.parquet"
        ),
        "inference_manifest": (
            PROJECT_ROOT
            / "results"
            / "tables"
            / f"inference_{prefix}_manifest.csv"
        ),
        "rankings_csv": (
            PROJECT_ROOT
            / "results"
            / "tables"
            / f"weekly_rankings_{prefix}.csv"
        ),
        "rankings_manifest": (
            PROJECT_ROOT
            / "results"
            / "tables"
            / f"weekly_rankings_{prefix}_manifest.csv"
        ),
    }


def main() -> None:
    """Run one all-or-nothing weekly publication attempt."""

    arguments = parse_arguments()
    as_of = parse_as_of(arguments.as_of)
    week = (
        resolve_target_week(arguments.season, as_of)
        if arguments.auto_week
        else int(arguments.week)
    )
    if arguments.publish_existing:
        run_command(
            publish_command(
                arguments.season, week, PUBLIC_COMPLETED_RESULTS
            )
        )
        return

    paths = output_paths(arguments.season, week)
    if paths["rankings_csv"].exists() or paths["rankings_manifest"].exists():
        if not (
            paths["rankings_csv"].exists()
            and paths["rankings_manifest"].exists()
        ):
            raise RuntimeError(
                "Only part of the archived ranking evidence exists for the "
                "target week. Repair the archive before automation continues."
            )
        run_command(
            publish_command(
                arguments.season, week, PUBLIC_COMPLETED_RESULTS
            )
        )
        print("weekly_pipeline_status=ALREADY_PUBLISHED")
        return

    revision = require_clean_start()
    print(f"orchestrated_revision={revision}")
    print(f"target_season={arguments.season}")
    print(f"target_week={week}")
    print(f"as_of_utc={as_of.isoformat()}")

    refresh_manifest = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / f"history_refresh_{arguments.season}_through_week_{week - 1:02d}_manifest.csv"
    )
    run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "refresh_weekly_history.py"),
            "--season",
            str(arguments.season),
            "--through-week",
            str(week - 1),
            "--source-mode",
            arguments.history_source_mode,
            "--player-output",
            str(PLAYER_HISTORY),
            "--opponent-output",
            str(OPPONENT_HISTORY),
            "--completed-results-output",
            str(COMPLETED_RESULTS),
            "--manifest-output",
            str(refresh_manifest),
        ]
    )
    run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_future_features.py"),
            "--live",
            "--season",
            str(arguments.season),
            "--week",
            str(week),
            "--as-of",
            as_of.isoformat(),
            "--player-history",
            str(PLAYER_HISTORY),
            "--opponent-history",
            str(OPPONENT_HISTORY),
            "--confirm-build",
            "BUILD_V1_FUTURE_FEATURES",
            "--orchestrated-revision",
            revision,
        ]
    )
    run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "predict_with_bundle.py"),
            "--input",
            str(paths["features"]),
            "--output",
            str(paths["predictions"]),
            "--manifest-output",
            str(paths["inference_manifest"]),
            "--confirm-inference",
            "RUN_V1_BUNDLE_INFERENCE",
            "--orchestrated-revision",
            revision,
        ]
    )
    run_command(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build_weekly_rankings.py"),
            "--season",
            str(arguments.season),
            "--week",
            str(week),
            "--confirm-build",
            "BUILD_V1_WEEKLY_RANKINGS",
            "--orchestrated-revision",
            revision,
        ]
    )
    run_command(
        publish_command(
            arguments.season, week, COMPLETED_RESULTS
        )
    )
    print("weekly_pipeline_status=PASS")


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    main()
