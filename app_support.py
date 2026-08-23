"""Pure data helpers for the public fantasy-football Streamlit app."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
SLOT_REQUIREMENTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}
COMPLETED_RESULTS_COLUMNS = {
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
}
DST_RANKING_COLUMNS = {
    "season",
    "week",
    "game_id",
    "game_date",
    "team",
    "opponent",
    "espn_projected_points",
    "espn_rank",
    "yahoo_projected_points",
    "yahoo_rank",
}
DST_RESULT_COLUMNS = {
    "season",
    "week",
    "game_id",
    "game_date",
    "team",
    "opponent",
    "espn_fantasy_points",
    "yahoo_fantasy_points",
}
KICKER_RANKING_COLUMNS = {
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "player_display_name",
    "position",
    "team",
    "opponent",
    "espn_projected_points",
    "espn_rank",
    "yahoo_projected_points",
    "yahoo_rank",
}
KICKER_RESULT_COLUMNS = {
    "season",
    "week",
    "game_id",
    "game_date",
    "player_id",
    "player_display_name",
    "position",
    "team",
    "opponent",
    "espn_fantasy_points",
    "yahoo_fantasy_points",
}


def normalize_rankings(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize serialized public fields for reliable UI filtering."""

    rankings = dataframe.copy()
    boolean_values = (
        rankings["role_eligible"].astype(str).str.strip().str.lower()
    )
    invalid = sorted(set(boolean_values) - {"true", "false"})
    if invalid:
        raise ValueError(f"Unexpected role_eligible values: {invalid}")
    rankings["role_eligible"] = boolean_values.eq("true")

    numeric_columns = [
        "display_projected_fantasy_points_ppr",
        "projected_fantasy_points_ppr",
        "position_rank",
        "overall_flex_rank",
        "remaining_flex_rank",
        "prior_games_count",
    ]
    for column in numeric_columns:
        if column in rankings:
            rankings[column] = pd.to_numeric(
                rankings[column], errors="coerce"
            )
    rankings["player_label"] = (
        rankings["player_display_name"].astype(str)
        + " | "
        + rankings["position"].astype(str)
        + " | "
        + rankings["team"].astype(str)
        + " | "
        + rankings["player_id"].astype(str)
    )
    return rankings


def top_projections(
    rankings: pd.DataFrame,
    position: str = "All",
    limit: int = 25,
) -> pd.DataFrame:
    """Return the highest role-eligible projections for display."""

    selected = rankings.loc[rankings["role_eligible"]].copy()
    if position != "All":
        selected = selected.loc[selected["position"].eq(position)]
    return selected.sort_values(
        [
            "display_projected_fantasy_points_ppr",
            "player_display_name",
        ],
        ascending=[False, True],
        kind="stable",
    ).head(limit).reset_index(drop=True)


def search_projection_pool(
    rankings: pd.DataFrame, search_text: str = ""
) -> pd.DataFrame:
    """Search the compact projection fields without changing ranking order."""

    search = search_text.strip()
    if not search:
        return rankings.copy()
    searchable = rankings[
        ["player_display_name", "position", "team", "opponent"]
    ].fillna("")
    matches = searchable.apply(
        lambda column: column.astype(str).str.contains(
            search, case=False, regex=False, na=False
        )
    ).any(axis="columns")
    return rankings.loc[matches].copy()


def apply_projection_intervals(
    rankings: pd.DataFrame, calibration: pd.DataFrame
) -> pd.DataFrame:
    """Apply position residual ranges calibrated on prior validation data."""

    required = {"position", "lower_residual", "upper_residual"}
    missing = sorted(required - set(calibration.columns))
    if missing:
        raise ValueError(
            "Projection calibration is missing columns: " + ", ".join(missing)
        )
    if calibration["position"].duplicated().any():
        raise ValueError("Projection calibration positions are not unique.")
    enriched = rankings.merge(
        calibration[["position", "lower_residual", "upper_residual"]],
        on="position",
        how="left",
        validate="many_to_one",
    )
    if enriched[["lower_residual", "upper_residual"]].isna().any().any():
        missing_positions = sorted(
            enriched.loc[
                enriched["lower_residual"].isna(), "position"
            ].unique()
        )
        raise ValueError(
            "Projection ranges are unavailable for positions: "
            + ", ".join(missing_positions)
        )
    projection = enriched["display_projected_fantasy_points_ppr"]
    enriched["projection_floor_ppr"] = (
        projection + enriched["lower_residual"]
    ).clip(lower=0).round(2)
    enriched["projection_ceiling_ppr"] = (
        projection + enriched["upper_residual"]
    ).clip(lower=0).round(2)
    enriched["projection_ceiling_ppr"] = enriched[
        ["projection_floor_ppr", "projection_ceiling_ppr"]
    ].max(axis="columns")
    return enriched


