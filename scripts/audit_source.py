import argparse
import os
import tomllib
from pathlib import Path

import nflreadpy as nfl
import polars as pl
from dotenv import load_dotenv
from nflreadpy.config import update_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_POSITIONS = ["QB", "RB", "WR", "TE"]


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Audit nflverse source grain, identifiers, joins, "
            "and fantasy-point consistency."
        )
    )
    parser.add_argument(
        "--season",
        type=int,
        required=True,
        help="NFL season to audit, such as 2025.",
    )
    return parser.parse_args()


def configure_cache():
    load_dotenv(PROJECT_ROOT / ".env")

    configured_path = Path(
        os.getenv("NFL_CACHE_DIR", "data/cache")
    )

    if configured_path.is_absolute():
        cache_dir = configured_path
    else:
        cache_dir = PROJECT_ROOT / configured_path

    cache_dir = cache_dir.resolve()
    cache_dir.mkdir(parents=True, exist_ok=True)

    update_config(
        cache_mode="filesystem",
        cache_dir=cache_dir,
        verbose=False,
    )

    print(f"Cache directory: {cache_dir}")


def print_section(title):
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def valid_text(column):
    return (
        pl.col(column)
        .fill_null("")
        .str
        .strip_chars()
        != ""
    )


def unavailable_count(dataframe, column):
    series = dataframe.get_column(column)
    null_rows = series.null_count()

    blank_rows = (
        int(
            (
                series
                .str
                .strip_chars()
                == ""
            ).sum()
        )
        if series.dtype == pl.String
        else 0
    )

    return null_rows + blank_rows


def percentage(numerator, denominator):
    if denominator == 0:
        return 0.0

    return round(
        (numerator / denominator) * 100,
        2,
    )


def print_position_counts(dataframe):
    print("rows_by_position:")

    if dataframe.height == 0:
        print("  None")
        return

    position_counts = (
        dataframe
        .group_by("position")
        .len()
        .sort("position")
    )

    for row in position_counts.iter_rows(named=True):
        print(
            f"  {row['position']}: "
            f"{row['len']:,}"
        )


def print_duplicate_summary(
    name,
    dataframe,
    key_columns,
):
    if dataframe.height == 0:
        repeated_groups = 0
        rows_in_repeated_groups = 0
        duplicate_rows_above_grain = 0
        maximum_rows_in_one_key = 0
    else:
        repeated = (
            dataframe
            .group_by(key_columns)
            .len()
            .filter(pl.col("len") > 1)
        )

        repeated_groups = repeated.height

        if repeated_groups:
            rows_in_repeated_groups = int(
                repeated
                .get_column("len")
                .sum()
            )
            maximum_rows_in_one_key = int(
                repeated
                .get_column("len")
                .max()
            )
        else:
            rows_in_repeated_groups = 0
            maximum_rows_in_one_key = 1

        duplicate_rows_above_grain = (
            rows_in_repeated_groups
            - repeated_groups
        )

    print(f"{name}_rows={dataframe.height:,}")
    print(
        f"{name}_repeated_key_groups="
        f"{repeated_groups:,}"
    )
    print(
        f"{name}_rows_in_repeated_key_groups="
        f"{rows_in_repeated_groups:,}"
    )
    print(
        f"{name}_duplicate_rows_above_grain="
        f"{duplicate_rows_above_grain:,}"
    )
    print(
        f"{name}_maximum_rows_in_one_key="
        f"{maximum_rows_in_one_key:,}"
    )


