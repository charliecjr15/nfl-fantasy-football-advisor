"""Tests for ESPN and Yahoo team D/ST scoring and projections."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_dst_rankings as dst  # noqa: E402


def test_official_default_points_allowed_bands() -> None:
    assert [
        dst.points_allowed_score(value, "espn")
        for value in [0, 6, 13, 17, 27, 34, 45, 46]
    ] == [5, 4, 3, 1, 0, -1, -3, -5]
    assert [
        dst.points_allowed_score(value, "yahoo")
        for value in [0, 6, 13, 20, 27, 34, 35]
    ] == [10, 7, 4, 1, 0, -1, -4]
    assert [
        dst.yards_allowed_score(value)
        for value in [99, 199, 299, 349, 399, 449, 499, 549, 550]
    ] == [5, 3, 2, 0, -1, -3, -5, -6, -7]


def test_team_game_scoring_uses_platform_specific_bands() -> None:
    facts = pd.DataFrame(
        [
            {
                "sacks": 3,
                "interceptions": 2,
                "fumble_recoveries": 1,
                "defensive_touchdowns": 1,
                "special_teams_touchdowns": 1,
                "blocked_kicks": 1,
                "safeties": 1,
                "points_allowed": 10,
                "yards_allowed": 250,
            }
        ]
    )

    scored = dst.score_team_games(facts)

    assert scored["espn_fantasy_points"].item() == 30
    assert scored["yahoo_fantasy_points"].item() == 29


def test_public_dst_snapshot_has_complete_week_one_coverage() -> None:
    rankings = pd.read_csv(
        PROJECT_ROOT
        / "results"
        / "tables"
        / "dst_rankings_2026_week_01.csv"
    )
    completed = pd.read_csv(
        PROJECT_ROOT / "results" / "public" / "completed_dst_results.csv"
    )

    assert len(rankings) == 32
    assert rankings["team"].nunique() == 32
    assert rankings["game_id"].nunique() == 16
    assert len(completed) == 544
    assert set(completed["season"]) == {2025}
    assert set(completed["week"]) == set(range(1, 19))
    assert not completed.duplicated(
        ["season", "week", "game_id", "team"]
    ).any()