def schedule_team_frame(schedule: pd.DataFrame) -> pd.DataFrame:
    """Return one team-opponent row for each scheduled game appearance."""

    required = {
        "season",
        "week",
        "game_id",
        "away_team",
        "home_team",
    }
    missing = sorted(required - set(schedule.columns))
    if missing:
        raise ValueError("Season schedule is missing columns: " + ", ".join(missing))
    away = schedule[
        ["season", "week", "game_id", "away_team", "home_team"]
    ].rename(columns={"away_team": "team", "home_team": "opponent"})
    away["venue"] = "Away"
    home = schedule[
        ["season", "week", "game_id", "home_team", "away_team"]
    ].rename(columns={"home_team": "team", "away_team": "opponent"})
    home["venue"] = "Home"
    appearances = pd.concat([away, home], ignore_index=True)
    appearances["week"] = pd.to_numeric(
        appearances["week"], errors="raise"
    ).astype(int)
    if appearances[["season", "week", "team"]].duplicated().any():
        raise ValueError("Schedule contains duplicate team-week appearances.")
    return appearances.sort_values(["team", "week"], kind="stable").reset_index(
        drop=True
    )


def team_bye_weeks(schedule: pd.DataFrame) -> pd.DataFrame:
    """Resolve the one missing regular-season week for every team."""

    appearances = schedule_team_frame(schedule)
    rows: list[dict[str, object]] = []
    for team, games in appearances.groupby("team", sort=True):
        missing = sorted(set(range(1, 19)) - set(games["week"]))
        if len(missing) != 1:
            raise ValueError(
                f"Team {team} must resolve to exactly one bye week."
            )
        rows.append({"team": team, "bye_week": missing[0]})
    if len(rows) != 32:
        raise ValueError(f"Expected 32 bye-week rows, observed {len(rows)}.")
    return pd.DataFrame(rows)


def season_outlook_frame(
    rankings: pd.DataFrame,
    schedule: pd.DataFrame,
    current_week: int,
    position: str = "All",
    limit: int = 50,
) -> pd.DataFrame:
    """Build a transparent current-rate rest-of-season planning proxy."""

    appearances = schedule_team_frame(schedule)
    remaining = (
        appearances.loc[appearances["week"].ge(current_week)]
        .groupby("team", as_index=False)
        .size()
        .rename(columns={"size": "games_remaining"})
    )
    byes = team_bye_weeks(schedule)
    selected = rankings.loc[rankings["role_eligible"]].copy()
    if position == "FLEX":
        selected = selected.loc[selected["position"].isin(FLEX_POSITIONS)]
    elif position != "All":
        selected = selected.loc[selected["position"].eq(position)]
    selected = selected.merge(remaining, on="team", how="left", validate="many_to_one")
    selected = selected.merge(byes, on="team", how="left", validate="many_to_one")
    if selected[["games_remaining", "bye_week"]].isna().any().any():
        raise ValueError("Season outlook could not reconcile every player team.")
    selected["ros_points_proxy"] = (
        selected["display_projected_fantasy_points_ppr"]
        * selected["games_remaining"]
    ).round(2)
    columns = [
        "player_id",
        "player_display_name",
        "position",
        "team",
        "bye_week",
        "games_remaining",
        "display_projected_fantasy_points_ppr",
        "ros_points_proxy",
        "evidence_confidence",
    ]
    for optional in ["projection_floor_ppr", "projection_ceiling_ppr"]:
        if optional in selected:
            columns.append(optional)
    return (
        selected.sort_values(
            ["ros_points_proxy", "player_display_name"],
            ascending=[False, True],
            kind="stable",
        )[columns]
        .head(limit)
        .reset_index(drop=True)
    )


