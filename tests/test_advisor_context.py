"""Tests for the public schedule, uncertainty, and game-context artifacts."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_advisor_context import (  # noqa: E402
    build_game_context,
    build_projection_calibration,
    classify_weather_risk,
    forecast_for_game,
    sha256_file,
)


def test_projection_calibration_covers_every_offensive_position() -> None:
    rows: list[dict[str, object]] = []
    for position in ["QB", "RB", "WR", "TE"]:
        for value in range(10):
            rows.append(
                {
                    "season": 2024,
                    "position": position,
                    "target_fantasy_points_ppr": float(value + 2),
                    "prediction_position_champion": float(value),
                }
            )
    validation = pd.DataFrame(rows)
    test = validation.assign(season=2025)

    calibration = build_projection_calibration(validation, test)

    assert calibration["position"].tolist() == ["QB", "RB", "WR", "TE"]
    assert calibration["lower_residual"].eq(2).all()
    assert calibration["upper_residual"].eq(2).all()
    assert calibration["test_coverage_pct"].eq(100).all()


def test_weather_risk_and_forecast_window_are_explicit() -> None:
    assert classify_weather_risk(31, 22, 34, 70) == (
        "HIGH_WIND | STRONG_GUSTS | PRECIPITATION | FREEZING"
    )
    assert classify_weather_risk(70, 5, 8, 10) == "LOW_WEATHER_RISK"

    future_game = pd.Series(
        {
            "roof": "outdoors",
            "gameday": "2026-09-13",
            "gametime": "13:00",
            "temp": None,
            "wind": None,
            "latitude": 40.0,
            "longitude": -75.0,
        }
    )
    result = forecast_for_game(
        future_game,
        datetime(2026, 8, 23, tzinfo=timezone.utc),
        lambda _latitude, _longitude: (_ for _ in ()).throw(
            AssertionError("Fetcher should not run outside the forecast window.")
        ),
    )
    assert result["forecast_status"] == "FORECAST_NOT_AVAILABLE_YET"
    assert result["weather_risk"] == "FORECAST_PENDING"


def test_game_context_accepts_a_bye_week_slate() -> None:
    schedule = pd.DataFrame(
        [
            {
                "season": 2026,
                "week": 7,
                "game_id": "2026_07_AAA_BBB",
                "gameday": "2026-10-25",
                "gametime": "13:00",
                "away_team": "AAA",
                "home_team": "BBB",
                "stadium": "Test Dome",
                "venue_label": "Test City",
                "roof": "dome",
                "surface": "turf",
                "spread_line": 1.5,
                "total_line": 42.0,
                "temp": None,
                "wind": None,
                "latitude": 40.0,
                "longitude": -75.0,
            }
        ]
    )

    context = build_game_context(
        schedule,
        7,
        datetime(2026, 10, 1, tzinfo=timezone.utc),
    )

    assert len(context) == 1
    assert context.iloc[0]["forecast_status"] == "INDOORS"
    assert context.iloc[0]["matchup"] == "AAA @ BBB"


def test_committed_advisor_context_is_self_consistent() -> None:
    public = PROJECT_ROOT / "results" / "public"
    manifest = json.loads(
        (public / "advisor_context.json").read_text(encoding="utf-8")
    )
    assert manifest["context_status"] == "PASS"
    assert manifest["season"] == 2026
    assert manifest["week"] == 1

    expectations = {
        "projection_calibration": ("projection_calibration.csv", 4),
        "model_accuracy": ("model_accuracy.csv", 5),
        "season_schedule": ("season_schedule.csv", 272),
        "game_context": ("game_context.csv", 16),
    }
    for key, (filename, expected_rows) in expectations.items():
        path = public / filename
        assert len(pd.read_csv(path)) == expected_rows
        assert manifest[key]["rows"] == expected_rows
        assert manifest[key]["sha256"] == sha256_file(path)

    schedule = pd.read_csv(public / "season_schedule.csv")
    game_context = pd.read_csv(public / "game_context.csv")
    assert not schedule[["season", "week", "game_id"]].duplicated().any()
    assert set(schedule["week"]) == set(range(1, 19))
    assert game_context["game_id"].is_unique
    assert set(game_context["week"]) == {1}
    assert set(game_context["forecast_status"]) == {
        "FORECAST_NOT_AVAILABLE_YET",
        "INDOORS",
    }
