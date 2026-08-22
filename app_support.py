"""Pure data helpers for the public fantasy-football Streamlit app."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3}
SLOT_REQUIREMENTS = {"QB": 1, "RB": 2, "WR": 2, "TE": 1}
FLEX_POSITIONS = {"RB", "WR", "TE"}


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
        + " · "
        + rankings["position"].astype(str)
        + " · "
        + rankings["team"].astype(str)
        + " · "
        + rankings["player_id"].astype(str)
    )
    return rankings


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
    """Return stable UI label-to-player mappings."""

    ordered = rankings.sort_values(
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
    rankings: pd.DataFrame, player_ids: Iterable[str]
) -> tuple[pd.DataFrame, list[str]]:
    """Choose a legal 1-QB, 2-RB, 2-WR, 1-TE, 1-FLEX lineup."""

    selected_ids = {str(player_id) for player_id in player_ids}
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

    eligible = roster.loc[roster["role_eligible"]].copy()
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
    return (
        rankings.loc[
            rankings["player_id"].astype(str).isin(selected_ids),
            [
                "player_display_name",
                "position",
                "team",
                "opponent",
                "display_projected_fantasy_points_ppr",
                "position_rank",
                "overall_flex_rank",
                "evidence_confidence",
                "role_eligible",
                "risk_flags",
                "recommendation_reason",
            ],
        ]
        .sort_values(
            "display_projected_fantasy_points_ppr",
            ascending=False,
            kind="stable",
        )
        .reset_index(drop=True)
    )