def bye_week_frame(
    rankings: pd.DataFrame,
    schedule: pd.DataFrame,
    player_ids: Iterable[str],
    current_week: int,
) -> pd.DataFrame:
    """Return one compact bye-planning row per selected roster player."""

    selected_ids = {str(player_id) for player_id in player_ids}
    roster = rankings.loc[
        rankings["player_id"].astype(str).isin(selected_ids),
        ["player_display_name", "position", "team"],
    ].copy()
    if roster.empty:
        return pd.DataFrame(
            columns=[
                "player_display_name",
                "position",
                "team",
                "bye_week",
                "bye_status",
            ]
        )
    roster = roster.merge(
        team_bye_weeks(schedule), on="team", how="left", validate="many_to_one"
    )
    roster["bye_status"] = roster["bye_week"].map(
        lambda bye: (
            "THIS WEEK"
            if int(bye) == current_week
            else "UPCOMING"
            if int(bye) > current_week
            else "COMPLETED"
        )
    )
    return roster.sort_values(
        ["bye_week", "position", "player_display_name"], kind="stable"
    ).reset_index(drop=True)


def waiver_shortlist(
    rankings: pd.DataFrame,
    roster_player_ids: Iterable[str],
    unavailable_player_ids: Iterable[str] = (),
    position: str = "All",
    limit: int = 15,
) -> pd.DataFrame:
    """Rank non-roster players while labeling the ownership assumption."""

    roster_ids = {str(player_id) for player_id in roster_player_ids}
    unavailable_ids = {str(player_id) for player_id in unavailable_player_ids}
    candidates = rankings.loc[
        rankings["role_eligible"]
        & ~rankings["player_id"].astype(str).isin(roster_ids | unavailable_ids)
    ].copy()
    if position == "FLEX":
        candidates = candidates.loc[candidates["position"].isin(FLEX_POSITIONS)]
    elif position != "All":
        candidates = candidates.loc[candidates["position"].eq(position)]

    roster = rankings.loc[
        rankings["player_id"].astype(str).isin(roster_ids)
        & rankings["role_eligible"]
    ].copy()
    weakest_by_position = roster.groupby("position")[
        "display_projected_fantasy_points_ppr"
    ].min()
    candidates["upgrade_vs_roster"] = candidates.apply(
        lambda row: (
            row["display_projected_fantasy_points_ppr"]
            - weakest_by_position.get(row["position"], float("nan"))
        ),
        axis="columns",
    ).round(2)
    columns = [
        "player_id",
        "player_display_name",
        "position",
        "team",
        "opponent",
        "display_projected_fantasy_points_ppr",
        "upgrade_vs_roster",
    ]
    for optional in ["projection_floor_ppr", "projection_ceiling_ppr"]:
        if optional in candidates:
            columns.append(optional)
    return (
        candidates.sort_values(
            [
                "display_projected_fantasy_points_ppr",
                "player_display_name",
            ],
            ascending=[False, True],
            kind="stable",
        )[columns]
        .head(limit)
        .reset_index(drop=True)
    )


def trade_side_summary(
    outlook: pd.DataFrame, player_ids: Iterable[str]
) -> dict[str, float | int]:
    """Summarize a proposed trade side using transparent planning measures."""

    selected_ids = {str(player_id) for player_id in player_ids}
    selected = outlook.loc[
        outlook["player_id"].astype(str).isin(selected_ids)
    ]
    result: dict[str, float | int] = {
        "players": len(selected),
        "weekly_projection": round(
            float(selected["display_projected_fantasy_points_ppr"].sum()), 2
        ),
        "ros_points_proxy": round(float(selected["ros_points_proxy"].sum()), 2),
    }
    if "projection_floor_ppr" in selected:
        result["weekly_floor"] = round(
            float(selected["projection_floor_ppr"].sum()), 2
        )
        result["weekly_ceiling"] = round(
            float(selected["projection_ceiling_ppr"].sum()), 2
        )
    return result


