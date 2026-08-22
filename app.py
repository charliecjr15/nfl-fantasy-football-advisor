"""Simple public Streamlit interface for the NFL fantasy advisor."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

from app_support import (
    comparison_frame,
    current_games,
    filter_completed_results,
    normalize_completed_results,
    normalize_rankings,
    optimize_lineup,
    selectable_players,
    top_projections,
)


PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_DIRECTORY = PROJECT_ROOT / "results" / "public"
RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_rankings.csv"
METADATA_PATH = PUBLIC_DIRECTORY / "latest_run.json"
COMPLETED_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_week_results.csv"

PLAYER_COLUMNS = [
    "player_display_name",
    "position",
    "team",
    "opponent",
    "display_projected_fantasy_points_ppr",
]
PLAYER_COLUMN_CONFIG = {
    "player_display_name": "Player",
    "position": "POS",
    "team": "Team",
    "opponent": "Opponent",
    "display_projected_fantasy_points_ppr": st.column_config.NumberColumn(
        "Projected PPR", format="%.2f"
    ),
}


st.set_page_config(
    page_title="Sunday Edge Fantasy Advisor",
    page_icon="🏈",
    layout="wide",
    initial_sidebar_state="collapsed",
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


@st.cache_data(show_spinner=False)
def load_completed_results(path: str) -> pd.DataFrame:
    """Read and normalize the separately published actual results."""

    return normalize_completed_results(pd.read_csv(path, low_memory=False))


def projection_table(dataframe: pd.DataFrame) -> None:
    """Display only the five requested player projection fields."""

    st.dataframe(
        dataframe[PLAYER_COLUMNS],
        hide_index=True,
        width="stretch",
        column_config=PLAYER_COLUMN_CONFIG,
    )


if not RANKINGS_PATH.exists() or not METADATA_PATH.exists():
    st.error("No validated weekly projections are available yet.")
    st.stop()

try:
    rankings = load_public_rankings(str(RANKINGS_PATH))
    metadata = load_public_metadata(str(METADATA_PATH))
    completed_results = (
        load_completed_results(str(COMPLETED_RESULTS_PATH))
        if COMPLETED_RESULTS_PATH.exists()
        else pd.DataFrame()
    )
except (OSError, ValueError, json.JSONDecodeError) as error:
    st.error(f"The weekly data could not be loaded: {error}")
    st.stop()


season = int(metadata["season"])
week = int(metadata["week"])
st.title("Sunday Edge Fantasy Advisor")
st.caption(f"{season} Week {week} full-PPR projections")

status = str(metadata.get("publication_status", "UNKNOWN"))
if "INJURY_CAVEAT" in status:
    st.warning(
        "Injury data is unavailable for this update. Check player status "
        "before setting your lineup."
    )
elif not status.startswith("PASS"):
    st.error("This weekly update is not ready for lineup decisions.")

(
    projections_tab,
    lineup_tab,
    compare_tab,
    games_tab,
    previous_tab,
) = st.tabs(
    [
        "Top projections",
        "My lineup",
        "Compare players",
        "This week's games",
        "Previous weeks",
    ]
)

with projections_tab:
    st.subheader("Highest projected players")
    filter_column, count_column = st.columns(2)
    with filter_column:
        selected_position = st.selectbox(
            "Position", ["All", "QB", "RB", "WR", "TE"]
        )
    with count_column:
        player_limit = st.selectbox(
            "Players to show", [10, 25, 50], index=1
        )
    leaders = top_projections(rankings, selected_position, player_limit)
    if leaders.empty:
        st.info("No players are available for this position.")
    else:
        projection_table(leaders)

with lineup_tab:
    st.subheader("My lineup")
    st.caption("Choose your roster to see the highest projected legal lineup.")
    player_map = selectable_players(rankings)
    selected_labels = st.multiselect(
        "Roster players",
        list(player_map),
        placeholder="Search and select your players",
    )
    if not selected_labels:
        st.info("Select your roster players to build a lineup.")
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
                    *PLAYER_COLUMNS,
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "recommended_slot": "Slot",
                "lineup_status": "Decision",
                **PLAYER_COLUMN_CONFIG,
            },
        )

with compare_tab:
    st.subheader("Compare players")
    comparison_map = selectable_players(rankings)
    comparison_labels = st.multiselect(
        "Players to compare",
        list(comparison_map),
        max_selections=4,
        placeholder="Select up to four players",
    )
    comparison = comparison_frame(
        rankings,
        [comparison_map[label] for label in comparison_labels],
    )
    if comparison.empty:
        st.info("Select at least one player to compare.")
    else:
        projection_table(comparison)

with games_tab:
    st.subheader(f"All games — Week {week}")
    games = current_games(rankings)
    st.dataframe(
        games,
        hide_index=True,
        width="stretch",
        column_config={"game_date": "Date", "matchup": "Matchup"},
    )

with previous_tab:
    st.subheader("Previous weeks")
    st.caption("Actual full-PPR points from completed games.")
    if completed_results.empty:
        st.info("Completed-week results will appear after games are played.")
    else:
        prior_seasons = sorted(
            completed_results["season"].astype(int).unique(), reverse=True
        )
        previous_filter_columns = st.columns(3)
        with previous_filter_columns[0]:
            prior_season = st.selectbox("Season", prior_seasons)
        available_weeks = sorted(
            completed_results.loc[
                completed_results["season"].eq(prior_season), "week"
            ]
            .astype(int)
            .unique(),
            reverse=True,
        )
        with previous_filter_columns[1]:
            prior_week = st.selectbox("Week", available_weeks)
        with previous_filter_columns[2]:
            prior_position = st.selectbox(
                "Position",
                ["All", "QB", "RB", "WR", "TE"],
                key="previous_position",
            )
        previous = filter_completed_results(
            completed_results, prior_season, prior_week, prior_position
        )
        st.dataframe(
            previous[
                [
                    "player_display_name",
                    "position",
                    "team",
                    "opponent",
                    "fantasy_points_ppr",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "position": "POS",
                "team": "Team",
                "opponent": "Opponent",
                "fantasy_points_ppr": st.column_config.NumberColumn(
                    "Actual PPR", format="%.2f"
                ),
            },
        )
