"""Build leakage-safe ESPN and Yahoo D/ST weekly projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import nflreadpy as nfl
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFENSIVE_POSITION_GROUPS = {"DB", "DL", "LB"}
SCORING_SOURCE_URLS = {
    "espn": (
        "https://support.espn.com/hc/en-us/articles/"
        "360003914032-Scoring-Formats"
    ),
    "yahoo": "https://help.yahoo.com/kb/SLN6489.html",
}
with (PROJECT_ROOT / "config" / "league_settings.toml").open(
    "rb"
) as scoring_file:
    DST_SCORING = tomllib.load(scoring_file)["dst_scoring"]

DST_RESULT_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "team",
    "opponent",
    "sacks",
    "interceptions",
    "fumble_recoveries",
    "defensive_touchdowns",
    "special_teams_touchdowns",
    "blocked_kicks",
    "safeties",
    "points_allowed",
    "yards_allowed",
    "espn_fantasy_points",
    "yahoo_fantasy_points",
]

DST_RANKING_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "team",
    "opponent",
    "espn_projected_points",
    "espn_rank",
    "espn_projection_method",
    "yahoo_projected_points",
    "yahoo_rank",
    "yahoo_projection_method",
    "history_games",
    "source_as_of_utc",
    "projection_created_at_utc",
    "ranking_version",
]

CANDIDATE_WEIGHTS = {
    "defense_last_3": (1.0, 0.0, 3),
    "defense_last_5": (1.0, 0.0, 5),
    "balanced_last_5": (0.5, 0.5, 5),
    "defense_60_opponent_40": (0.6, 0.4, 5),
    "defense_40_opponent_60": (0.4, 0.6, 5),
    "opponent_last_5": (0.0, 1.0, 5),
}


def parse_arguments() -> argparse.Namespace:
    """Parse D/ST ranking inputs."""

    parser = argparse.ArgumentParser(
        description="Build current ESPN and Yahoo D/ST projections."
    )
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--week", type=int, required=True)
    parser.add_argument(
        "--start-season",
        type=int,
        help="Defaults to three seasons before the target season.",
    )
    parser.add_argument(
        "--as-of",
        help="UTC-aware ISO-8601 source cutoff used for lineage.",
    )
    parser.add_argument("--rankings-output")
    parser.add_argument("--completed-results-output")
    parser.add_argument("--manifest-output")
    arguments = parser.parse_args()
    if not 1 <= arguments.week <= 18:
        parser.error("--week must be between 1 and 18.")
    if arguments.start_season is None:
        arguments.start_season = arguments.season - 3
    if arguments.start_season > arguments.season - 1:
        parser.error("--start-season must include a prior season.")
    return arguments


def resolve_project_path(value: str) -> Path:
    """Resolve one repository-relative path."""

    path = Path(value)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def display_path(path: Path) -> str:
    """Return a repository-relative path where possible."""

    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def parse_as_of(raw_value: str | None) -> datetime:
    """Return an aware UTC source cutoff."""

    if raw_value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("--as-of must include a UTC offset.")
    return parsed.astimezone(timezone.utc)


def sha256_file(path: Path) -> str:
    """Hash one file in bounded blocks."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    """Write CSV without exposing a partial file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.stem}.tmp{path.suffix}")
    dataframe.to_csv(temporary, index=False, lineterminator="\n")
    os.replace(temporary, path)


def require_unique(
    dataframe: pd.DataFrame,
    columns: list[str],
    label: str,
) -> None:
    """Require complete unique keys."""

    if dataframe[columns].isna().any(axis=1).any():
        raise ValueError(f"{label} contains unavailable key values.")
    duplicates = int(dataframe.duplicated(columns).sum())
    if duplicates:
        raise ValueError(f"{label} contains {duplicates} duplicate keys.")