def flex_projections(
    rankings: pd.DataFrame,
    limit: int = 25,
) -> pd.DataFrame:
    """Return the highest role-eligible RB, WR, and TE FLEX choices."""

    return (
        rankings.loc[
            rankings["role_eligible"]
            & rankings["position"].isin(FLEX_POSITIONS)
        ]
        .sort_values(
            [
                "display_projected_fantasy_points_ppr",
                "player_display_name",
            ],
            ascending=[False, True],
            kind="stable",
        )
        .head(limit)
        .reset_index(drop=True)
    )


def current_games(rankings: pd.DataFrame) -> pd.DataFrame:
    """Return one compact matchup row per target-week game."""

    rows: list[dict[str, object]] = []
    for game_id, game in rankings.groupby("game_id", sort=False):
        teams = sorted(
            set(game["team"].dropna().astype(str))
            | set(game["opponent"].dropna().astype(str))
        )
        if len(teams) != 2:
            raise ValueError(
                f"Game {game_id} does not resolve to exactly two teams."
            )
        game_date = pd.to_datetime(
            game["game_date"].iloc[0], errors="raise"
        )
        rows.append(
            {
                "game_date": game_date.strftime("%a, %b %d"),
                "matchup": f"{teams[0]} vs {teams[1]}",
                "_sort_date": game_date,
            }
        )
    return (
        pd.DataFrame(rows)
        .sort_values(["_sort_date", "matchup"], kind="stable")
        .drop(columns="_sort_date")
        .reset_index(drop=True)
    )


