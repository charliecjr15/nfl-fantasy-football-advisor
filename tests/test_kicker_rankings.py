"""Tests for ESPN and Yahoo kicker scoring and projections."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_kicker_rankings import (  # noqa: E402
    projection_candidates,
    score_kicker_games,
)


def scoring_sample(**overrides: int) -> pd.DataFrame:
    """Return one zero-filled kicker scoring row."""

    row = {
        "field_goals_made_0_19": 0,
        "field_goals_made_20_29": 0,
        "field_goals_made_30_39": 0,
        "field_goals_made_40_49": 0,
        "field_goals_made_50_59": 0,
        "field_goals_made_60_plus": 0,
        "extra_points_made": 0,
        "field_goals_missed": 0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_espn_and_yahoo_kicker_profiles_differ_as_documented() -> None:
    long_field_goal = score_kicker_games(
        scoring_sample(field_goals_made_60_plus=1)
    )
    miss = score_kicker_games(scoring_sample(field_goals_missed=1))

    assert long_field_goal["espn_fantasy_points"].item() == 6.0
    assert long_field_goal["yahoo_fantasy_points"].item() == 5.0
    assert miss["espn_fantasy_points"].item() == -1.0
    assert miss["yahoo_fantasy_points"].item() == 0.0


def test_projection_candidates_use_only_prior_games() -> None:
    history = pd.DataFrame(
        [
            {
                "season": 2025,
                "week": 1,
                "game_id": "g1",
                "game_date": "2025-09-01",
                "team": "AAA",
                "opponent": "BBB",
                "espn_fantasy_points": 4.0,
            },
            {
                "season": 2025,
                "week": 2,
                "game_id": "g2",
                "game_date": "2025-09-08",
                "team": "AAA",
                "opponent": "CCC",
                "espn_fantasy_points": 20.0,
            },
        ]
    )

    candidates = projection_candidates(history, "espn_fantasy_points")

    assert candidates.loc[1, "team_last_3"] == 4.0
    assert candidates.loc[1, "team_last_5"] == 4.0


def test_week_one_kicker_snapshot_has_one_player_per_team() -> None:
    rankings = pd.read_csv(
        PROJECT_ROOT
        / "results"
        / "tables"
        / "kicker_rankings_2026_week_01.csv"
    )

    assert len(rankings) == 32
    assert rankings["team"].nunique() == 32
    assert rankings["player_id"].nunique() == 32
    assert rankings["game_id"].nunique() == 16
    assert set(rankings["position"]) == {"K"}
    assert set(rankings["espn_rank"]) == set(range(1, 33))
    assert set(rankings["yahoo_rank"]) == set(range(1, 33))
