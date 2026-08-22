"""Simple public Streamlit interface for the NFL fantasy advisor."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pandas as pd
import streamlit as st

import app_support as _app_support


# Streamlit can rerun this file while retaining an older imported helper module.
# Reload it so an app deployment and its matching helper changes stay in sync.
_app_support = importlib.reload(_app_support)
comparison_frame = _app_support.comparison_frame
current_games = _app_support.current_games
dst_projection_frame = _app_support.dst_projection_frame
filter_completed_kicker_results = _app_support.filter_completed_kicker_results
filter_completed_dst_results = _app_support.filter_completed_dst_results
filter_completed_results = _app_support.filter_completed_results
flex_projections = _app_support.flex_projections
kicker_projection_frame = _app_support.kicker_projection_frame
normalize_completed_kicker_results = _app_support.normalize_completed_kicker_results
normalize_completed_dst_results = _app_support.normalize_completed_dst_results
normalize_completed_results = _app_support.normalize_completed_results
normalize_kicker_rankings = _app_support.normalize_kicker_rankings
normalize_dst_rankings = _app_support.normalize_dst_rankings
normalize_rankings = _app_support.normalize_rankings
optimize_lineup = _app_support.optimize_lineup
season_totals_frame = _app_support.season_totals_frame
selectable_kickers = _app_support.selectable_kickers
selectable_players = _app_support.selectable_players
top_projections = _app_support.top_projections


PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_DIRECTORY = PROJECT_ROOT / "results" / "public"
RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_rankings.csv"
METADATA_PATH = PUBLIC_DIRECTORY / "latest_run.json"
COMPLETED_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_week_results.csv"
DST_RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_dst_rankings.csv"
COMPLETED_DST_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_dst_results.csv"
KICKER_RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_kicker_rankings.csv"
COMPLETED_KICKER_RESULTS_PATH = (
    PUBLIC_DIRECTORY / "completed_kicker_results.csv"
)

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


@st.cache_data(show_spinner=False)
def load_dst_rankings(path: str) -> pd.DataFrame:
    """Read and normalize the separately validated D/ST projections."""

    return normalize_dst_rankings(pd.read_csv(path, low_memory=False))


@st.cache_data(show_spinner=False)
def load_completed_dst_results(path: str) -> pd.DataFrame:
    """Read and normalize actual team D/ST scores."""

    return normalize_completed_dst_results(pd.read_csv(path, low_memory=False))


@st.cache_data(show_spinner=False)
def load_kicker_rankings(path: str) -> pd.DataFrame:
    """Read and normalize separately validated kicker projections."""

    return normalize_kicker_rankings(pd.read_csv(path, low_memory=False))


@st.cache_data(show_spinner=False)
def load_completed_kicker_results(path: str) -> pd.DataFrame:
    """Read and normalize actual kicker scores."""

    return normalize_completed_kicker_results(
        pd.read_csv(path, low_memory=False)
    )


def projection_table(dataframe: pd.DataFrame) -> None:
    """Display only the five requested player projection fields."""

    st.dataframe(
        dataframe[PLAYER_COLUMNS],
        hide_index=True,
        width="stretch",
        column_config=PLAYER_COLUMN_CONFIG,
    )


def dst_table(dataframe: pd.DataFrame, points_label: str) -> None:
    """Display a compact D/ST team, opponent, and points table."""

    st.dataframe(
        dataframe[["team", "opponent", "projected_points"]],
        hide_index=True,
        width="stretch",
        column_config={
            "team": "Defense",
            "opponent": "Opponent",
            "projected_points": st.column_config.NumberColumn(
                points_label, format="%.2f"
            ),
        },
    )


def kicker_table(dataframe: pd.DataFrame, points_column: str) -> None:
    """Display compact player, position, matchup, and kicker points."""

    st.dataframe(
        dataframe[
            [
                "player_display_name",
                "position",
                "team",
                "opponent",
                points_column,
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "player_display_name": "Player",
            "position": "POS",
            "team": "Team",
            "opponent": "Opponent",
            points_column: st.column_config.NumberColumn(
                "Projected Points", format="%.2f"
            ),
        },
    )


required_public_files = [
    RANKINGS_PATH,
    METADATA_PATH,
    COMPLETED_RESULTS_PATH,
    DST_RANKINGS_PATH,
    COMPLETED_DST_RESULTS_PATH,
    KICKER_RANKINGS_PATH,
    COMPLETED_KICKER_RESULTS_PATH,
]
if not all(path.exists() for path in required_public_files):
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
    dst_rankings = load_dst_rankings(str(DST_RANKINGS_PATH))
    completed_dst_results = load_completed_dst_results(
        str(COMPLETED_DST_RESULTS_PATH)
    )
    kicker_rankings = load_kicker_rankings(str(KICKER_RANKINGS_PATH))
    completed_kicker_results = load_completed_kicker_results(
        str(COMPLETED_KICKER_RESULTS_PATH)
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
    flex_tab,
    kickers_tab,
    dst_tab,
    games_tab,
    previous_tab,
    season_totals_tab,
) = st.tabs(
    [
        "Top projections",
        "My lineup",
        "Compare players",
        "Flex",
        "Kickers",
        "D/ST",
        "This week's games",
        "Previous weeks",
        "Season totals",
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
    st.markdown("#### Kicker")
    lineup_kicker_columns = st.columns(2)
    with lineup_kicker_columns[0]:
        lineup_kicker_profile = st.selectbox(
            "Kicker scoring",
            ["ESPN", "Yahoo"],
            key="lineup_kicker_scoring",
        )
    kicker_map = selectable_kickers(kicker_rankings)
    with lineup_kicker_columns[1]:
        selected_kicker = st.selectbox(
            "Your kicker",
            ["None", *kicker_map],
            key="lineup_kicker",
        )
    if selected_kicker != "None":
        kicker_projection = kicker_projection_frame(
            kicker_rankings, lineup_kicker_profile
        )
        kicker_projection = kicker_projection.loc[
            kicker_projection["player_id"].astype(str).eq(
                str(kicker_map[selected_kicker])
            )
        ]
        kicker_table(kicker_projection, "projected_points")

    st.markdown("#### Defense/Special Teams")
    defense_map = dict(
        zip(dst_rankings["defense_label"], dst_rankings["team"])
    )
    defense_columns = st.columns(2)
    with defense_columns[0]:
        lineup_dst_profile = st.selectbox(
            "D/ST scoring", ["ESPN", "Yahoo"], key="lineup_dst_scoring"
        )
    with defense_columns[1]:
        selected_defense = st.selectbox(
            "Your D/ST",
            ["None", *defense_map],
            key="lineup_defense",
        )
    if selected_defense != "None":
        defense_projection = dst_projection_frame(
            dst_rankings, lineup_dst_profile
        )
        defense_projection = defense_projection.loc[
            defense_projection["team"].eq(defense_map[selected_defense])
        ]
        dst_table(defense_projection, "Projected Points")

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

with flex_tab:
    st.subheader("Flex projections")
    st.caption("RB, WR, and TE players eligible for your FLEX spot.")
    flex_limit = st.selectbox(
        "Players to show", [10, 25, 50], index=1, key="flex_limit"
    )
    flex_players = flex_projections(rankings, flex_limit)
    projection_table(flex_players)

with kickers_tab:
    st.subheader("Kicker projections")
    st.caption(
        "Choose your platform's default scoring. Check the final depth chart "
        "before kickoff."
    )
    kicker_profile = st.selectbox(
        "Scoring", ["ESPN", "Yahoo"], key="kicker_tab_scoring"
    )
    kicker_projections = kicker_projection_frame(
        kicker_rankings, kicker_profile
    )
    kicker_table(kicker_projections, "projected_points")

with dst_tab:
    st.subheader("Defense/Special Teams projections")
    st.caption(
        "Choose your platform's default scoring. Custom league settings may "
        "produce different totals."
    )
    dst_profile = st.selectbox(
        "Scoring", ["ESPN", "Yahoo"], key="dst_tab_scoring"
    )
    dst_projections = dst_projection_frame(dst_rankings, dst_profile)
    dst_table(dst_projections, "Projected Points")

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
    result_type = st.radio(
        "Results", ["Players", "Kickers", "D/ST"], horizontal=True
    )
    if result_type == "Players":
        st.caption("Actual full-PPR points from completed games.")
        prior_seasons = sorted(
            completed_results["season"].astype(int).unique(), reverse=True
        )
        previous_filter_columns = st.columns(3)
        with previous_filter_columns[0]:
            prior_season = st.selectbox(
                "Season", prior_seasons, key="player_history_season"
            )
        available_weeks = sorted(
            completed_results.loc[
                completed_results["season"].eq(prior_season), "week"
            ]
            .astype(int)
            .unique(),
            reverse=True,
        )
        with previous_filter_columns[1]:
            prior_week = st.selectbox(
                "Week", available_weeks, key="player_history_week"
            )
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
    elif result_type == "Kickers":
        st.caption("Actual kicker points using the selected platform default.")
        kicker_seasons = sorted(
            completed_kicker_results["season"].astype(int).unique(), reverse=True
        )
        kicker_history_columns = st.columns(3)
        with kicker_history_columns[0]:
            kicker_season = st.selectbox(
                "Season", kicker_seasons, key="kicker_history_season"
            )
        kicker_weeks = sorted(
            completed_kicker_results.loc[
                completed_kicker_results["season"].eq(kicker_season), "week"
            ]
            .astype(int)
            .unique(),
            reverse=True,
        )
        with kicker_history_columns[1]:
            kicker_week = st.selectbox(
                "Week", kicker_weeks, key="kicker_history_week"
            )
        with kicker_history_columns[2]:
            kicker_history_profile = st.selectbox(
                "Scoring",
                ["ESPN", "Yahoo"],
                key="kicker_history_scoring",
            )
        previous_kickers = filter_completed_kicker_results(
            completed_kicker_results,
            kicker_season,
            kicker_week,
            kicker_history_profile,
        )
        st.dataframe(
            previous_kickers,
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "position": "POS",
                "team": "Team",
                "opponent": "Opponent",
                "actual_points": st.column_config.NumberColumn(
                    "Actual Points", format="%.2f"
                ),
            },
        )
    else:
        st.caption("Actual D/ST points using the selected platform default.")
        dst_seasons = sorted(
            completed_dst_results["season"].astype(int).unique(), reverse=True
        )
        dst_history_columns = st.columns(3)
        with dst_history_columns[0]:
            dst_season = st.selectbox(
                "Season", dst_seasons, key="dst_history_season"
            )
        dst_weeks = sorted(
            completed_dst_results.loc[
                completed_dst_results["season"].eq(dst_season), "week"
            ]
            .astype(int)
            .unique(),
            reverse=True,
        )
        with dst_history_columns[1]:
            dst_week = st.selectbox(
                "Week", dst_weeks, key="dst_history_week"
            )
        with dst_history_columns[2]:
            dst_history_profile = st.selectbox(
                "Scoring",
                ["ESPN", "Yahoo"],
                key="dst_history_scoring",
            )
        previous_dst = filter_completed_dst_results(
            completed_dst_results,
            dst_season,
            dst_week,
            dst_history_profile,
        )
        st.dataframe(
            previous_dst,
            hide_index=True,
            width="stretch",
            column_config={
                "team": "Defense",
                "opponent": "Opponent",
                "actual_points": st.column_config.NumberColumn(
                    "Actual Points", format="%.2f"
                ),
            },
        )

with season_totals_tab:
    st.subheader("Season totals")
    st.caption(
        "Completed full-PPR player points plus kicker points under the "
        "selected platform default."
    )
    total_seasons = sorted(
        set(completed_results["season"].astype(int))
        | set(completed_kicker_results["season"].astype(int)),
        reverse=True,
    )
    season_total_columns = st.columns(3)
    with season_total_columns[0]:
        totals_season = st.selectbox(
            "Season", total_seasons, key="totals_season"
        )
    with season_total_columns[1]:
        totals_position = st.selectbox(
            "Position",
            ["All", "QB", "RB", "WR", "TE", "FLEX", "K"],
            key="totals_position",
        )
    with season_total_columns[2]:
        totals_kicker_profile = st.selectbox(
            "Kicker scoring",
            ["ESPN", "Yahoo"],
            key="totals_kicker_scoring",
        )
    season_totals = season_totals_frame(
        completed_results,
        completed_kicker_results,
        totals_season,
        totals_position,
        totals_kicker_profile,
    )
    st.dataframe(
        season_totals,
        hide_index=True,
        width="stretch",
        column_config={
            "player_display_name": "Player",
            "position": "POS",
            "team": "Latest Team",
            "total_points": st.column_config.NumberColumn(
                "Season Points", format="%.2f"
            ),
        },
    )