def normalize_completed_results(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize the separately published observed-results table."""

    missing = sorted(COMPLETED_RESULTS_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(
            "Completed results are missing columns: " + ", ".join(missing)
        )
    completed = dataframe.copy()
    for column in ["season", "week", "fantasy_points_ppr"]:
        completed[column] = pd.to_numeric(completed[column], errors="raise")
    completed["game_date"] = pd.to_datetime(
        completed["game_date"], errors="raise"
    )
    return completed


def filter_completed_results(
    completed: pd.DataFrame,
    season: int,
    week: int,
    position: str = "All",
) -> pd.DataFrame:
    """Return actual PPR results for one completed week."""

    selected = completed.loc[
        completed["season"].eq(season) & completed["week"].eq(week)
    ].copy()
    if position != "All":
        selected = selected.loc[selected["position"].eq(position)]
    return selected.sort_values(
        ["fantasy_points_ppr", "player_display_name"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def normalize_dst_rankings(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize the separately published team D/ST projections."""

    missing = sorted(DST_RANKING_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(
            "D/ST rankings are missing columns: " + ", ".join(missing)
        )
    rankings = dataframe.copy()
    for column in [
        "season",
        "week",
        "espn_projected_points",
        "espn_rank",
        "yahoo_projected_points",
        "yahoo_rank",
    ]:
        rankings[column] = pd.to_numeric(rankings[column], errors="raise")
    rankings["defense_label"] = (
        rankings["team"].astype(str)
        + " D/ST | vs "
        + rankings["opponent"].astype(str)
    )
    return rankings


def dst_projection_frame(
    rankings: pd.DataFrame,
    profile: str,
) -> pd.DataFrame:
    """Return a compact projection table for one scoring platform."""

    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"espn", "yahoo"}:
        raise ValueError(f"Unknown D/ST scoring profile: {profile}")
    points_column = f"{normalized_profile}_projected_points"
    rank_column = f"{normalized_profile}_rank"
    return (
        rankings.loc[:, ["team", "opponent", points_column, rank_column]]
        .rename(
            columns={points_column: "projected_points", rank_column: "rank"}
        )
        .sort_values(["rank", "team"], kind="stable")
        .reset_index(drop=True)
    )


def normalize_completed_dst_results(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize actual team D/ST scores for previous-week display."""

    missing = sorted(DST_RESULT_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(
            "Completed D/ST results are missing columns: "
            + ", ".join(missing)
        )
    completed = dataframe.copy()
    for column in [
        "season",
        "week",
        "espn_fantasy_points",
        "yahoo_fantasy_points",
    ]:
        completed[column] = pd.to_numeric(completed[column], errors="raise")
    completed["game_date"] = pd.to_datetime(
        completed["game_date"], errors="raise"
    )
    return completed


def filter_completed_dst_results(
    completed: pd.DataFrame,
    season: int,
    week: int,
    profile: str,
) -> pd.DataFrame:
    """Return one completed week of D/ST scores for a platform."""

    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"espn", "yahoo"}:
        raise ValueError(f"Unknown D/ST scoring profile: {profile}")
    points_column = f"{normalized_profile}_fantasy_points"
    return (
        completed.loc[
            completed["season"].eq(season)
            & completed["week"].eq(week),
            ["team", "opponent", points_column],
        ]
        .rename(columns={points_column: "actual_points"})
        .sort_values(
            ["actual_points", "team"],
            ascending=[False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def normalize_kicker_rankings(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize separately published kicker projections."""

    missing = sorted(KICKER_RANKING_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(
            "Kicker rankings are missing columns: " + ", ".join(missing)
        )
    rankings = dataframe.copy()
    for column in [
        "season",
        "week",
        "espn_projected_points",
        "espn_rank",
        "yahoo_projected_points",
        "yahoo_rank",
    ]:
        rankings[column] = pd.to_numeric(rankings[column], errors="raise")
    rankings["kicker_label"] = (
        rankings["player_display_name"].astype(str)
        + " | K | "
        + rankings["team"].astype(str)
        + " | vs "
        + rankings["opponent"].astype(str)
    )
    return rankings


def kicker_projection_frame(
    rankings: pd.DataFrame,
    profile: str,
) -> pd.DataFrame:
    """Return compact kicker projections for one platform."""

    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"espn", "yahoo"}:
        raise ValueError(f"Unknown kicker scoring profile: {profile}")
    points_column = f"{normalized_profile}_projected_points"
    rank_column = f"{normalized_profile}_rank"
    return (
        rankings.loc[
            :,
            [
                "player_id",
                "player_display_name",
                "position",
                "team",
                "opponent",
                points_column,
                rank_column,
            ],
        ]
        .rename(
            columns={points_column: "projected_points", rank_column: "rank"}
        )
        .sort_values(["rank", "player_display_name"], kind="stable")
        .reset_index(drop=True)
    )


def normalize_completed_kicker_results(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Normalize actual kicker scores for history and season totals."""

    missing = sorted(KICKER_RESULT_COLUMNS - set(dataframe.columns))
    if missing:
        raise ValueError(
            "Completed kicker results are missing columns: "
            + ", ".join(missing)
        )
    completed = dataframe.copy()
    for column in [
        "season",
        "week",
        "espn_fantasy_points",
        "yahoo_fantasy_points",
    ]:
        completed[column] = pd.to_numeric(completed[column], errors="raise")
    completed["game_date"] = pd.to_datetime(
        completed["game_date"], errors="raise"
    )
    return completed


def filter_completed_kicker_results(
    completed: pd.DataFrame,
    season: int,
    week: int,
    profile: str,
) -> pd.DataFrame:
    """Return one completed week of kicker scores for a platform."""

    normalized_profile = profile.strip().lower()
    if normalized_profile not in {"espn", "yahoo"}:
        raise ValueError(f"Unknown kicker scoring profile: {profile}")
    points_column = f"{normalized_profile}_fantasy_points"
    return (
        completed.loc[
            completed["season"].eq(season) & completed["week"].eq(week),
            [
                "player_display_name",
                "position",
                "team",
                "opponent",
                points_column,
            ],
        ]
        .rename(columns={points_column: "actual_points"})
        .sort_values(
            ["actual_points", "player_display_name"],
            ascending=[False, True],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def selectable_kickers(rankings: pd.DataFrame) -> dict[str, str]:
    """Return stable kicker label-to-player mappings."""

    ordered = rankings.sort_values(
        ["team", "player_display_name"], kind="stable"
    )
    return dict(zip(ordered["kicker_label"], ordered["player_id"]))


def season_totals_frame(
    completed_players: pd.DataFrame,
    completed_kickers: pd.DataFrame,
    season: int,
    position: str = "All",
    kicker_profile: str = "ESPN",
    completed_dst: pd.DataFrame | None = None,
    dst_profile: str | None = None,
) -> pd.DataFrame:
    """Aggregate completed offensive, kicker, and optional D/ST points."""

    offense = completed_players.loc[
        completed_players["season"].eq(season)
    ].copy()
    offense["_points"] = offense["fantasy_points_ppr"]
    normalized_profile = kicker_profile.strip().lower()
    if normalized_profile not in {"espn", "yahoo"}:
        raise ValueError(f"Unknown kicker scoring profile: {kicker_profile}")
    kicker_points = f"{normalized_profile}_fantasy_points"
    kickers = completed_kickers.loc[
        completed_kickers["season"].eq(season)
    ].copy()
    kickers["_points"] = kickers[kicker_points]
    frames = [
        offense[
            [
                "game_date",
                "player_id",
                "player_display_name",
                "position",
                "team",
                "_points",
            ]
        ],
        kickers[
            [
                "game_date",
                "player_id",
                "player_display_name",
                "position",
                "team",
                "_points",
            ]
        ],
    ]
    if completed_dst is not None:
        normalized_dst_profile = (
            dst_profile if dst_profile is not None else kicker_profile
        ).strip().lower()
        if normalized_dst_profile not in {"espn", "yahoo"}:
            raise ValueError(f"Unknown D/ST scoring profile: {dst_profile}")
        dst_points = f"{normalized_dst_profile}_fantasy_points"
        defenses = completed_dst.loc[
            completed_dst["season"].eq(season)
        ].copy()
        defenses["player_id"] = "DST_" + defenses["team"].astype(str)
        defenses["player_display_name"] = (
            defenses["team"].astype(str) + " D/ST"
        )
        defenses["position"] = "D/ST"
        defenses["_points"] = defenses[dst_points]
        frames.append(
            defenses[
                [
                    "game_date",
                    "player_id",
                    "player_display_name",
                    "position",
                    "team",
                    "_points",
                ]
            ]
        )
    combined = pd.concat(frames, ignore_index=True)
    if position == "FLEX":
        combined = combined.loc[combined["position"].isin(FLEX_POSITIONS)]
    elif position != "All":
        combined = combined.loc[combined["position"].eq(position)]
    if combined.empty:
        return pd.DataFrame(
            columns=[
                "player_display_name",
                "position",
                "team",
                "total_points",
            ]
        )
    latest_team = (
        combined.sort_values("game_date", kind="stable")
        .drop_duplicates("player_id", keep="last")
        .loc[:, ["player_id", "team"]]
    )
    totals = (
        combined.groupby(
            ["player_id", "player_display_name", "position"],
            as_index=False,
            sort=False,
        )["_points"]
        .sum()
        .rename(columns={"_points": "total_points"})
        .merge(latest_team, on="player_id", how="left", validate="one_to_one")
    )
    totals["total_points"] = totals["total_points"].round(2)
    return totals[
        ["player_display_name", "position", "team", "total_points"]
    ].sort_values(
        ["total_points", "player_display_name"],
        ascending=[False, True],
        kind="stable",
    ).reset_index(drop=True)


def filter_rankings(
    rankings: pd.DataFrame,
    positions: Iterable[str],
    teams: Iterable[str],
    tiers: Iterable[str],
    confidence: Iterable[str],
    search_text: str = "",
) -> pd.DataFrame:
    """Apply the global dashboard filters deterministically."""

    selected = rankings.loc[
        rankings["position"].isin(list(positions))
        & rankings["team"].isin(list(teams))
        & rankings["lineup_tier"].isin(list(tiers))
        & rankings["evidence_confidence"].isin(list(confidence))
    ].copy()
    search = search_text.strip()
    if search:
        selected = selected.loc[
            selected["player_display_name"].astype(str).str.contains(
                search, case=False, regex=False, na=False
            )
        ]
    return selected.sort_values(
        [
            "role_eligible",
            "display_projected_fantasy_points_ppr",
            "position",
            "player_display_name",
        ],
        ascending=[False, False, True, True],
        kind="stable",
    )


def selectable_players(rankings: pd.DataFrame) -> dict[str, str]:
    """Return stable UI mappings for players with a usable weekly role."""

    ordered = rankings.loc[rankings["role_eligible"]].sort_values(
        [
            "position",
            "display_projected_fantasy_points_ppr",
            "player_display_name",
        ],
        ascending=[True, False, True],
        key=lambda series: (
            series.map(POSITION_ORDER)
            if series.name == "position"
            else series
        ),
        kind="stable",
    )
    return dict(zip(ordered["player_label"], ordered["player_id"]))


def optimize_lineup(
    rankings: pd.DataFrame,
    player_ids: Iterable[str],
    unavailable_player_ids: Iterable[str] = (),
) -> tuple[pd.DataFrame, list[str]]:
    """Choose a legal 1-QB, 2-RB, 2-WR, 1-TE, 1-FLEX lineup."""

    selected_ids = {str(player_id) for player_id in player_ids}
    unavailable_ids = {
        str(player_id) for player_id in unavailable_player_ids
    }
    roster = rankings.loc[
        rankings["player_id"].astype(str).isin(selected_ids)
    ].copy()
    roster = roster.sort_values(
        ["display_projected_fantasy_points_ppr", "player_display_name"],
        ascending=[False, True],
        kind="stable",
    )
    roster["recommended_slot"] = "BENCH"
    roster["lineup_status"] = "BENCH"

    eligible = roster.loc[
        roster["role_eligible"]
        & ~roster["player_id"].astype(str).isin(unavailable_ids)
    ].copy()
    used_player_ids: set[str] = set()
    gaps: list[str] = []

    for position, required in SLOT_REQUIREMENTS.items():
        candidates = eligible.loc[
            eligible["position"].eq(position)
            & ~eligible["player_id"].astype(str).isin(used_player_ids)
        ].head(required)
        for player_id in candidates["player_id"].astype(str):
            used_player_ids.add(player_id)
            roster.loc[
                roster["player_id"].astype(str).eq(player_id),
                ["recommended_slot", "lineup_status"],
            ] = [position, "START"]
        missing = required - len(candidates)
        if missing:
            gaps.append(f"{position}: missing {missing}")

    flex_candidates = eligible.loc[
        eligible["position"].isin(FLEX_POSITIONS)
        & ~eligible["player_id"].astype(str).isin(used_player_ids)
    ].head(1)
    if flex_candidates.empty:
        gaps.append("FLEX: missing 1")
    else:
        flex_id = str(flex_candidates.iloc[0]["player_id"])
        used_player_ids.add(flex_id)
        roster.loc[
            roster["player_id"].astype(str).eq(flex_id),
            ["recommended_slot", "lineup_status"],
        ] = ["FLEX", "START"]

    roster.loc[
        ~roster["role_eligible"],
        ["recommended_slot", "lineup_status"],
    ] = ["INELIGIBLE", "CHECK ROLE"]
    roster.loc[
        roster["player_id"].astype(str).isin(unavailable_ids),
        ["recommended_slot", "lineup_status"],
    ] = ["UNAVAILABLE", "SIT"]
    slot_order = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "FLEX": 4}
    roster["_slot_order"] = roster["recommended_slot"].map(
        slot_order
    ).fillna(9)
    roster = roster.sort_values(
        [
            "_slot_order",
            "display_projected_fantasy_points_ppr",
            "player_display_name",
        ],
        ascending=[True, False, True],
        kind="stable",
    ).drop(columns="_slot_order")
    return roster.reset_index(drop=True), gaps


def comparison_frame(
    rankings: pd.DataFrame, player_ids: Iterable[str]
) -> pd.DataFrame:
    """Return a projection-sorted comparison for selected players."""

    selected_ids = {str(player_id) for player_id in player_ids}
    columns = [
        "player_display_name",
        "position",
        "team",
        "opponent",
        "display_projected_fantasy_points_ppr",
    ]
    for optional in ["projection_floor_ppr", "projection_ceiling_ppr"]:
        if optional in rankings:
            columns.append(optional)
    return (
        rankings.loc[
            rankings["player_id"].astype(str).isin(selected_ids),
            columns,
        ]
        .sort_values(
            "display_projected_fantasy_points_ppr",
            ascending=False,
            kind="stable",
        )
        .reset_index(drop=True)
    )
