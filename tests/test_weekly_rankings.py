"""Focused tests for weekly lineup-demand and confidence rules."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_weekly_rankings import (  # noqa: E402
    assign_confidence,
    assign_rankings,
    validate_schedule_coverage,
)


def configuration() -> dict:
    """Return a small two-team rule configuration."""

    return {
        "rankings": {
            "display_projection_floor": 0.0,
            "injury_context_status": (
                "SOURCE_UNAVAILABLE_FOR_2026_AT_BUILD"
            ),
        },
        "quality": {
            "supported_positions": ["QB", "RB", "WR", "TE"],
            "prediction_column": "projected_fantasy_points_ppr",
            "maximum_team_count": 32,
            "maximum_game_count": 16,
        },
        "role_eligibility": {"QB": 1, "RB": 3, "WR": 3, "TE": 2},
        "confidence": {
            "high_minimum_prior_games": 5,
            "high_maximum_days_since_previous_game": 365,
            "medium_minimum_prior_games": 3,
            "medium_maximum_days_since_previous_game": 730,
            "require_previous_snap_record_for_high": True,
        },
    }


def test_bye_week_coverage_uses_feature_evidence() -> None:
    rows = []
    for game_number in range(14):
        for side in ["A", "B"]:
            rows.append(
                {
                    "game_id": f"game-{game_number}",
                    "team": f"{side}{game_number:02d}",
                }
            )
    rankings = pd.DataFrame(rows)
    feature_manifest = {
        "source_summary": '{"candidate_teams": 28, "candidate_games": 14}'
    }
    assert validate_schedule_coverage(
        rankings, feature_manifest, configuration()
    ) == (28, 14)


def league_settings() -> dict:
    """Return two-team roster demand for a compact fixture."""

    return {
        "league": {"team_count": 2},
        "roster": {
            "quarterbacks": 1,
            "running_backs": 1,
            "wide_receivers": 1,
            "tight_ends": 1,
            "flex": 1,
            "flex_eligible_positions": ["RB", "WR", "TE"],
        },
    }


def fixture() -> pd.DataFrame:
    """Create enough players to fill every two-team lineup slot."""

    rows = []
    scores = {
        "QB": [20, 19, 18],
        "RB": [17, 16, 15, 14, 30],
        "WR": [13, 12, 11, 10],
        "TE": [9, 8, 7, 6],
    }
    depth_ranks = {
        "QB": [1, 1, 2],
        "RB": [1, 1, 2, 2, 4],
        "WR": [1, 1, 2, 2],
        "TE": [1, 1, 2, 2],
    }
    for position, values in scores.items():
        for index, score in enumerate(values, start=1):
            rows.append(
                {
                    "player_id": f"{position}{index}",
                    "position": position,
                    "pos_abb": position,
                    "projected_fantasy_points_ppr": float(score),
                    "pos_rank": depth_ranks[position][index - 1],
                    "pos_slot": 1,
                    "prior_games_count": 10,
                    "days_since_previous_game": 100,
                    "has_previous_snap_record": 1,
                }
            )
    return pd.DataFrame(rows)


def test_depth_filter_prevents_high_scoring_backup_from_starting() -> None:
    """A conditional-appearance score cannot bypass role eligibility."""

    ranked = assign_rankings(
        fixture(),
        configuration(),
        league_settings(),
    )
    backup = ranked.loc[ranked["player_id"].eq("RB5")].iloc[0]
    assert backup["raw_position_rank"] == 1
    assert not backup["role_eligible"]
    assert backup["projected_lineup_slot"] == "ROLE_FILTERED"
    assert pd.isna(backup["position_rank"])


def test_lineup_demand_fills_fixed_and_flex_slots() -> None:
    """Two complete lineups contain eight fixed slots and two FLEX slots."""

    ranked = assign_rankings(
        fixture(),
        configuration(),
        league_settings(),
    )
    counts = ranked["projected_lineup_slot"].value_counts().to_dict()
    assert counts["QB"] == 2
    assert counts["RB"] == 2
    assert counts["WR"] == 2
    assert counts["TE"] == 2
    assert counts["FLEX"] == 2


def test_confidence_and_display_floor_are_separate_from_raw_score() -> None:
    """Low evidence and display flooring do not alter the raw prediction."""

    frame = fixture()
    frame.loc[0, "prior_games_count"] = 0
    frame.loc[0, "days_since_previous_game"] = 900
    frame.loc[0, "projected_fantasy_points_ppr"] = -2.5
    confidence = assign_confidence(frame, configuration()["confidence"])
    assert confidence.iloc[0] == "LOW"

    ranked = assign_rankings(frame, configuration(), league_settings())
    row = ranked.loc[ranked["player_id"].eq("QB1")].iloc[0]
    assert row["projected_fantasy_points_ppr"] == -2.5
    assert row["display_projected_fantasy_points_ppr"] == 0.0