def print_join_coverage(
    name,
    base,
    lookup,
    join_columns,
    segment_column=None,
):
    lookup_keys = (
        lookup
        .select(join_columns)
        .unique()
        .with_columns(
            pl.lit(True).alias("__matched")
        )
    )

    joined = base.join(
        lookup_keys,
        on=join_columns,
        how="left",
    )

    matched_rows = int(
        joined
        .get_column("__matched")
        .fill_null(False)
        .sum()
    )

    unmatched_rows = joined.height - matched_rows

    print(f"{name}_base_rows={joined.height:,}")
    print(f"{name}_matched_rows={matched_rows:,}")
    print(f"{name}_unmatched_rows={unmatched_rows:,}")
    print(
        f"{name}_match_rate_pct="
        f"{percentage(matched_rows, joined.height):.2f}"
    )

    if (
        segment_column is not None
        and segment_column in joined.columns
    ):
        print(f"{name}_by_{segment_column}:")

        segment_summary = (
            joined
            .group_by(segment_column)
            .agg(
                pl.len().alias("base_rows"),
                (
                    pl.col("__matched")
                    .fill_null(False)
                    .cast(pl.Int64)
                    .sum()
                    .alias("matched_rows")
                ),
            )
            .with_columns(
                (
                    pl.col("base_rows")
                    - pl.col("matched_rows")
                ).alias("unmatched_rows")
            )
            .sort(segment_column)
        )

        for row in segment_summary.iter_rows(named=True):
            print(
                f"  {row[segment_column]}: "
                f"base_rows={row['base_rows']:,}, "
                f"matched_rows={row['matched_rows']:,}, "
                f"unmatched_rows={row['unmatched_rows']:,}, "
                f"match_rate_pct="
                f"{percentage(row['matched_rows'], row['base_rows']):.2f}"
            )

    return joined


def load_scoring_settings():
    settings_path = (
        PROJECT_ROOT
        / "config"
        / "league_settings.toml"
    )

    with settings_path.open(
        "rb",
    ) as settings_file:
        settings = tomllib.load(settings_file)

    return settings["scoring"]


def audit_schedules(schedules):
    print_section("SCHEDULE GRAIN")

    regular = schedules.filter(
        pl.col("game_type") == "REG"
    )

    valid_games = regular.filter(
        valid_text("game_id")
    )

    exact_duplicate_rows = int(
        regular
        .is_duplicated()
        .sum()
    )

    print(f"source_schedule_rows={schedules.height:,}")
    print(f"regular_season_games={regular.height:,}")
    print(
        "unavailable_game_ids="
        f"{unavailable_count(regular, 'game_id'):,}"
    )
    print(
        f"exact_duplicate_schedule_rows="
        f"{exact_duplicate_rows:,}"
    )

    print_duplicate_summary(
        "schedule_game_id",
        valid_games,
        ["game_id"],
    )

    home_team_weeks = regular.select(
        "season",
        "week",
        pl.col("home_team").alias("team"),
    )

    away_team_weeks = regular.select(
        "season",
        "week",
        pl.col("away_team").alias("team"),
    )

    team_weeks = pl.concat(
        [home_team_weeks, away_team_weeks]
    )

    print_duplicate_summary(
        "schedule_team_week",
        team_weeks,
        ["season", "week", "team"],
    )

    return regular


def audit_player_stats(player_stats):
    print_section("CORE PLAYER-STATS GRAIN")

    regular = player_stats.filter(
        pl.col("season_type") == "REG"
    )

    core = regular.filter(
        pl.col("position").is_in(CORE_POSITIONS)
    )

    valid_core = core.filter(
        valid_text("player_id")
    )

    exact_duplicate_rows = int(
        core
        .is_duplicated()
        .sum()
    )

    print(f"source_player_stat_rows={player_stats.height:,}")
    print(
        f"regular_season_player_stat_rows="
        f"{regular.height:,}"
    )
    print(f"core_position_rows={core.height:,}")
    print(
        "core_rows_with_unavailable_player_id="
        f"{unavailable_count(core, 'player_id'):,}"
    )
    print(
        f"exact_duplicate_core_stat_rows="
        f"{exact_duplicate_rows:,}"
    )

    print_position_counts(core)

    print_duplicate_summary(
        "core_player_week",
        valid_core,
        ["season", "week", "player_id"],
    )

    print_duplicate_summary(
        "core_player_game",
        valid_core,
        [
            "season",
            "week",
            "game_id",
            "player_id",
        ],
    )

    return core


