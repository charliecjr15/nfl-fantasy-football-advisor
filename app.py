"""Public Streamlit interface for the NFL fantasy-football advisor."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from app_support import (
    comparison_frame,
    filter_rankings,
    normalize_rankings,
    optimize_lineup,
    selectable_players,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RANKINGS_PATH = PROJECT_ROOT / "results" / "public" / "latest_rankings.csv"
METADATA_PATH = PROJECT_ROOT / "results" / "public" / "latest_run.json"


st.set_page_config(
    page_title="Sunday Edge Fantasy Advisor",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(show_spinner=False)
def load_public_rankings(path: str) -> pd.DataFrame:
    """Read and normalize the validated public snapshot."""

    return normalize_rankings(pd.read_csv(path, low_memory=False))


@st.cache_data(show_spinner=False)
def load_public_metadata(path: str) -> dict[str, object]:
    """Read the publication metadata."""

    with Path(path).open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def show_source_error() -> None:
    """Render a useful empty state when publication artifacts are absent."""

    st.error(
        "No validated public rankings are available. Run "
        "`python scripts/publish_latest.py --season YEAR --week WEEK` first."
    )
    st.stop()


if not RANKINGS_PATH.exists() or not METADATA_PATH.exists():
    show_source_error()

try:
    rankings = load_public_rankings(str(RANKINGS_PATH))
    metadata = load_public_metadata(str(METADATA_PATH))
except (OSError, ValueError, json.JSONDecodeError) as error:
    st.error(f"The published snapshot could not be loaded: {error}")
    st.stop()


st.title("Sunday Edge Fantasy Advisor")
st.caption(
    "Weekly full-PPR projections from a frozen, leakage-safe model bundle."
)

status = str(metadata.get("publication_status", "UNKNOWN"))
if "INJURY_CAVEAT" in status:
    st.warning(
        "Current injury-report data was unavailable for this build. Check "
        "official player availability before setting a lineup."
    )
elif not status.startswith("PASS"):
    st.error("This snapshot is not marked ready for lineup decisions.")

metric_columns = st.columns(5)
metric_columns[0].metric(
    "Projection week",
    f"{int(metadata['season'])} · Week {int(metadata['week'])}",
)
metric_columns[1].metric("Players scored", f"{len(rankings):,}")
metric_columns[2].metric(
    "Role eligible", f"{int(rankings['role_eligible'].sum()):,}"
)
metric_columns[3].metric(
    "Starter + FLEX pool",
    f"{int(rankings['lineup_tier'].isin(['PROVISIONAL_STARTER', 'PROVISIONAL_FLEX']).sum()):,}",
)
metric_columns[4].metric(
    "Games covered", f"{int(rankings['game_id'].nunique())}"
)

with st.sidebar:
    st.header("Rankings filters")
    position_values = sorted(
        rankings["position"].dropna().unique(),
        key=lambda value: {"QB": 0, "RB": 1, "WR": 2, "TE": 3}.get(
            value, 9
        ),
    )
    selected_positions = st.multiselect(
        "Position", position_values, default=position_values
    )
    team_values = sorted(rankings["team"].dropna().unique())
    selected_teams = st.multiselect(
        "Team", team_values, default=team_values
    )
    tier_values = [
        value
        for value in [
            "PROVISIONAL_STARTER",
            "PROVISIONAL_FLEX",
            "BENCH_DEPTH",
            "ROLE_FILTERED",
        ]
        if value in set(rankings["lineup_tier"])
    ]
    selected_tiers = st.multiselect(
        "Recommendation tier", tier_values, default=tier_values
    )
    confidence_values = sorted(
        rankings["evidence_confidence"].dropna().unique()
    )
    selected_confidence = st.multiselect(
        "Evidence confidence",
        confidence_values,
        default=confidence_values,
    )
    player_search = st.text_input("Search player")
    st.divider()
    st.caption(
        f"Source cutoff: {metadata.get('source_as_of_utc', 'Unavailable')}"
    )
    st.caption(
        "Evidence confidence describes historical coverage, not prediction "
        "certainty."
    )


filtered = filter_rankings(
    rankings,
    selected_positions,
    selected_teams,
    selected_tiers,
    selected_confidence,
    player_search,
)

rankings_tab, lineup_tab, compare_tab, method_tab = st.tabs(
    ["Weekly rankings", "My lineup", "Compare players", "Methodology"]
)

with rankings_tab:
    st.subheader("Highest projected players")
    if filtered.empty:
        st.info("No players match the selected filters.")
    else:
        chart_rows = filtered.head(20).copy()
        chart_rows["player"] = (
            chart_rows["player_display_name"]
            + " ("
            + chart_rows["position"]
            + ")"
        )
        st.bar_chart(
            chart_rows.set_index("player")[
                "display_projected_fantasy_points_ppr"
            ],
            horizontal=True,
            x_label="Projected full-PPR points",
            y_label="Player",
        )
        st.dataframe(
            filtered[
                [
                    "player_display_name",
                    "position",
                    "team",
                    "opponent",
                    "display_projected_fantasy_points_ppr",
                    "position_rank",
                    "overall_flex_rank",
                    "projected_lineup_slot",
                    "lineup_tier",
                    "evidence_confidence",
                    "risk_flags",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "position": "POS",
                "team": "Team",
                "opponent": "Opponent",
                "display_projected_fantasy_points_ppr": st.column_config.NumberColumn(
                    "Projected PPR", format="%.2f"
                ),
                "position_rank": st.column_config.NumberColumn(
                    "Position rank", format="%d"
                ),
                "overall_flex_rank": st.column_config.NumberColumn(
                    "FLEX rank", format="%d"
                ),
            },
        )
        st.download_button(
            "Download filtered rankings",
            data=filtered.drop(columns="player_label").to_csv(index=False),
            file_name=(
                f"fantasy_rankings_{int(metadata['season'])}_"
                f"week_{int(metadata['week']):02d}.csv"
            ),
            mime="text/csv",
        )

with lineup_tab:
    st.subheader("Choose your roster")
    st.write(
        "Select your players. The advisor fills 1 QB, 2 RB, 2 WR, 1 TE, "
        "and 1 FLEX using the displayed projections."
    )
    player_map = selectable_players(rankings)
    selected_labels = st.multiselect(
        "Roster players",
        list(player_map),
        placeholder="Search and select players",
    )
    if not selected_labels:
        st.info("Select roster players to generate a lineup.")
    else:
        lineup, gaps = optimize_lineup(
            rankings, [player_map[label] for label in selected_labels]
        )
        if gaps:
            st.warning("Roster gaps: " + "; ".join(gaps))
        st.dataframe(
            lineup[
                [
                    "recommended_slot",
                    "lineup_status",
                    "player_display_name",
                    "position",
                    "team",
                    "opponent",
                    "display_projected_fantasy_points_ppr",
                    "evidence_confidence",
                    "risk_flags",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "recommended_slot": "Recommended slot",
                "lineup_status": "Decision",
                "player_display_name": "Player",
                "display_projected_fantasy_points_ppr": st.column_config.NumberColumn(
                    "Projected PPR", format="%.2f"
                ),
            },
        )

with compare_tab:
    st.subheader("Compare up to four players")
    comparison_map = selectable_players(rankings)
    default_comparisons = list(comparison_map)[:2]
    comparison_labels = st.multiselect(
        "Players to compare",
        list(comparison_map),
        default=default_comparisons,
        max_selections=4,
    )
    comparison = comparison_frame(
        rankings,
        [comparison_map[label] for label in comparison_labels],
    )
    if comparison.empty:
        st.info("Select at least one player to compare.")
    else:
        st.bar_chart(
            comparison.set_index("player_display_name")[
                "display_projected_fantasy_points_ppr"
            ],
            x_label="Player",
            y_label="Projected full-PPR points",
        )
        st.dataframe(
            comparison,
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "display_projected_fantasy_points_ppr": st.column_config.NumberColumn(
                    "Projected PPR", format="%.2f"
                ),
            },
        )

with method_tab:
    st.subheader("How to use these projections")
    st.markdown(
        """
        - Projections estimate full-PPR points conditional on a player appearing.
        - Position rank compares role-eligible players at the same position.
        - Overall FLEX rank compares role-eligible RB, WR, and TE players.
        - Recommendations support lineup decisions; they are not guarantees.
        - Verify injuries, inactive lists, weather, and late role changes before kickoff.
        """
    )
    st.json(
        {
            "model_bundle": metadata.get("model_bundle_version"),
            "ranking_version": metadata.get("ranking_version"),
            "ranking_run_utc": metadata.get("ranking_run_timestamp_utc"),
            "published_utc": metadata.get("published_at_utc"),
            "status": metadata.get("publication_status"),
        },
        expanded=False,
    )
