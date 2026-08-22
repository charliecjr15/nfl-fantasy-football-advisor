"""Tests for public snapshot promotion and Streamlit rendering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from publish_latest import publish, validate_publication  # noqa: E402


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


def test_streamlit_default_view_renders_chart_and_tables() -> None:
    app = AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=30)
    app.run()
    assert not app.exception
    assert len(app.metric) == 5
    assert len(app.warning) == 1
    assert len(app.dataframe) >= 2
    assert len(app.get("vega_lite_chart")) >= 1