def audit_rosters(rosters):
    print_section("WEEKLY ROSTER GRAIN")

    regular = rosters.filter(
        pl.col("game_type") == "REG"
    )

    core = regular.filter(
        pl.col("position").is_in(CORE_POSITIONS)
    )

    valid_core = core.filter(
        valid_text("gsis_id")
    )

    print(f"source_roster_rows={rosters.height:,}")
    print(
        f"regular_season_roster_rows="
        f"{regular.height:,}"
    )
    print(f"core_position_roster_rows={core.height:,}")
    print(
        "core_rows_with_unavailable_gsis_id="
        f"{unavailable_count(core, 'gsis_id'):,}"
    )
    print(
        "core_rows_with_unavailable_pfr_id="
        f"{unavailable_count(core, 'pfr_id'):,}"
    )

    print_position_counts(core)

    print_duplicate_summary(
        "roster_player_team_week",
        valid_core,
        ["season", "week", "team", "gsis_id"],
    )

    print_duplicate_summary(
        "roster_player_week",
        valid_core,
        ["season", "week", "gsis_id"],
    )

    valid_crosswalk = valid_core.filter(
        valid_text("pfr_id")
    )

    crosswalk_conflicts = (
        valid_crosswalk
        .group_by(
            ["season", "week", "team", "gsis_id"]
        )
        .agg(
            pl.col("pfr_id")
            .n_unique()
            .alias("distinct_pfr_ids")
        )
        .filter(
            pl.col("distinct_pfr_ids") > 1
        )
        .height
    )

    print(
        "roster_gsis_to_pfr_conflicting_groups="
        f"{crosswalk_conflicts:,}"
    )

    return regular, core


def audit_injuries(injuries):
    print_section("INJURY GRAIN")

    regular = injuries.filter(
        (pl.col("season_type") == "REG")
        & (pl.col("game_type") == "REG")
    )

    core = regular.filter(
        pl.col("position").is_in(CORE_POSITIONS)
    )

    valid_core = core.filter(
        valid_text("gsis_id")
    )

    print(f"source_injury_rows={injuries.height:,}")
    print(
        f"regular_season_injury_rows="
        f"{regular.height:,}"
    )
    print(f"core_position_injury_rows={core.height:,}")
    print(
        "core_rows_with_unavailable_gsis_id="
        f"{unavailable_count(core, 'gsis_id'):,}"
    )

    report_status_unavailable = unavailable_count(
        core,
        "report_status",
    )

    practice_status_unavailable = unavailable_count(
        core,
        "practice_status",
    )

    print(
        "core_rows_without_final_report_status="
        f"{report_status_unavailable:,}"
    )
    print(
        "core_rows_without_final_report_status_pct="
        f"{percentage(report_status_unavailable, core.height):.2f}"
    )
    print(
        "core_rows_without_practice_status="
        f"{practice_status_unavailable:,}"
    )
    print(
        "core_rows_without_practice_status_pct="
        f"{percentage(practice_status_unavailable, core.height):.2f}"
    )

    print_duplicate_summary(
        "injury_player_team_week",
        valid_core,
        ["season", "week", "team", "gsis_id"],
    )

    return core


def audit_snap_counts(snap_counts):
    print_section("SNAP-COUNT GRAIN")

    regular = snap_counts.filter(
        pl.col("game_type") == "REG"
    )

    core = regular.filter(
        pl.col("position").is_in(CORE_POSITIONS)
    )

    valid_core = core.filter(
        valid_text("pfr_player_id")
    )

    print(f"source_snap_rows={snap_counts.height:,}")
    print(
        f"regular_season_snap_rows="
        f"{regular.height:,}"
    )
    print(f"core_position_snap_rows={core.height:,}")
    print(
        "core_rows_with_unavailable_pfr_player_id="
        f"{unavailable_count(core, 'pfr_player_id'):,}"
    )

    print_position_counts(core)

    print_duplicate_summary(
        "snap_player_game",
        valid_core,
        [
            "season",
            "week",
            "game_id",
            "team",
            "pfr_player_id",
        ],
    )

    print_duplicate_summary(
        "snap_player_team_week",
        valid_core,
        [
            "season",
            "week",
            "team",
            "pfr_player_id",
        ],
    )

    return regular, core


