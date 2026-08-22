"""Build leakage-safe ESPN and Yahoo weekly kicker projections."""

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
SETTINGS_PATH = PROJECT_ROOT / "config" / "kicker_settings.toml"
with SETTINGS_PATH.open("rb") as settings_file:
    KICKER_SETTINGS = tomllib.load(settings_file)
KICKER_SCORING = KICKER_SETTINGS["kicker_scoring"]

TEAM_ALIASES = {
    "AZ": "ARI",
    "ARZ": "ARI",
    "JAC": "JAX",
    "OAK": "LV",
    "SD": "LAC",
    "STL": "LA",
}

KICKER_RESULT_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "player_display_name",
    "position",
    "team",
    "opponent",
    "field_goals_made",
    "field_goals_attempted",
    "field_goals_missed",
    "field_goals_blocked",
    "field_goals_made_0_19",
    "field_goals_made_20_29",
    "field_goals_made_30_39",
    "field_goals_made_40_49",
    "field_goals_made_50_59",
    "field_goals_made_60_plus",
    "extra_points_made",
    "extra_points_attempted",
    "extra_points_missed",
    "extra_points_blocked",
    "espn_fantasy_points",
    "yahoo_fantasy_points",
]

KICKER_RANKING_COLUMNS = [
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "player_display_name",
    "position",
    "team",
    "opponent",
    "selection_status",
    "espn_projected_points",
    "espn_rank",
    "espn_projection_method",
    "yahoo_projected_points",
    "yahoo_rank",
    "yahoo_projection_method",
    "team_history_games",
    "player_history_games",
    "source_as_of_utc",
    "projection_created_at_utc",
    "ranking_version",
]

CANDIDATE_METHODS = [
    "team_last_3",
    "team_last_5",
    "balanced_last_5",
    "team_60_opponent_40",
    "team_40_opponent_60",
    "opponent_last_5",
]


