"""Tests for public-app filtering, comparison, and lineup logic."""

from __future__ import annotations

import pandas as pd

from app_support import (
    comparison_frame,
    filter_rankings,
    normalize_rankings,
    optimize_lineup,
)


def sample_rankings() -> pd.DataFrame:
    """Return a complete small fantasy roster with one extra FLEX player."""

    rows = []
    specifications = [
        ("qb1", "Quarter Back", "QB", 20.0, True),
        ("rb1", "Running One", "RB", 17.0, True),
        ("rb2", "Running Two", "RB", 15.0, True),
        ("rb3", "Running Three", "RB", 14.0, True),
        ("wr1", "Wide One", "WR", 18.0, True),
        ("wr2", "Wide Two", "WR", 16.0, True),
        ("wr3", "Wide Three", "WR", 13.0, True),
        ("te1", "Tight One", "TE", 12.0, True),
        ("te2", "Tight Two", "TE", 11.0, False),
    ]
    for rank, (player_id, name, position, points, eligible) in enumerate(
        specifications, start=1
    ):
        rows.append(
            {
                "player_id": player_id,
                "player_display_name": name,
                "position": position,
                "team": "AAA",
                "opponent": "BBB",
                "role_eligible": str(eligible),
                "display_projected_fantasy_points_ppr": points,
                "projected_fantasy_points_ppr": points,
                "position_rank": rank,
                "overall_flex_rank": rank,
                "remaining_flex_rank": rank,
                "prior_games_count": 5,
                "lineup_tier": (
                    "PROVISIONAL_STARTER" if eligible else "ROLE_FILTERED"
                ),
                "evidence_confidence": "HIGH",
                "risk_flags": "NONE",
                "recommendation_reason": "Synthetic test row",
            }
        )
    return normalize_rankings(pd.DataFrame(rows))


def test_optimizer_fills_legal_slots_and_best_remaining_flex() -> None:
    rankings = sample_rankings()
    lineup, gaps = optimize_lineup(rankings, rankings["player_id"])

    starters = lineup.loc[lineup["lineup_status"].eq("START")]
    assert gaps == []
    assert starters["recommended_slot"].value_counts().to_dict() == {
        "RB": 2,
        "WR": 2,
        "QB": 1,
        "TE": 1,
        "FLEX": 1,
    }
    assert starters.loc[
        starters["recommended_slot"].eq("FLEX"), "player_id"
    ].item() == "rb3"
    assert lineup.loc[lineup["player_id"].eq("te2"), "lineup_status"].item() == (
        "CHECK ROLE"
    )


def test_filter_and_comparison_preserve_requested_players() -> None:
    rankings = sample_rankings()
    filtered = filter_rankings(
        rankings,
        positions=["WR"],
        teams=["AAA"],
        tiers=["PROVISIONAL_STARTER"],
        confidence=["HIGH"],
        search_text="Wide",
    )
    assert filtered["player_id"].tolist() == ["wr1", "wr2", "wr3"]

    comparison = comparison_frame(rankings, ["qb1", "te1"])
    assert comparison["player_display_name"].tolist() == [
        "Quarter Back",
        "Tight One",
    ]