def audit_depth_charts(depth_charts):
    print_section("DEPTH-CHART GRAIN AND DATES")

    with_dates = depth_charts.with_columns(
        pl.col("dt")
        .str
        .to_datetime(
            format="%Y-%m-%dT%H:%M:%SZ",
            strict=False,
        )
        .dt
        .date()
        .alias("depth_date")
    )

    core = with_dates.filter(
        pl.col("pos_abb").is_in(CORE_POSITIONS)
    )

    valid_core = core.filter(
        valid_text("gsis_id")
    )

    invalid_dates = (
        with_dates
        .get_column("depth_date")
        .null_count()
    )

    minimum_date = (
        with_dates
        .get_column("depth_date")
        .min()
    )

    maximum_date = (
        with_dates
        .get_column("depth_date")
        .max()
    )

    print(
        f"source_depth_chart_rows="
        f"{depth_charts.height:,}"
    )
    print(f"core_position_depth_rows={core.height:,}")
    print(f"minimum_depth_date={minimum_date}")
    print(f"maximum_depth_date={maximum_date}")
    print(f"invalid_depth_dates={invalid_dates:,}")
    print(
        "core_rows_with_unavailable_gsis_id="
        f"{unavailable_count(core, 'gsis_id'):,}"
    )

    print_duplicate_summary(
        "depth_player_slot_date",
        valid_core,
        [
            "dt",
            "team",
            "gsis_id",
            "pos_abb",
            "pos_slot",
        ],
    )

    distinct_dates = (
        with_dates
        .get_column("depth_date")
        .drop_nulls()
        .n_unique()
    )

    print(f"distinct_depth_dates={distinct_dates:,}")
    print(
        "depth_chart_join_rule="
        "Use the latest depth_date available before each game date."
    )

    return core


def audit_join_coverage(
    player_stats,
    schedules,
    rosters,
    injuries,
    regular_snap_counts,
    core_snap_counts,
):
    print_section("JOIN COVERAGE")

    schedule_keys = schedules.select(
        "game_id"
    )

    print_join_coverage(
        "stats_to_schedule",
        player_stats,
        schedule_keys,
        ["game_id"],
        "position",
    )

    roster_gsis_keys = (
        rosters
        .filter(valid_text("gsis_id"))
        .select(
            "season",
            "week",
            "team",
            pl.col("gsis_id").alias("player_id"),
        )
    )

    print_join_coverage(
        "stats_to_roster_gsis",
        player_stats,
        roster_gsis_keys,
        ["season", "week", "team", "player_id"],
        "position",
    )

    roster_injury_keys = (
        rosters
        .filter(valid_text("gsis_id"))
        .select(
            "season",
            "week",
            "team",
            "gsis_id",
        )
    )

    valid_injuries = injuries.filter(
        valid_text("gsis_id")
    )

    print_join_coverage(
        "injuries_to_roster_gsis",
        valid_injuries,
        roster_injury_keys,
        ["season", "week", "team", "gsis_id"],
        "position",
    )

    roster_pfr_keys = (
        rosters
        .filter(valid_text("pfr_id"))
        .select(
            "season",
            "week",
            "team",
            pl.col("pfr_id").alias("pfr_player_id"),
        )
    )

    print_join_coverage(
        "snaps_to_roster_pfr",
        core_snap_counts,
        roster_pfr_keys,
        [
            "season",
            "week",
            "team",
            "pfr_player_id",
        ],
        "position",
    )

    roster_crosswalk = (
        rosters
        .filter(
            valid_text("gsis_id")
            & valid_text("pfr_id")
        )
        .group_by(
            ["season", "week", "team", "gsis_id"]
        )
        .agg(
            pl.col("pfr_id")
            .first()
            .alias("pfr_player_id")
        )
        .rename(
            {"gsis_id": "player_id"}
        )
    )

    stats_with_pfr = player_stats.join(
        roster_crosswalk,
        on=["season", "week", "team", "player_id"],
        how="left",
    )

    snap_keys = regular_snap_counts.select(
        "season",
        "week",
        "team",
        "pfr_player_id",
    )

    print_join_coverage(
        "stats_to_snaps_via_pfr",
        stats_with_pfr,
        snap_keys,
        [
            "season",
            "week",
            "team",
            "pfr_player_id",
        ],
        "position",
    )