def parse_arguments() -> argparse.Namespace:
    """Parse kicker ranking inputs."""

    parser = argparse.ArgumentParser(
        description="Build current ESPN and Yahoo kicker projections."
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
        help="UTC-aware ISO-8601 source cutoff used for depth-chart selection.",
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
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Download bounded statistics, schedules, roster, and depth charts."""

    stat_frames: list[pd.DataFrame] = []
    schedule_frames: list[pd.DataFrame] = []
    for season in range(start_season, target_season + 1):
        print(f"Loading kicker schedules for {season}...")
        schedule_frames.append(nfl.load_schedules(season).to_pandas())
        if season == target_season and target_week == 1:
            continue
        print(f"Loading kicker statistics for {season}...")
        stats = nfl.load_player_stats(
            season, summary_level="week"
        ).to_pandas()
        if season == target_season:
            stats = stats.loc[stats["week"].lt(target_week)].copy()
        stat_frames.append(stats)
    if not stat_frames:
        raise ValueError("No completed kicker statistics were loaded.")
    print(f"Loading current kicker roster and depth charts for {target_season}...")
    roster = nfl.load_rosters(target_season).to_pandas()
    depth = nfl.load_depth_charts(target_season).to_pandas()
    return (
        pd.concat(stat_frames, ignore_index=True, sort=False),
        pd.concat(schedule_frames, ignore_index=True, sort=False),
        roster,
        depth,
    )


def score_kicker_games(kicker_games: pd.DataFrame) -> pd.DataFrame:
    """Apply the official ESPN and Yahoo default kicker profiles."""

    scored = kicker_games.copy()
    source_columns = {
        "field_goal_0_19": "field_goals_made_0_19",
        "field_goal_20_29": "field_goals_made_20_29",
        "field_goal_30_39": "field_goals_made_30_39",
        "field_goal_40_49": "field_goals_made_40_49",
        "field_goal_50_59": "field_goals_made_50_59",
        "field_goal_60_plus": "field_goals_made_60_plus",
        "extra_point_made": "extra_points_made",
        "field_goal_missed": "field_goals_missed",
    }
    for profile in ["espn", "yahoo"]:
        rules = KICKER_SCORING[profile]
        scored[f"{profile}_fantasy_points"] = sum(
            float(rules[rule]) * scored[column]
            for rule, column in source_columns.items()
        )
    return scored


def build_kicker_games(
    raw_stats: pd.DataFrame,
    schedules: pd.DataFrame,
) -> pd.DataFrame:
    """Build one observed kicker-player row per completed team-game."""

    source_mapping = {
        "fg_made": "field_goals_made",
        "fg_att": "field_goals_attempted",
        "fg_missed": "field_goals_missed",
        "fg_blocked": "field_goals_blocked",
        "fg_made_0_19": "field_goals_made_0_19",
        "fg_made_20_29": "field_goals_made_20_29",
        "fg_made_30_39": "field_goals_made_30_39",
        "fg_made_40_49": "field_goals_made_40_49",
        "fg_made_50_59": "field_goals_made_50_59",
        "fg_made_60_": "field_goals_made_60_plus",
        "pat_made": "extra_points_made",
        "pat_att": "extra_points_attempted",
        "pat_missed": "extra_points_missed",
        "pat_blocked": "extra_points_blocked",
    }
    required = {
        "season",
        "week",
        "season_type",
        "game_id",
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent_team",
        *source_mapping,
    }
    missing = sorted(required - set(raw_stats.columns))
    if missing:
        raise ValueError(
            "Kicker statistics are missing columns: " + ", ".join(missing)
        )
    kickers = raw_stats.loc[
        raw_stats["season_type"].astype(str).str.upper().eq("REG")
        & raw_stats["position"].astype(str).str.upper().eq("K")
    ].copy()
    kickers = kickers.rename(columns=source_mapping)
    numeric_columns = list(source_mapping.values())
    for column in numeric_columns:
        kickers[column] = pd.to_numeric(
            kickers[column], errors="coerce"
        ).fillna(0)
    kickers["team"] = kickers["team"].replace(TEAM_ALIASES)
    kickers["opponent"] = kickers["opponent_team"].replace(TEAM_ALIASES)
    distance_total = kickers[
        [
            "field_goals_made_0_19",
            "field_goals_made_20_29",
            "field_goals_made_30_39",
            "field_goals_made_40_49",
            "field_goals_made_50_59",
            "field_goals_made_60_plus",
        ]
    ].sum(axis=1)
    if not distance_total.eq(kickers["field_goals_made"]).all():
        raise ValueError("Kicker field-goal distance buckets do not reconcile.")
    field_goal_attempts = (
        kickers["field_goals_made"]
        + kickers["field_goals_missed"]
        + kickers["field_goals_blocked"]
    )
    if not field_goal_attempts.eq(kickers["field_goals_attempted"]).all():
        raise ValueError("Kicker field-goal attempts do not reconcile.")
    extra_point_attempts = (
        kickers["extra_points_made"]
        + kickers["extra_points_missed"]
        + kickers["extra_points_blocked"]
    )
    if not extra_point_attempts.eq(kickers["extra_points_attempted"]).all():
        raise ValueError("Kicker extra-point attempts do not reconcile.")

    schedule_dates = schedules.loc[
        schedules["game_type"].astype(str).str.upper().eq("REG")
        & schedules["home_score"].notna()
        & schedules["away_score"].notna(),
        ["season", "week", "game_id", "gameday"],
    ].drop_duplicates(["season", "week", "game_id"])
    kickers = kickers.merge(
        schedule_dates,
        on=["season", "week", "game_id"],
        how="inner",
        validate="many_to_one",
    )
    kickers["game_date"] = pd.to_datetime(
        kickers["gameday"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    kickers["position"] = "K"
    require_unique(
        kickers,
        ["season", "week", "game_id", "player_id"],
        "Completed kicker results",
    )
    if kickers.duplicated(["season", "week", "game_id", "team"]).any():
        raise ValueError("Multiple kickers are recorded for one team-game.")
    scored = score_kicker_games(kickers)
    results = scored.loc[:, KICKER_RESULT_COLUMNS].sort_values(
        ["season", "week", "game_id", "team"], kind="stable"
    )
    values = results[KICKER_RESULT_COLUMNS[9:]].apply(
        pd.to_numeric, errors="coerce"
    )
    if values.isna().any(axis=1).any() or not values.map(math.isfinite).all(
        axis=None
    ):
        raise ValueError("Kicker results contain invalid numeric values.")
    if values.iloc[:, :-2].lt(0).any(axis=1).any():
        raise ValueError("Kicker event totals cannot be negative.")
    return results.reset_index(drop=True)


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
        raise ValueError("No target-week kicker schedule was found.")
    common = {
        "season": target["season"],
        "week": target["week"],
        "game_id": target["game_id"],
        "game_date": target["gameday"],
    }
    games = pd.concat(
        [
            pd.DataFrame(
                {
                    **common,
                    "team": target["home_team"],
                    "opponent": target["away_team"],
                }
            ),
            pd.DataFrame(
                {
                    **common,
                    "team": target["away_team"],
                    "opponent": target["home_team"],
                }
            ),
        ],
        ignore_index=True,
    )
    games["team"] = games["team"].replace(TEAM_ALIASES)
    games["opponent"] = games["opponent"].replace(TEAM_ALIASES)
    games["game_date"] = pd.to_datetime(
        games["game_date"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    require_unique(
        games,
        ["season", "week", "game_id", "team"],
        "Target kicker schedule",
    )
    if not games.groupby("game_id")["team"].nunique().eq(2).all():
        raise ValueError("A target kicker game does not contain two teams.")
    return games.reset_index(drop=True)


def select_target_kickers(
    games: pd.DataFrame,
    roster: pd.DataFrame,
    depth: pd.DataFrame,
    history: pd.DataFrame,
    source_as_of: datetime,
) -> pd.DataFrame:
    """Select one active kicker per scheduled team using latest depth order."""

    required_roster = {
        "team",
        "position",
        "status",
        "full_name",
        "gsis_id",
    }
    required_depth = {"dt", "team", "gsis_id", "pos_abb", "pos_rank", "pos_slot"}
    if required_roster - set(roster):
        raise ValueError("Current roster is missing kicker selection fields.")
    if required_depth - set(depth):
        raise ValueError("Depth chart is missing kicker selection fields.")
    teams = set(games["team"])
    active = roster.loc[
        roster["team"].replace(TEAM_ALIASES).isin(teams)
        & roster["position"].astype(str).str.upper().eq("K")
        & roster["status"].astype(str).str.upper().eq("ACT")
        & roster["gsis_id"].notna()
    ].copy()
    active["team"] = active["team"].replace(TEAM_ALIASES)
    active = active.rename(
        columns={"gsis_id": "player_id", "full_name": "player_display_name"}
    )
    active = active.drop_duplicates(["team", "player_id"])

    depth_rows = depth.copy()
    depth_rows["team"] = depth_rows["team"].replace(TEAM_ALIASES)
    depth_rows["depth_timestamp"] = pd.to_datetime(
        depth_rows["dt"], errors="raise", utc=True
    )
    depth_rows = depth_rows.loc[
        depth_rows["team"].isin(teams)
        & depth_rows["depth_timestamp"].le(source_as_of)
    ].copy()
    latest = depth_rows.groupby("team")["depth_timestamp"].transform("max")
    depth_rows = depth_rows.loc[
        depth_rows["depth_timestamp"].eq(latest)
        & depth_rows["pos_abb"].astype(str).str.upper().eq("PK")
    ].copy()
    depth_rows = depth_rows.rename(columns={"gsis_id": "player_id"})
    depth_rows = depth_rows.sort_values(
        ["team", "pos_rank", "pos_slot", "player_id"], kind="stable"
    ).drop_duplicates(["team", "player_id"])
    active = active.merge(
        depth_rows[
            ["team", "player_id", "pos_rank", "pos_slot", "depth_timestamp"]
        ],
        on=["team", "player_id"],
        how="left",
        validate="one_to_one",
    )
    player_games = history.groupby("player_id").size()
    active["prior_player_games"] = (
        active["player_id"].map(player_games).fillna(0).astype(int)
    )
    active["has_depth_rank"] = active["pos_rank"].notna()
    active = active.sort_values(
        ["team", "has_depth_rank", "pos_rank", "prior_player_games", "player_id"],
        ascending=[True, False, True, False, True],
        kind="stable",
        na_position="last",
    )
    chosen = active.drop_duplicates("team", keep="first").copy()
    missing_teams = sorted(teams - set(chosen["team"]))
    if missing_teams:
        raise ValueError(
            "No active kicker candidate was found for: " + ", ".join(missing_teams)
        )
    chosen["selection_status"] = chosen["has_depth_rank"].map(
        {True: "PRIMARY_DEPTH_CHART", False: "ACTIVE_ROSTER_FALLBACK"}
    )
    selected = games.merge(
        chosen[
            [
                "team",
                "player_id",
                "player_display_name",
                "selection_status",
                "prior_player_games",
            ]
        ],
        on="team",
        how="left",
        validate="one_to_one",
    )
    selected["position"] = "K"
    require_unique(
        selected,
        ["season", "week", "game_id", "player_id"],
        "Target kicker candidates",
    )
    return selected


def projection_candidates(
    rows: pd.DataFrame,
    outcome_column: str,
) -> pd.DataFrame:
    """Build strict-prior recent-form projection candidates."""

    ordered = rows.sort_values(
        ["game_date", "season", "week", "game_id", "team"], kind="stable"
    ).copy()
    ordered["_outcome"] = pd.to_numeric(
        ordered[outcome_column], errors="coerce"
    )
    for window in [3, 5]:
        ordered[f"team_last_{window}"] = ordered.groupby("team", sort=False)[
            "_outcome"
        ].transform(
            lambda values: values.shift(1).rolling(window, min_periods=1).mean()
        )
        ordered[f"opponent_last_{window}"] = ordered.groupby(
            "opponent", sort=False
        )["_outcome"].transform(
            lambda values: values.shift(1).rolling(window, min_periods=1).mean()
        )
    prior_mean = ordered["_outcome"].expanding().mean().shift(1)
    for column in [
        "team_last_3",
        "team_last_5",
        "opponent_last_3",
        "opponent_last_5",
    ]:
        ordered[column] = ordered[column].fillna(prior_mean)
    ordered["balanced_last_5"] = (
        0.5 * ordered["team_last_5"] + 0.5 * ordered["opponent_last_5"]
    )
    ordered["team_60_opponent_40"] = (
        0.6 * ordered["team_last_5"] + 0.4 * ordered["opponent_last_5"]
    )
    ordered["team_40_opponent_60"] = (
        0.4 * ordered["team_last_5"] + 0.6 * ordered["opponent_last_5"]
    )
    return ordered


def select_projection_method(
    history: pd.DataFrame,
    outcome_column: str,
    validation_season: int,
) -> tuple[str, dict[str, float]]:
    """Select one candidate on a fixed validation season."""

    candidates = projection_candidates(history, outcome_column)
    validation = candidates.loc[candidates["season"].eq(validation_season)]
    if validation.empty:
        raise ValueError("Kicker validation season is unavailable.")
    metrics: dict[str, float] = {}
    for method in CANDIDATE_METHODS:
        valid = validation[[method, "_outcome"]].dropna()
        if valid.empty:
            raise ValueError(f"Kicker candidate {method} has no validation rows.")
        metrics[method] = float((valid[method] - valid["_outcome"]).abs().mean())
    selected = min(metrics, key=lambda method: (metrics[method], method))
    return selected, metrics


def evaluate_method(
    history: pd.DataFrame,
    outcome_column: str,
    method: str,
    season: int,
) -> dict[str, float | int]:
    """Evaluate a frozen method in the later test season."""

    candidates = projection_candidates(history, outcome_column)
    tested = candidates.loc[candidates["season"].eq(season)].dropna(
        subset=[method, "_outcome"]
    )
    errors = tested[method] - tested["_outcome"]
    return {
        "rows": len(tested),
        "mae": float(errors.abs().mean()),
        "rmse": float(errors.pow(2).mean() ** 0.5),
    }


def project_target_week(
    history: pd.DataFrame,
    target_kickers: pd.DataFrame,
    source_as_of: datetime,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Project ESPN and Yahoo points for each target-week kicker."""

    target_season = int(target_kickers["season"].iloc[0])
    validation_season = target_season - 2
    test_season = target_season - 1
    rankings = target_kickers.copy()
    team_games = history.groupby("team").size()
    player_games = history.groupby("player_id").size()
    rankings["team_history_games"] = (
        rankings["team"].map(team_games).fillna(0).astype(int)
    )
    rankings["player_history_games"] = (
        rankings["player_id"].map(player_games).fillna(0).astype(int)
    )
    evidence: dict[str, Any] = {
        "validation_season": validation_season,
        "test_season": test_season,
        "profiles": {},
    }
    for profile in ["espn", "yahoo"]:
        outcome = f"{profile}_fantasy_points"
        method, validation_metrics = select_projection_method(
            history, outcome, validation_season
        )
        placeholder = target_kickers[
            ["season", "week", "game_id", "game_date", "team", "opponent"]
        ].copy()
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
                placeholder,
            ],
            ignore_index=True,
        )
        candidates = projection_candidates(combined, outcome)
        target_keys = set(
            target_kickers[
                ["season", "week", "game_id", "team"]
            ].itertuples(index=False, name=None)
        )
        is_target = candidates[
            ["season", "week", "game_id", "team"]
        ].apply(tuple, axis=1).isin(target_keys)
        projected = candidates.loc[
            is_target,
            ["season", "week", "game_id", "team", method],
        ].rename(columns={method: f"{profile}_projected_points"})
        rankings = rankings.merge(
            projected,
            on=["season", "week", "game_id", "team"],
            how="left",
            validate="one_to_one",
        )
        points = f"{profile}_projected_points"
        if rankings[points].isna().any():
            raise ValueError(f"{profile.upper()} kicker projections are missing.")
        rankings[points] = rankings[points].round(2).clip(lower=0)
        rankings[f"{profile}_rank"] = rankings[points].rank(
            method="first", ascending=False
        ).astype(int)
        rankings[f"{profile}_projection_method"] = method
        evidence["profiles"][profile] = {
            "selected_method": method,
            "validation_mae": validation_metrics,
            "test_metrics": evaluate_method(
                history, outcome, method, test_season
            ),
        }
    rankings["source_as_of_utc"] = source_as_of.isoformat()
    rankings["projection_created_at_utc"] = datetime.now(
        timezone.utc
    ).isoformat()
    rankings["ranking_version"] = "v1_kicker_recent_form"
    rankings = rankings.loc[:, KICKER_RANKING_COLUMNS].sort_values(
        ["espn_rank", "player_display_name"], kind="stable"
    )
    require_unique(
        rankings,
        ["season", "week", "game_id", "player_id"],
        "Kicker rankings",
    )
    if rankings["team"].nunique() != len(rankings):
        raise ValueError("Kicker rankings must contain one player per team.")
    return rankings.reset_index(drop=True), evidence


