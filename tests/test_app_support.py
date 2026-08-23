"""Tests for public-app filtering, comparison, and lineup logic."""

from __future__ import annotations

import pandas as pd

from app_support import (
    comparison_frame,
    current_games,
    dst_projection_frame,
    filter_completed_kicker_results,
    filter_completed_dst_results,
    filter_completed_results,
    filter_rankings,
    flex_projections,
    kicker_projection_frame,
    normalize_completed_kicker_results,
    normalize_completed_dst_results,
    normalize_completed_results,
    normalize_dst_rankings,
    normalize_kicker_rankings,
    normalize_rankings,
    optimize_lineup,
    search_projection_pool,
    season_totals_frame,
    top_projections,
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
                "season": 2026,
                "week": 1,
                "game_id": "2026_01_AAA_BBB",
                "game_date": "2026-09-10",
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
    assert list(comparison.columns) == [
        "player_display_name",
        "position",
        "team",
        "opponent",
        "display_projected_fantasy_points_ppr",
    ]


def test_top_projections_and_games_are_compact() -> None:
    rankings = sample_rankings()

    leaders = top_projections(rankings, position="WR", limit=2)
    games = current_games(rankings)

    assert leaders["player_id"].tolist() == ["wr1", "wr2"]
    assert games.to_dict("records") == [
        {"game_date": "Thu, Sep 10", "matchup": "AAA vs BBB"}
    ]


def test_projection_search_matches_player_team_position_and_opponent() -> None:
    rankings = sample_rankings()

    assert search_projection_pool(
        rankings, "wide one"
    )["player_id"].tolist() == ["wr1"]
    assert len(search_projection_pool(rankings, "AAA")) == len(rankings)
    assert len(search_projection_pool(rankings, "QB")) == 1
    assert len(search_projection_pool(rankings, "BBB")) == len(rankings)
    assert search_projection_pool(rankings, "").equals(rankings)


def test_flex_projections_include_only_rb_wr_and_te() -> None:
    rankings = sample_rankings()

    flex = flex_projections(rankings, limit=4)

    assert flex["position"].tolist() == ["WR", "RB", "WR", "RB"]
    assert "QB" not in set(flex["position"])


def test_previous_week_results_filter_to_requested_week_and_position() -> None:
    completed = normalize_completed_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-1",
                    "game_date": "2026-01-03",
                    "player_id": "rb1",
                    "player_display_name": "Running One",
                    "position": "RB",
                    "team": "AAA",
                    "opponent": "BBB",
                    "fantasy_points_ppr": 22.5,
                },
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-1",
                    "game_date": "2026-01-03",
                    "player_id": "wr1",
                    "player_display_name": "Wide One",
                    "position": "WR",
                    "team": "AAA",
                    "opponent": "BBB",
                    "fantasy_points_ppr": 18.0,
                },
            ]
        )
    )

    selected = filter_completed_results(completed, 2025, 18, "RB")

    assert selected["player_id"].tolist() == ["rb1"]
    assert selected["fantasy_points_ppr"].item() == 22.5


def test_dst_helpers_switch_between_espn_and_yahoo() -> None:
    rankings = normalize_dst_rankings(
        pd.DataFrame(
            [
                {
                    "season": 2026,
                    "week": 1,
                    "game_id": "game-1",
                    "game_date": "2026-09-10",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_projected_points": 8.5,
                    "espn_rank": 1,
                    "yahoo_projected_points": 7.0,
                    "yahoo_rank": 2,
                },
                {
                    "season": 2026,
                    "week": 1,
                    "game_id": "game-1",
                    "game_date": "2026-09-10",
                    "team": "BBB",
                    "opponent": "AAA",
                    "espn_projected_points": 6.0,
                    "espn_rank": 2,
                    "yahoo_projected_points": 9.0,
                    "yahoo_rank": 1,
                },
            ]
        )
    )
    completed = normalize_completed_dst_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_fantasy_points": 12.0,
                    "yahoo_fantasy_points": 10.0,
                }
            ]
        )
    )

    yahoo = dst_projection_frame(rankings, "Yahoo")
    actual = filter_completed_dst_results(completed, 2025, 18, "ESPN")

    assert yahoo["team"].tolist() == ["BBB", "AAA"]
    assert yahoo["projected_points"].tolist() == [9.0, 7.0]
    assert actual.to_dict("records") == [
        {"team": "AAA", "opponent": "BBB", "actual_points": 12.0}
    ]


def test_kicker_helpers_and_season_totals_switch_profiles() -> None:
    rankings = normalize_kicker_rankings(
        pd.DataFrame(
            [
                {
                    "season": 2026,
                    "week": 1,
                    "game_id": "game-1",
                    "game_date": "2026-09-10",
                    "player_id": "k1",
                    "player_display_name": "Kicker One",
                    "position": "K",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_projected_points": 8.0,
                    "espn_rank": 2,
                    "yahoo_projected_points": 10.0,
                    "yahoo_rank": 1,
                }
            ]
        )
    )
    completed_kickers = normalize_completed_kicker_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "player_id": "k1",
                    "player_display_name": "Kicker One",
                    "position": "K",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_fantasy_points": 9.0,
                    "yahoo_fantasy_points": 11.0,
                }
            ]
        )
    )
    completed_players = normalize_completed_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "player_id": "rb1",
                    "player_display_name": "Running One",
                    "position": "RB",
                    "team": "AAA",
                    "opponent": "BBB",
                    "fantasy_points_ppr": 20.0,
                }
            ]
        )
    )

    yahoo = kicker_projection_frame(rankings, "Yahoo")
    previous = filter_completed_kicker_results(
        completed_kickers, 2025, 18, "ESPN"
    )
    totals = season_totals_frame(
        completed_players, completed_kickers, 2025, "All", "Yahoo"
    )

    assert yahoo["projected_points"].tolist() == [10.0]
    assert previous["actual_points"].tolist() == [9.0]
    assert totals[["player_display_name", "total_points"]].to_dict(
        "records"
    ) == [
        {"player_display_name": "Running One", "total_points": 20.0},
        {"player_display_name": "Kicker One", "total_points": 11.0},
    ]


def test_season_totals_can_include_dst_under_selected_profile() -> None:
    completed_players = normalize_completed_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "player_id": "rb1",
                    "player_display_name": "Running One",
                    "position": "RB",
                    "team": "AAA",
                    "opponent": "BBB",
                    "fantasy_points_ppr": 20.0,
                }
            ]
        )
    )
    completed_kickers = normalize_completed_kicker_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "player_id": "k1",
                    "player_display_name": "Kicker One",
                    "position": "K",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_fantasy_points": 9.0,
                    "yahoo_fantasy_points": 11.0,
                }
            ]
        )
    )
    completed_dst = normalize_completed_dst_results(
        pd.DataFrame(
            [
                {
                    "season": 2025,
                    "week": 18,
                    "game_id": "game-0",
                    "game_date": "2026-01-03",
                    "team": "AAA",
                    "opponent": "BBB",
                    "espn_fantasy_points": 12.0,
                    "yahoo_fantasy_points": 10.0,
                }
            ]
        )
    )

    totals = season_totals_frame(
        completed_players,
        completed_kickers,
        2025,
        "D/ST",
        "Yahoo",
        completed_dst,
        "Yahoo",
    )

    assert totals.to_dict("records") == [
        {
            "player_display_name": "AAA D/ST",
            "position": "D/ST",
            "team": "AAA",
            "total_points": 10.0,
        }
    ]