def audit_fantasy_points(player_stats):
    print_section("CONFIGURED FULL-PPR RECONCILIATION")

    scoring = load_scoring_settings()

    calculated_points = (
        (
            pl.col("passing_yards").fill_null(0)
            * scoring["passing_yards"]
        )
        + (
            pl.col("passing_tds").fill_null(0)
            * scoring["passing_touchdowns"]
        )
        + (
            pl.col("passing_interceptions").fill_null(0)
            * scoring["interceptions"]
        )
        + (
            pl.col("rushing_yards").fill_null(0)
            * scoring["rushing_yards"]
        )
        + (
            pl.col("rushing_tds").fill_null(0)
            * scoring["rushing_touchdowns"]
        )
        + (
            pl.col("receptions").fill_null(0)
            * scoring["receptions"]
        )
        + (
            pl.col("receiving_yards").fill_null(0)
            * scoring["receiving_yards"]
        )
        + (
            pl.col("receiving_tds").fill_null(0)
            * scoring["receiving_touchdowns"]
        )
        + (
            (
                pl.col("passing_2pt_conversions").fill_null(0)
                + pl.col("rushing_2pt_conversions").fill_null(0)
                + pl.col("receiving_2pt_conversions").fill_null(0)
            )
            * scoring["two_point_conversions"]
        )
        + (
            pl.col("special_teams_tds").fill_null(0)
            * scoring["special_teams_touchdowns"]
        )
        + (
            (
                pl.col("sack_fumbles_lost").fill_null(0)
                + pl.col("rushing_fumbles_lost").fill_null(0)
                + pl.col("receiving_fumbles_lost").fill_null(0)
            )
            * scoring["fumbles_lost"]
        )
    ).alias("calculated_ppr")

    comparison = (
        player_stats
        .filter(
            pl.col("fantasy_points_ppr").is_not_null()
        )
        .with_columns(calculated_points)
        .with_columns(
            (
                pl.col("calculated_ppr")
                - pl.col("fantasy_points_ppr")
            )
            .abs()
            .alias("absolute_difference")
        )
    )

    tolerance = 0.01

    mismatched_rows = (
        comparison
        .filter(
            pl.col("absolute_difference") > tolerance
        )
        .height
    )

    maximum_difference = (
        comparison
        .get_column("absolute_difference")
        .max()
        if comparison.height
        else None
    )

    print(
        "calculation_scope="
        "Configured full-PPR scoring including special-teams touchdowns"
    )
    print(
        f"comparison_rows="
        f"{comparison.height:,}"
    )
    print(
        f"rows_outside_tolerance="
        f"{mismatched_rows:,}"
    )
    print(
        "rows_outside_tolerance_pct="
        f"{percentage(mismatched_rows, comparison.height):.2f}"
    )
    print(f"tolerance={tolerance:.2f}")
    print(
        f"maximum_absolute_difference="
        f"{maximum_difference}"
    )
    print(
        "interpretation_note="
        "Nonzero differences may represent scoring events not included "
        "in the current league configuration."
    )


def main():
    args = parse_args()
    configure_cache()

    print(f"Audit season: {args.season}")
    print(
        "Audit scope: regular season, "
        "core fantasy positions QB/RB/WR/TE"
    )

    player_stats = nfl.load_player_stats(
        args.season,
        summary_level="week",
    )
    schedules = nfl.load_schedules(args.season)
    rosters = nfl.load_rosters_weekly(args.season)
    injuries = nfl.load_injuries(args.season)
    depth_charts = nfl.load_depth_charts(args.season)
    snap_counts = nfl.load_snap_counts(args.season)

    regular_schedules = audit_schedules(schedules)
    core_player_stats = audit_player_stats(player_stats)

    regular_rosters, core_rosters = audit_rosters(
        rosters
    )

    core_injuries = audit_injuries(injuries)
    regular_snap_counts, core_snap_counts = (
        audit_snap_counts(snap_counts)
    )

    audit_depth_charts(depth_charts)

    audit_join_coverage(
        core_player_stats,
        regular_schedules,
        regular_rosters,
        core_injuries,
        regular_snap_counts,
        core_snap_counts,
    )

    audit_fantasy_points(core_player_stats)

    print_section("SOURCE AUDIT COMPLETE")
    print("No processed datasets were written.")
    print(
        "Review all duplicate counts, join rates, "
        "and scoring differences before modeling."
    )


if __name__ == "__main__":
    main()