def build_manifest(
    rankings: pd.DataFrame,
    completed_results: pd.DataFrame,
    evidence: dict[str, Any],
    start_season: int,
    rankings_path: Path,
    completed_results_path: Path,
) -> pd.DataFrame:
    """Build compact kicker lineage and quality evidence."""

    rows = [
        ("run_timestamp_utc", datetime.now(timezone.utc).isoformat()),
        ("ranking_version", "v1_kicker_recent_form"),
        ("start_season", start_season),
        ("target_season", int(rankings["season"].iloc[0])),
        ("target_week", int(rankings["week"].iloc[0])),
        ("output_rows", len(rankings)),
        ("candidate_teams", rankings["team"].nunique()),
        ("candidate_games", rankings["game_id"].nunique()),
        (
            "fallback_kickers",
            int(rankings["selection_status"].eq("ACTIVE_ROSTER_FALLBACK").sum()),
        ),
        ("rookie_or_new_kickers", int(rankings["player_history_games"].eq(0).sum())),
        (
            "duplicate_keys",
            int(
                rankings.duplicated(
                    ["season", "week", "game_id", "player_id"]
                ).sum()
            ),
        ),
        (
            "unavailable_keys",
            int(
                rankings[
                    ["season", "week", "game_id", "player_id"]
                ].isna().any(axis=1).sum()
            ),
        ),
        ("selection_evidence", json.dumps(evidence, sort_keys=True)),
        (
            "scoring_sources",
            json.dumps(KICKER_SETTINGS["lineage"], sort_keys=True),
        ),
        ("scoring_config_sha256", sha256_file(SETTINGS_PATH)),
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
    """Build and archive one target-week kicker snapshot."""

    arguments = parse_arguments()
    source_as_of = parse_as_of(arguments.as_of)
    prefix = f"{arguments.season}_week_{arguments.week:02d}"
    rankings_path = resolve_project_path(
        arguments.rankings_output
        or f"results/tables/kicker_rankings_{prefix}.csv"
    )
    completed_results_path = resolve_project_path(
        arguments.completed_results_output
        or "data/processed/runtime_history/completed_kicker_results.csv"
    )
    manifest_path = resolve_project_path(
        arguments.manifest_output
        or f"results/tables/kicker_rankings_{prefix}_manifest.csv"
    )
    if rankings_path.exists() or manifest_path.exists():
        raise FileExistsError(
            "Immutable kicker ranking evidence already exists for this week."
        )

    raw_stats, schedules, roster, depth = load_sources(
        arguments.start_season, arguments.season, arguments.week
    )
    history = build_kicker_games(raw_stats, schedules)
    history = history.loc[
        history["season"].lt(arguments.season)
        | (
            history["season"].eq(arguments.season)
            & history["week"].lt(arguments.week)
        )
    ].copy()
    target_games = build_target_games(
        schedules, arguments.season, arguments.week
    )
    target_kickers = select_target_kickers(
        target_games, roster, depth, history, source_as_of
    )
    rankings, evidence = project_target_week(
        history, target_kickers, source_as_of
    )
    completed_results = history.loc[
        history["season"].between(arguments.season - 1, arguments.season),
        KICKER_RESULT_COLUMNS,
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
    print(f"kicker_rankings_rows={len(rankings):,}")
    print(f"completed_kicker_rows={len(completed_results):,}")
    print(f"kicker_rankings={display_path(rankings_path)}")
    print(f"completed_kicker_results={display_path(completed_results_path)}")
    print(f"kicker_manifest={display_path(manifest_path)}")
    print("kicker_ranking_status=PASS")


if __name__ == "__main__":
    main()
