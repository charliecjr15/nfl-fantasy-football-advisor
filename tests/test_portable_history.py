"""Regression evidence for portable history and frozen feature parity."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_future_features as future  # noqa: E402


def test_portable_history_reproduces_week_18_replay() -> None:
    player_path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "runtime_history"
        / "player_game_history.parquet"
    )
    opponent_path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "runtime_history"
        / "opponent_position_week_history.parquet"
    )
    reference_path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "future_features"
        / "2025_week_18_replay_features.parquet"
    )
    if not all(path.exists() for path in [player_path, opponent_path, reference_path]):
        pytest.skip("Local ignored parity artifacts are unavailable.")

    with (PROJECT_ROOT / "config" / "future_features_settings.toml").open(
        "rb"
    ) as file_handle:
        configuration = tomllib.load(file_handle)
    with (PROJECT_ROOT / "config" / "model_settings.toml").open(
        "rb"
    ) as file_handle:
        model_settings = tomllib.load(file_handle)
    metadata, _, numeric, output_columns = future.configured_contract(
        model_settings, configuration
    )

    expected = pd.read_parquet(reference_path)
    candidates = expected[
        metadata + future.CURRENT_CONTEXT_COLUMNS
    ].copy()
    player_history, opponent_history, _ = future.load_prior_history_files(
        player_path,
        opponent_path,
        configuration,
        2025,
        18,
    )
    actual = future.build_future_features(
        candidates,
        player_history,
        opponent_history,
        output_columns,
    )
    actual = actual[output_columns].sort_values(
        ["season", "week", "player_id"]
    ).reset_index(drop=True)
    expected = expected[output_columns].sort_values(
        ["season", "week", "player_id"]
    ).reset_index(drop=True)

    nonnumeric = [column for column in output_columns if column not in numeric]
    pd.testing.assert_frame_equal(
        actual[nonnumeric], expected[nonnumeric], check_dtype=False
    )
    np.testing.assert_allclose(
        actual[numeric].to_numpy(dtype=float),
        expected[numeric].to_numpy(dtype=float),
        rtol=0,
        atol=1e-10,
        equal_nan=True,
    )