def load_sources(
    start_season: int,
    target_season: int,
    target_week: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Download bounded weekly player statistics and schedules."""

    stat_frames: list[pd.DataFrame] = []
    schedule_frames: list[pd.DataFrame] = []
    for season in range(start_season, target_season + 1):
        print(f"Loading D/ST schedules for {season}...")
        schedule_frames.append(nfl.load_schedules(season).to_pandas())
        if season == target_season and target_week == 1:
            continue
        print(f"Loading D/ST player statistics for {season}...")
        stats = nfl.load_player_stats(
            season, summary_level="week"
        ).to_pandas()
        if season == target_season:
            stats = stats.loc[stats["week"].lt(target_week)].copy()
        stat_frames.append(stats)
    if not stat_frames:
        raise ValueError("No completed D/ST statistics were loaded.")
    return (
        pd.concat(stat_frames, ignore_index=True, sort=False),
        pd.concat(schedule_frames, ignore_index=True, sort=False),
    )


def points_allowed_score(points: float, profile: str) -> float:
    """Score one official default points-allowed band."""

    if profile not in DST_SCORING:
        raise ValueError(f"Unknown D/ST scoring profile: {profile}")
    bands = DST_SCORING[profile]["points_allowed_bands"]
    return float(next(score for maximum, score in bands if points <= maximum))


def yards_allowed_score(yards: float) -> float:
    """Score ESPN's standard total-yards-allowed band."""

    bands = DST_SCORING["espn"]["yards_allowed_bands"]
    return float(next(score for maximum, score in bands if yards <= maximum))


def score_team_games(team_games: pd.DataFrame) -> pd.DataFrame:
    """Apply ESPN and Yahoo default D/ST scoring to team-game facts."""

    scored = team_games.copy()
    common_rules = DST_SCORING["common"]
    common = sum(
        float(common_rules[column]) * scored[column]
        for column in common_rules
    )
    scored["espn_fantasy_points"] = common + scored[
        "points_allowed"
    ].map(lambda value: points_allowed_score(value, "espn")) + scored[
        "yards_allowed"
    ].map(yards_allowed_score)
    scored["yahoo_fantasy_points"] = common + scored[
        "points_allowed"
    ].map(lambda value: points_allowed_score(value, "yahoo"))
    return scored


def build_team_games(
    raw_stats: pd.DataFrame,
    schedules: pd.DataFrame,
) -> pd.DataFrame:
    """Build one completed D/ST fact row per team-game."""

    required_stats = {
        "season",
        "week",
        "season_type",
        "game_id",
        "team",
        "position_group",
        "passing_yards",
        "passing_interceptions",
        "rushing_yards",
        "sack_yards_lost",
        "sacks_suffered",
        "def_sacks",
        "def_interceptions",
        "fumble_recovery_opp",
        "def_tds",
        "fumble_recovery_tds",
        "special_teams_tds",
        "def_safeties",
        "def_punt_blocks",
        "def_pat_blocks",
        "def_fg_blocks",
    }
    missing_stats = sorted(required_stats - set(raw_stats.columns))
    if missing_stats:
        raise ValueError(
            "D/ST player statistics are missing columns: "
            + ", ".join(missing_stats)
        )
    stats = raw_stats.loc[
        raw_stats["season_type"].astype(str).str.upper().eq("REG")
    ].copy()
    numeric_columns = sorted(required_stats - {
        "season_type",
        "game_id",
        "team",
        "position_group",
    })
    for column in numeric_columns:
        stats[column] = pd.to_numeric(stats[column], errors="coerce").fillna(0)
    stats["defensive_fumble_touchdowns"] = stats[
        "fumble_recovery_tds"
    ].where(stats["position_group"].isin(DEFENSIVE_POSITION_GROUPS), 0)
    team_stats = (
        stats.groupby(
            ["season", "week", "game_id", "team"],
            as_index=False,
            sort=False,
        )
        .agg(
            sacks=("def_sacks", "sum"),
            interceptions=("def_interceptions", "sum"),
            fumble_recoveries=("fumble_recovery_opp", "sum"),
            interception_touchdowns=("def_tds", "sum"),
            fumble_touchdowns=("defensive_fumble_touchdowns", "sum"),
            special_teams_touchdowns=("special_teams_tds", "sum"),
            safeties=("def_safeties", "sum"),
            punt_blocks=("def_punt_blocks", "sum"),
            pat_blocks=("def_pat_blocks", "sum"),
            field_goal_blocks=("def_fg_blocks", "sum"),
            passing_yards=("passing_yards", "sum"),
            rushing_yards=("rushing_yards", "sum"),
            sack_yards_lost=("sack_yards_lost", "sum"),
            offensive_interceptions=("passing_interceptions", "sum"),
            sacks_suffered=("sacks_suffered", "sum"),
        )
    )
    team_stats["defensive_touchdowns"] = (
        team_stats["interception_touchdowns"]
        + team_stats["fumble_touchdowns"]
    )
    team_stats["blocked_kicks"] = (
        team_stats["punt_blocks"]
        + team_stats["pat_blocks"]
        + team_stats["field_goal_blocks"]
    )
    team_stats["offensive_yards"] = (
        team_stats["passing_yards"]
        - team_stats["sack_yards_lost"]
        + team_stats["rushing_yards"]
    )
    require_unique(
        team_stats,
        ["season", "week", "game_id", "team"],
        "Aggregated D/ST statistics",
    )

    required_schedule = {
        "season",
        "week",
        "game_type",
        "game_id",
        "gameday",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
    }
    missing_schedule = sorted(required_schedule - set(schedules.columns))
    if missing_schedule:
        raise ValueError(
            "D/ST schedules are missing columns: "
            + ", ".join(missing_schedule)
        )
    completed_schedule = schedules.loc[
        schedules["game_type"].astype(str).str.upper().eq("REG")
        & schedules["home_score"].notna()
        & schedules["away_score"].notna()
    ].copy()
    common = {
        "season": completed_schedule["season"],
        "week": completed_schedule["week"],
        "game_id": completed_schedule["game_id"],
        "game_date": completed_schedule["gameday"],
    }
    home = pd.DataFrame(
        {
            **common,
            "team": completed_schedule["home_team"],
            "opponent": completed_schedule["away_team"],
            "raw_points_allowed": completed_schedule["away_score"],
        }
    )
    away = pd.DataFrame(
        {
            **common,
            "team": completed_schedule["away_team"],
            "opponent": completed_schedule["home_team"],
            "raw_points_allowed": completed_schedule["home_score"],
        }
    )
    team_games = pd.concat([home, away], ignore_index=True)
    require_unique(
        team_games,
        ["season", "week", "game_id", "team"],
        "Completed D/ST schedule",
    )
    facts = team_games.merge(
        team_stats,
        on=["season", "week", "game_id", "team"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    unmatched = int(facts["_merge"].ne("both").sum())
    if unmatched:
        raise ValueError(
            f"D/ST facts have {unmatched} unmatched team-stat rows."
        )
    facts = facts.drop(columns="_merge")
    opponent_context = team_stats.loc[
        :,
        [
            "season",
            "week",
            "game_id",
            "team",
            "defensive_touchdowns",
            "offensive_yards",
            "offensive_interceptions",
            "sacks_suffered",
        ],
    ].rename(
        columns={
            "team": "opponent",
            "defensive_touchdowns": "opponent_defensive_touchdowns",
            "offensive_yards": "yards_allowed",
            "offensive_interceptions": "opponent_interceptions_thrown",
            "sacks_suffered": "opponent_sacks_suffered",
        }
    )
    facts = facts.merge(
        opponent_context,
        on=["season", "week", "game_id", "opponent"],
        how="left",
        validate="one_to_one",
    )
    opponent_columns = [
        "opponent_defensive_touchdowns",
        "yards_allowed",
        "opponent_interceptions_thrown",
        "opponent_sacks_suffered",
    ]
    if facts[opponent_columns].isna().any(axis=1).any():
        raise ValueError("D/ST facts are missing opponent context.")
    if not facts["interceptions"].eq(
        facts["opponent_interceptions_thrown"]
    ).all():
        raise ValueError("D/ST interceptions do not reconcile to the offense.")
    sack_credit_gap = (
        facts["opponent_sacks_suffered"] - facts["sacks"]
    ).round(6)
    if not sack_credit_gap.isin([0.0, 1.0]).all():
        raise ValueError("D/ST sack sources have an unexpected discrepancy.")
    facts["sacks"] = facts["opponent_sacks_suffered"]
    facts["points_allowed"] = (
        pd.to_numeric(facts["raw_points_allowed"], errors="raise")
        - 6 * facts["opponent_defensive_touchdowns"]
    ).clip(lower=0)
    facts["game_date"] = pd.to_datetime(
        facts["game_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    scored = score_team_games(facts)
    scored = scored.loc[:, DST_RESULT_COLUMNS].sort_values(
        ["season", "week", "game_id", "team"], kind="stable"
    )
    numeric = scored[DST_RESULT_COLUMNS[6:]].apply(
        pd.to_numeric, errors="coerce"
    )
    if numeric.isna().any(axis=1).any():
        raise ValueError("D/ST results contain unavailable numeric values.")
    if not numeric.map(math.isfinite).all(axis=None):
        raise ValueError("D/ST results contain non-finite numeric values.")
    return scored.reset_index(drop=True)


def build_target_games(
    schedules: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Expand the target schedule to one row per team-game."""

    target = schedules.loc[
        schedules["season"].eq(season)
        & schedules["week"].eq(week)
        & schedules["game_type"].astype(str).str.upper().eq("REG")
    ].copy()
    if target.empty:
        raise ValueError("No target-week D/ST schedule was found.")
    common = {
        "season": target["season"],
        "week": target["week"],
        "game_id": target["game_id"],
        "game_date": target["gameday"],
    }
    home = pd.DataFrame(
        {
            **common,
            "team": target["home_team"],
            "opponent": target["away_team"],
        }
    )
    away = pd.DataFrame(
        {
            **common,
            "team": target["away_team"],
            "opponent": target["home_team"],
        }
    )
    games = pd.concat([home, away], ignore_index=True)
    games["game_date"] = pd.to_datetime(
        games["game_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    require_unique(
        games,
        ["season", "week", "game_id", "team"],
        "Target D/ST schedule",
    )
    game_sizes = games.groupby("game_id")["team"].nunique()
    if not game_sizes.eq(2).all():
        raise ValueError("A target D/ST game does not contain two teams.")
    return games.sort_values(
        ["game_date", "game_id", "team"], kind="stable"
    ).reset_index(drop=True)


def projection_candidates(
    rows: pd.DataFrame,
    outcome_column: str,
) -> pd.DataFrame:
    """Build strict-prior-game recent-form projection candidates."""

    ordered = rows.sort_values(
        ["game_date", "season", "week", "game_id", "team"],
        kind="stable",
    ).copy()
    ordered["_outcome"] = pd.to_numeric(
        ordered[outcome_column], errors="coerce"
    )
    for window in [3, 5]:
        ordered[f"defense_last_{window}"] = ordered.groupby(
            "team", sort=False
        )["_outcome"].transform(
            lambda values: values.shift(1).rolling(
                window, min_periods=1
            ).mean()
        )
        ordered[f"opponent_last_{window}"] = ordered.groupby(
            "opponent", sort=False
        )["_outcome"].transform(
            lambda values: values.shift(1).rolling(
                window, min_periods=1
            ).mean()
        )
    prior_mean = ordered["_outcome"].expanding().mean().shift(1)
    for column in [
        "defense_last_3",
        "defense_last_5",
        "opponent_last_3",
        "opponent_last_5",
    ]:
        ordered[column] = ordered[column].fillna(prior_mean)
    ordered["balanced_last_5"] = (
        0.5 * ordered["defense_last_5"]
        + 0.5 * ordered["opponent_last_5"]
    )
    ordered["defense_60_opponent_40"] = (
        0.6 * ordered["defense_last_5"]
        + 0.4 * ordered["opponent_last_5"]
    )
    ordered["defense_40_opponent_60"] = (
        0.4 * ordered["defense_last_5"]
        + 0.6 * ordered["opponent_last_5"]
    )
    return ordered


def select_projection_method(
    history: pd.DataFrame,
    outcome_column: str,
    validation_season: int,
) -> tuple[str, dict[str, float]]:
    """Select one candidate using only the fixed validation season."""

    candidates = projection_candidates(history, outcome_column)
    validation = candidates.loc[
        candidates["season"].eq(validation_season)
    ].copy()
    if validation.empty:
        raise ValueError("D/ST validation season is unavailable.")
    metrics: dict[str, float] = {}
    for method in CANDIDATE_WEIGHTS:
        valid = validation[[method, "_outcome"]].dropna()
        if valid.empty:
            raise ValueError(f"D/ST candidate {method} has no validation rows.")
        metrics[method] = float((valid[method] - valid["_outcome"]).abs().mean())
    selected = min(metrics, key=lambda method: (metrics[method], method))
    return selected, metrics


def evaluate_method(
    history: pd.DataFrame,
    outcome_column: str,
    method: str,
    season: int,
) -> dict[str, float | int]:
    """Evaluate one frozen candidate in a later season."""

    candidates = projection_candidates(history, outcome_column)
    tested = candidates.loc[candidates["season"].eq(season)].dropna(
        subset=[method, "_outcome"]
    )
    errors = tested[method] - tested["_outcome"]
    return {
        "rows": len(tested),
        "mae": float(errors.abs().mean()),
        "rmse": float((errors.pow(2).mean()) ** 0.5),
    }


def project_target_week(
    history: pd.DataFrame,
    target_games: pd.DataFrame,
    source_as_of: datetime,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Project both scoring profiles for one target week."""

    validation_season = int(target_games["season"].iloc[0]) - 2
    test_season = int(target_games["season"].iloc[0]) - 1
    rankings = target_games.copy()
    evidence: dict[str, Any] = {
        "validation_season": validation_season,
        "test_season": test_season,
        "profiles": {},
    }
    history_counts = history.groupby("team").size()
    rankings["history_games"] = (
        rankings["team"].map(history_counts).fillna(0).astype(int)
    )
    for profile in ["espn", "yahoo"]:
        outcome = f"{profile}_fantasy_points"
        selected, validation_metrics = select_projection_method(
            history, outcome, validation_season
        )
        placeholder = target_games.copy()
        placeholder[outcome] = pd.NA
        combined = pd.concat(
            [
                history[
                    [
                        "season",
                        "week",
                        "game_id",
                        "game_date",
                        "team",
                        "opponent",
                        outcome,
                    ]
                ],
                placeholder[
                    [
                        "season",
                        "week",
                        "game_id",
                        "game_date",
                        "team",
                        "opponent",
                        outcome,
                    ]
                ],
            ],
            ignore_index=True,
        )
        candidates = projection_candidates(combined, outcome)
        target_keys = set(
            target_games[
                ["season", "week", "game_id", "team"]
            ].itertuples(index=False, name=None)
        )
        candidate_keys = candidates[
            ["season", "week", "game_id", "team"]
        ].apply(tuple, axis=1)
        target_projection = candidates.loc[
            candidate_keys.isin(target_keys),
            ["season", "week", "game_id", "team", selected],
        ].rename(columns={selected: f"{profile}_projected_points"})
        rankings = rankings.merge(
            target_projection,
            on=["season", "week", "game_id", "team"],
            how="left",
            validate="one_to_one",
        )
        projection_column = f"{profile}_projected_points"
        if rankings[projection_column].isna().any():
            raise ValueError(f"{profile.upper()} D/ST projections are missing.")
        rankings[projection_column] = rankings[projection_column].round(2)
        rankings[f"{profile}_rank"] = rankings[
            projection_column
        ].rank(method="first", ascending=False).astype(int)
        rankings[f"{profile}_projection_method"] = selected
        evidence["profiles"][profile] = {
            "selected_method": selected,
            "validation_mae": validation_metrics,
            "test_metrics": evaluate_method(
                history, outcome, selected, test_season
            ),
        }
    created_at = datetime.now(timezone.utc).isoformat()
    rankings["source_as_of_utc"] = source_as_of.isoformat()
    rankings["projection_created_at_utc"] = created_at
    rankings["ranking_version"] = "v1_dst_recent_form"
    rankings = rankings.loc[:, DST_RANKING_COLUMNS].sort_values(
        ["espn_rank", "team"], kind="stable"
    )
    require_unique(
        rankings,
        ["season", "week", "game_id", "team"],
        "D/ST rankings",
    )
    return rankings.reset_index(drop=True), evidence


def build_manifest(
    rankings: pd.DataFrame,
    completed_results: pd.DataFrame,
    evidence: dict[str, Any],
    start_season: int,
    rankings_path: Path,
    completed_results_path: Path,
) -> pd.DataFrame:
    """Build compact D/ST lineage and quality evidence."""

    rows = [
        ("run_timestamp_utc", datetime.now(timezone.utc).isoformat()),
        ("ranking_version", "v1_dst_recent_form"),
        ("start_season", start_season),
        ("target_season", int(rankings["season"].iloc[0])),
        ("target_week", int(rankings["week"].iloc[0])),
        ("output_rows", len(rankings)),
        ("candidate_teams", rankings["team"].nunique()),
        ("candidate_games", rankings["game_id"].nunique()),
        ("duplicate_keys", int(rankings.duplicated([
            "season", "week", "game_id", "team"
        ]).sum())),
        ("unavailable_keys", int(rankings[
            ["season", "week", "game_id", "team"]
        ].isna().any(axis=1).sum())),
        ("selection_evidence", json.dumps(evidence, sort_keys=True)),
        ("scoring_sources", json.dumps(SCORING_SOURCE_URLS, sort_keys=True)),
        (
            "scoring_config_sha256",
            sha256_file(PROJECT_ROOT / "config" / "league_settings.toml"),
        ),
        ("rankings_csv_sha256", sha256_file(rankings_path)),
        ("completed_results_rows", len(completed_results)),
        (
            "completed_results_csv_sha256",
            sha256_file(completed_results_path),
        ),
        ("ranking_status", "PASS"),
    ]
    return pd.DataFrame(rows, columns=["manifest_key", "manifest_value"])


def main() -> None:
    """Build and archive one target-week D/ST snapshot."""

    arguments = parse_arguments()
    source_as_of = parse_as_of(arguments.as_of)
    prefix = f"{arguments.season}_week_{arguments.week:02d}"
    rankings_path = resolve_project_path(
        arguments.rankings_output
        or f"results/tables/dst_rankings_{prefix}.csv"
    )
    completed_results_path = resolve_project_path(
        arguments.completed_results_output
        or "data/processed/runtime_history/completed_dst_results.csv"
    )
    manifest_path = resolve_project_path(
        arguments.manifest_output
        or f"results/tables/dst_rankings_{prefix}_manifest.csv"
    )
    if rankings_path.exists() or manifest_path.exists():
        raise FileExistsError(
            "Immutable D/ST ranking evidence already exists for this week."
        )

    raw_stats, schedules = load_sources(
        arguments.start_season,
        arguments.season,
        arguments.week,
    )
    history = build_team_games(raw_stats, schedules)
    history = history.loc[
        (history["season"].lt(arguments.season))
        | (
            history["season"].eq(arguments.season)
            & history["week"].lt(arguments.week)
        )
    ].copy()
    target_games = build_target_games(
        schedules, arguments.season, arguments.week
    )
    rankings, evidence = project_target_week(
        history, target_games, source_as_of
    )
    completed_results = history.loc[
        history["season"].between(
            arguments.season - 1, arguments.season
        ),
        DST_RESULT_COLUMNS,
    ].reset_index(drop=True)

    atomic_write_csv(rankings, rankings_path)
    atomic_write_csv(completed_results, completed_results_path)
    manifest = build_manifest(
        rankings,
        completed_results,
        evidence,
        arguments.start_season,
        rankings_path,
        completed_results_path,
    )
    atomic_write_csv(manifest, manifest_path)
    print(f"dst_rankings_rows={len(rankings):,}")
    print(f"completed_dst_rows={len(completed_results):,}")
    print(f"dst_rankings={display_path(rankings_path)}")
    print(f"completed_dst_results={display_path(completed_results_path)}")
    print(f"dst_manifest={display_path(manifest_path)}")
    print("dst_ranking_status=PASS")


if __name__ == "__main__":
    main()
