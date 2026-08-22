"""Tests for public snapshot promotion and Streamlit rendering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from publish_latest import (  # noqa: E402
    publish,
    validate_completed_results,
    validate_publication,
)


def test_week_one_snapshot_passes_publication_contract() -> None:
    rankings_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01.csv"
    )
    manifest_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01_manifest.csv"
    )
    rankings, manifest, summary = validate_publication(
        rankings_path, manifest_path, 2026, 1
    )
    assert len(rankings) == 808
    assert summary["role_eligible_rows"] == 283
    assert summary["projected_lineup_rows"] == 84
    assert manifest["ranking_status"] == "PASS_WITH_INJURY_CAVEAT"


def test_publish_writes_matching_public_files(tmp_path: Path) -> None:
    rankings_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01.csv"
    )
    manifest_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01_manifest.csv"
    )
    public_rankings = tmp_path / "latest_rankings.csv"
    public_metadata = tmp_path / "latest_run.json"
    payload = publish(
        rankings_path,
        manifest_path,
        public_rankings,
        public_metadata,
        2026,
        1,
    )
    reopened = json.loads(public_metadata.read_text(encoding="utf-8"))
    assert public_rankings.exists()
    assert reopened["rankings_sha256"] == payload["rankings_sha256"]
    assert reopened["publication_status"] == "PASS_WITH_INJURY_CAVEAT"


def test_republishing_identical_snapshot_is_a_no_op(tmp_path: Path) -> None:
    rankings_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01.csv"
    )
    manifest_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01_manifest.csv"
    )
    public_rankings = tmp_path / "latest_rankings.csv"
    public_metadata = tmp_path / "latest_run.json"
    first_payload = publish(
        rankings_path,
        manifest_path,
        public_rankings,
        public_metadata,
        2026,
        1,
    )
    rankings_bytes = public_rankings.read_bytes()
    metadata_bytes = public_metadata.read_bytes()

    second_payload = publish(
        rankings_path,
        manifest_path,
        public_rankings,
        public_metadata,
        2026,
        1,
    )

    assert second_payload == first_payload
    assert public_rankings.read_bytes() == rankings_bytes
    assert public_metadata.read_bytes() == metadata_bytes


def test_completed_results_pass_publication_contract() -> None:
    completed_path = (
        PROJECT_ROOT / "results" / "public" / "completed_week_results.csv"
    )
    completed, summary = validate_completed_results(
        completed_path, 2026, 1
    )
    assert set(completed["season"]) == {2025}
    assert summary["completed_results_rows"] == 6037
    assert summary["completed_results_latest_season"] == 2025
    assert summary["completed_results_latest_week"] == 18


def test_completed_results_reject_projection_week(tmp_path: Path) -> None:
    source = pd.read_csv(
        PROJECT_ROOT / "results" / "public" / "completed_week_results.csv"
    ).head(1)
    source["season"] = 2026
    source["week"] = 1
    invalid_path = tmp_path / "future_results.csv"
    source.to_csv(invalid_path, index=False)

    with pytest.raises(ValueError, match="projection week"):
        validate_completed_results(invalid_path, 2026, 1)


def test_publish_includes_validated_completed_results(tmp_path: Path) -> None:
    rankings_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01.csv"
    )
    manifest_path = (
        PROJECT_ROOT
        / "results"
        / "tables"
        / "weekly_rankings_2026_week_01_manifest.csv"
    )
    completed_path = (
        PROJECT_ROOT / "results" / "public" / "completed_week_results.csv"
    )
    public_rankings = tmp_path / "latest_rankings.csv"
    public_metadata = tmp_path / "latest_run.json"
    public_completed = tmp_path / "completed_week_results.csv"

    payload = publish(
        rankings_path,
        manifest_path,
        public_rankings,
        public_metadata,
        2026,
        1,
        completed_path,
        public_completed,
    )

    assert public_completed.exists()
    assert payload["completed_results_rows"] == 6037
    assert payload["completed_results_sha256"]


def test_streamlit_default_view_is_compact_and_has_five_tabs() -> None:
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert len(app.tabs) == 5
    assert [tab.label for tab in app.tabs] == [
        "Top projections",
        "My lineup",
        "Compare players",
        "This week's games",
        "Previous weeks",
    ]
    assert len(app.metric) == 0
    assert len(app.warning) == 1
    assert len(app.dataframe) == 3
    assert len(app.get("vega_lite_chart")) == 0
    assert list(app.dataframe[0].value.columns) == [
        "player_display_name",
        "position",
        "team",
        "opponent",
        "display_projected_fantasy_points_ppr",
    ]
