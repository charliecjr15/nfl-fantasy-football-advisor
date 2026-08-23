"""Public Streamlit interface for the Sunday Edge fantasy advisor."""

from __future__ import annotations

import importlib
import json
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

import app_support as _app_support


# Streamlit can rerun this file while retaining an older imported helper module.
_app_support = importlib.reload(_app_support)
apply_projection_intervals = _app_support.apply_projection_intervals
bye_week_frame = _app_support.bye_week_frame
comparison_frame = _app_support.comparison_frame
dst_projection_frame = _app_support.dst_projection_frame
filter_completed_dst_results = _app_support.filter_completed_dst_results
filter_completed_kicker_results = _app_support.filter_completed_kicker_results
filter_completed_results = _app_support.filter_completed_results
flex_projections = _app_support.flex_projections
kicker_projection_frame = _app_support.kicker_projection_frame
normalize_completed_dst_results = _app_support.normalize_completed_dst_results
normalize_completed_kicker_results = _app_support.normalize_completed_kicker_results
normalize_completed_results = _app_support.normalize_completed_results
normalize_dst_rankings = _app_support.normalize_dst_rankings
normalize_kicker_rankings = _app_support.normalize_kicker_rankings
normalize_rankings = _app_support.normalize_rankings
optimize_lineup = _app_support.optimize_lineup
season_outlook_frame = _app_support.season_outlook_frame
season_totals_frame = _app_support.season_totals_frame
search_projection_pool = _app_support.search_projection_pool
selectable_kickers = _app_support.selectable_kickers
selectable_players = _app_support.selectable_players
team_bye_weeks = _app_support.team_bye_weeks
top_projections = _app_support.top_projections
trade_side_summary = _app_support.trade_side_summary
waiver_shortlist = _app_support.waiver_shortlist


PROJECT_ROOT = Path(__file__).resolve().parent
PUBLIC_DIRECTORY = PROJECT_ROOT / "results" / "public"
RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_rankings.csv"
METADATA_PATH = PUBLIC_DIRECTORY / "latest_run.json"
COMPLETED_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_week_results.csv"
DST_RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_dst_rankings.csv"
COMPLETED_DST_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_dst_results.csv"
KICKER_RANKINGS_PATH = PUBLIC_DIRECTORY / "latest_kicker_rankings.csv"
COMPLETED_KICKER_RESULTS_PATH = PUBLIC_DIRECTORY / "completed_kicker_results.csv"
CALIBRATION_PATH = PUBLIC_DIRECTORY / "projection_calibration.csv"
MODEL_ACCURACY_PATH = PUBLIC_DIRECTORY / "model_accuracy.csv"
SEASON_SCHEDULE_PATH = PUBLIC_DIRECTORY / "season_schedule.csv"
GAME_CONTEXT_PATH = PUBLIC_DIRECTORY / "game_context.csv"
ADVISOR_CONTEXT_PATH = PUBLIC_DIRECTORY / "advisor_context.json"

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


def apply_app_styles(path: Path) -> None:
    """Load the checked-in visual theme without runtime dependencies."""

    if path.exists():
        st.markdown(
            f"<style>{path.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


def published_label(value: object) -> str:
    """Return a compact UTC freshness label for the public snapshot."""

    try:
        timestamp = pd.to_datetime(value, utc=True, errors="raise")
    except (TypeError, ValueError):
        return "Latest validated update"
    return timestamp.strftime("Updated %b %d, %Y at %H:%M UTC")


def render_app_header(
    metadata: dict[str, object], season: int, week: int
) -> None:
    """Render the compact scoreboard-style masthead."""

    freshness = escape(published_label(metadata.get("published_at_utc")))
    st.markdown(
        f"""
        <section class="se-hero">
          <div class="se-hero__brand">
            <span class="se-mark">SE</span>
            <div>
              <div class="se-eyebrow">Fantasy decision desk</div>
              <h1>Sunday Edge</h1>
              <p>Clear calls for your next lineup decision.</p>
            </div>
          </div>
          <div class="se-scoreboard">
            <div><span>Season</span><strong>{season}</strong></div>
            <div><span>Week</span><strong>{week}</strong></div>
            <div><span>Games</span><strong>{int(metadata.get('game_count', 0))}</strong></div>
            <small><i></i>{freshness}</small>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def section_intro(kicker: str, title: str, body: str) -> None:
    """Give each decision area a consistent, restrained heading."""

    st.markdown(
        f"""
        <div class="se-section-head">
          <span>{escape(kicker)}</span>
          <h2>{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_player_board(dataframe: pd.DataFrame, limit: int | None = None) -> None:
    """Render a scan-friendly leaderboard with projection ranges."""

    board = dataframe.head(limit) if limit else dataframe
    if board.empty:
        st.info("No players match these filters.")
        return
    rows: list[str] = []
    for rank, (_, player) in enumerate(board.iterrows(), start=1):
        name = escape(str(player["player_display_name"]))
        position = escape(str(player["position"]))
        team = escape(str(player["team"]))
        opponent = escape(str(player["opponent"]))
        projection = float(player["display_projected_fantasy_points_ppr"])
        range_text = ""
        if {
            "projection_floor_ppr",
            "projection_ceiling_ppr",
        }.issubset(board.columns):
            floor = float(player["projection_floor_ppr"])
            ceiling = float(player["projection_ceiling_ppr"])
            range_text = f"<small>range {floor:.1f}-{ceiling:.1f}</small>"
        rows.append(
            f'<div class="se-player-row">'
            f'<div class="se-rank">{rank}</div>'
            f'<div class="se-player-name"><strong>{name}</strong><span>{team} vs {opponent}</span></div>'
            f'<span class="se-position se-position--{position.lower()}">{position}</span>'
            f'<div class="se-projection"><strong>{projection:.2f}</strong><span>PPR</span>{range_text}</div>'
            "</div>"
        )
    st.markdown(
        '<div class="se-player-board">' + "".join(rows) + "</div>",
        unsafe_allow_html=True,
    )


def dst_table(dataframe: pd.DataFrame, points_label: str) -> None:
    """Display a compact D/ST projection table."""

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


def kicker_table(dataframe: pd.DataFrame) -> None:
    """Display compact kicker projections."""

    st.dataframe(
        dataframe[
            [
                "player_display_name",
                "position",
                "team",
                "opponent",
                "projected_points",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "player_display_name": "Player",
            "position": "POS",
            "team": "Team",
            "opponent": "Opponent",
            "projected_points": st.column_config.NumberColumn(
                "Projected Points", format="%.2f"
            ),
        },
    )


def render_summary_card(label: str, value: str, detail: str) -> None:
    """Render one decision summary without a bulky metric widget."""

    st.markdown(
        f"""
        <div class="se-summary-card">
          <span>{escape(label)}</span>
          <strong>{escape(value)}</strong>
          <small>{escape(detail)}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_game_cards(games: pd.DataFrame) -> None:
    """Render the weekly schedule as matchup cards."""

    cards: list[str] = []
    for _, game in games.iterrows():
        risk = str(game["weather_risk"])
        if risk == "INDOORS":
            risk_class = "indoors"
        elif risk == "LOW_WEATHER_RISK":
            risk_class = "low"
        elif any(flag in risk for flag in ["HIGH_WIND", "STRONG_GUSTS"]):
            risk_class = "high"
        elif any(flag in risk for flag in ["PRECIPITATION", "FREEZING", "EXTREME_HEAT"]):
            risk_class = "moderate"
        else:
            risk_class = "pending"
        line_parts: list[str] = []
        if pd.notna(game.get("total_line")):
            line_parts.append(f"O/U {float(game['total_line']):.1f}")
        if pd.notna(game.get("spread_line")):
            line_parts.append(f"Spread {float(game['spread_line']):+.1f}")
        weather = escape(str(game["forecast_note"]))
        if str(game["forecast_status"]) in {
            "FORECAST_AVAILABLE",
            "RECORDED_GAME_WEATHER",
        }:
            weather_values: list[str] = []
            if pd.notna(game.get("temperature_f")):
                weather_values.append(f"{float(game['temperature_f']):.0f} F")
            if pd.notna(game.get("wind_mph")):
                weather_values.append(f"wind {float(game['wind_mph']):.0f} mph")
            if weather_values:
                weather = " - ".join(weather_values)
        cards.append(
            f'<article class="se-game-card">'
            f'<div class="se-game-card__time">{escape(str(game["kickoff_et"]))}</div>'
            f'<div class="se-matchup"><b>{escape(str(game["away_team"]))}</b><span>@</span><b>{escape(str(game["home_team"]))}</b></div>'
            f'<div class="se-venue">{escape(str(game["venue_label"]))} - {escape(str(game["roof"]).title())}</div>'
            f'<div class="se-game-lines">{" - ".join(line_parts) if line_parts else "Lines pending"}</div>'
            f'<div class="se-weather se-weather--{risk_class}"><i></i>{escape(risk.replace("_", " ").title())}</div>'
            f"<p>{weather}</p>"
            "</article>"
        )
    st.markdown(
        '<div class="se-game-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_csv(path: str) -> pd.DataFrame:
    """Load a checked-in public CSV."""

    return pd.read_csv(path, low_memory=False)


@st.cache_data(show_spinner=False)
def load_json(path: str) -> dict[str, object]:
    """Load a checked-in public JSON document."""

    with Path(path).open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


apply_app_styles(PROJECT_ROOT / "assets" / "app.css")

required_public_files = [
    RANKINGS_PATH,
    METADATA_PATH,
    COMPLETED_RESULTS_PATH,
    DST_RANKINGS_PATH,
    COMPLETED_DST_RESULTS_PATH,
    KICKER_RANKINGS_PATH,
    COMPLETED_KICKER_RESULTS_PATH,
    CALIBRATION_PATH,
    MODEL_ACCURACY_PATH,
    SEASON_SCHEDULE_PATH,
    GAME_CONTEXT_PATH,
    ADVISOR_CONTEXT_PATH,
]
if not all(path.exists() for path in required_public_files):
    st.error("No validated weekly projections are available yet.")
    st.stop()

try:
    metadata = load_json(str(METADATA_PATH))
    advisor_context = load_json(str(ADVISOR_CONTEXT_PATH))
    rankings = normalize_rankings(load_csv(str(RANKINGS_PATH)))
    calibration = load_csv(str(CALIBRATION_PATH))
    rankings = apply_projection_intervals(rankings, calibration)
    completed_results = normalize_completed_results(load_csv(str(COMPLETED_RESULTS_PATH)))
    dst_rankings = normalize_dst_rankings(load_csv(str(DST_RANKINGS_PATH)))
    completed_dst_results = normalize_completed_dst_results(load_csv(str(COMPLETED_DST_RESULTS_PATH)))
    kicker_rankings = normalize_kicker_rankings(load_csv(str(KICKER_RANKINGS_PATH)))
    completed_kicker_results = normalize_completed_kicker_results(load_csv(str(COMPLETED_KICKER_RESULTS_PATH)))
    model_accuracy = load_csv(str(MODEL_ACCURACY_PATH))
    season_schedule = load_csv(str(SEASON_SCHEDULE_PATH))
    game_context = load_csv(str(GAME_CONTEXT_PATH))
except (OSError, ValueError, json.JSONDecodeError) as error:
    st.error(f"The weekly data could not be loaded: {error}")
    st.stop()

season = int(metadata["season"])
week = int(metadata["week"])
if (
    int(advisor_context.get("season", -1)) != season
    or int(advisor_context.get("week", -1)) != week
    or not str(advisor_context.get("context_status", "")).startswith("PASS")
):
    st.error("The decision context does not match the published projection week.")
    st.stop()

render_app_header(metadata, season, week)

profile_param = str(st.query_params.get("platform", "ESPN")).upper()
if profile_param not in {"ESPN", "YAHOO"}:
    profile_param = "ESPN"
profile_column, note_column = st.columns([1, 2.6], vertical_alignment="bottom")
with profile_column:
    scoring_profile = st.radio(
        "League scoring",
        ["ESPN", "Yahoo"],
        index=0 if profile_param == "ESPN" else 1,
        horizontal=True,
        key="global_scoring_profile",
        help="Applies to kicker and D/ST projections and results. Offense uses full PPR.",
    )
with note_column:
    st.markdown(
        '<div class="se-profile-note"><b>Full PPR offense</b><span>Platform profile applies to K and D/ST everywhere.</span></div>',
        unsafe_allow_html=True,
    )

player_map = selectable_players(rankings)
id_to_player_label = {player_id: label for label, player_id in player_map.items()}
saved_roster_ids = [
    player_id
    for player_id in str(st.query_params.get("roster", "")).split(",")
    if player_id in id_to_player_label
]
if "roster_players" not in st.session_state:
    st.session_state["roster_players"] = [id_to_player_label[player_id] for player_id in saved_roster_ids]

status = str(metadata.get("publication_status", "UNKNOWN"))
if not status.startswith("PASS"):
    st.error("This weekly update is not ready for lineup decisions.")

rankings_tab, team_tab, compare_tab, games_tab, season_tab = st.tabs(
    ["Rankings", "My Team", "Compare", "Game Center", "Season"]
)

with rankings_tab:
    section_intro(
        "Week board",
        "Find the best play",
        "Start with the projected leaders, then narrow the board only when you need to.",
    )
    ranking_view = st.radio(
        "Ranking view",
        ["Offense", "FLEX", "Kickers", "D/ST", "Waivers"],
        horizontal=True,
        label_visibility="collapsed",
        key="ranking_view",
    )
    if ranking_view == "Offense":
        filter_column, count_column, search_column = st.columns([1, 1, 2])
        with filter_column:
            selected_position = st.selectbox("Position", ["All", "QB", "RB", "WR", "TE"])
        with count_column:
            player_limit = st.selectbox("Show", [10, 20, 40], index=0)
        with search_column:
            projection_search = st.text_input(
                "Search",
                placeholder="Player, team, position, or opponent",
                key="projection_search",
            )
        projection_pool = search_projection_pool(rankings, projection_search)
        leaders = top_projections(projection_pool, selected_position, player_limit)
        render_player_board(leaders)
        st.caption(
            "The range is an 80% historical residual interval, not a guarantee. "
            "The point projection remains the ranking value."
        )
    elif ranking_view == "FLEX":
        flex_count = st.selectbox("Show", [10, 20, 40], index=1, key="flex_count")
        render_player_board(flex_projections(rankings, flex_count))
        st.caption("FLEX includes RB, WR, and TE players.")
    elif ranking_view == "Kickers":
        st.caption(f"{scoring_profile} default scoring. Confirm the final depth chart before kickoff.")
        kicker_table(kicker_projection_frame(kicker_rankings, scoring_profile))
    elif ranking_view == "D/ST":
        st.caption(f"{scoring_profile} default scoring. Custom league settings can change these totals.")
        dst_table(dst_projection_frame(dst_rankings, scoring_profile), "Projected Points")
    else:
        roster_labels = st.session_state.get("roster_players", [])
        roster_ids = [player_map[label] for label in roster_labels if label in player_map]
        waiver_position = st.selectbox(
            "Position", ["All", "QB", "RB", "WR", "TE", "FLEX"], key="waiver_position"
        )
        waivers = waiver_shortlist(rankings, roster_ids, position=waiver_position, limit=20)
        st.caption(
            "Suggested player pool only. Sunday Edge cannot see your league's ownership, "
            "so confirm availability in ESPN or Yahoo."
        )
        waiver_columns = [
            "player_display_name",
            "position",
            "team",
            "opponent",
            "display_projected_fantasy_points_ppr",
        ]
        if roster_ids:
            waiver_columns.append("upgrade_vs_roster")
        st.dataframe(
            waivers[waiver_columns],
            hide_index=True,
            width="stretch",
            column_config={
                **PLAYER_COLUMN_CONFIG,
                "upgrade_vs_roster": st.column_config.NumberColumn("vs weakest roster player", format="%+.2f"),
            },
        )

with team_tab:
    section_intro(
        "Roster room",
        "Set your best legal lineup",
        "Save your roster once, flag unavailable players, and let the optimizer fill every slot.",
    )
    selected_labels = st.multiselect(
        "Roster players",
        list(player_map),
        placeholder="Search and select your QB, RB, WR, and TE players",
        key="roster_players",
    )
    available_unavailable_labels = [label for label in selected_labels if label in player_map]
    if "unavailable_players" in st.session_state:
        st.session_state["unavailable_players"] = [
            label for label in st.session_state["unavailable_players"] if label in available_unavailable_labels
        ]
    unavailable_labels = st.multiselect(
        "Out / doubtful / unavailable",
        available_unavailable_labels,
        placeholder="Optional manual availability check",
        key="unavailable_players",
        help="The 2026 injury feed is not published yet, so this manual flag keeps the optimizer honest.",
    )
    roster_ids = [player_map[label] for label in selected_labels]
    unavailable_ids = [player_map[label] for label in unavailable_labels]

    lineup, gaps = optimize_lineup(rankings, roster_ids, unavailable_ids)
    starter_rows = lineup.loc[lineup["lineup_status"].eq("START")]
    offense_total = float(starter_rows["display_projected_fantasy_points_ppr"].sum())
    if not selected_labels:
        st.info("Add your roster to build a lineup, bye plan, and waiver shortlist.")
    else:
        if gaps:
            st.warning("Roster gaps: " + "; ".join(gaps))
        st.dataframe(
            lineup[
                [
                    "recommended_slot",
                    "lineup_status",
                    *PLAYER_COLUMNS,
                    "projection_floor_ppr",
                    "projection_ceiling_ppr",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "recommended_slot": "Slot",
                "lineup_status": "Decision",
                **PLAYER_COLUMN_CONFIG,
                "projection_floor_ppr": st.column_config.NumberColumn("Floor", format="%.2f"),
                "projection_ceiling_ppr": st.column_config.NumberColumn("Ceiling", format="%.2f"),
            },
        )

    specialist_columns = st.columns(2)
    kicker_map = selectable_kickers(kicker_rankings)
    saved_kicker = str(st.query_params.get("kicker", ""))
    kicker_options = ["None", *kicker_map]
    saved_kicker_label = next(
        (label for label, player_id in kicker_map.items() if str(player_id) == saved_kicker), "None"
    )
    with specialist_columns[0]:
        selected_kicker = st.selectbox(
            "Kicker", kicker_options, index=kicker_options.index(saved_kicker_label), key="lineup_kicker"
        )
    defense_map = dict(zip(dst_rankings["defense_label"], dst_rankings["team"]))
    saved_defense = str(st.query_params.get("dst", ""))
    defense_options = ["None", *defense_map]
    saved_defense_label = next(
        (label for label, team in defense_map.items() if str(team) == saved_defense), "None"
    )
    with specialist_columns[1]:
        selected_defense = st.selectbox(
            "D/ST", defense_options, index=defense_options.index(saved_defense_label), key="lineup_defense"
        )

    selected_kicker_points = 0.0
    if selected_kicker != "None":
        kicker_rows = kicker_projection_frame(kicker_rankings, scoring_profile)
        kicker_rows = kicker_rows.loc[
            kicker_rows["player_id"].astype(str).eq(str(kicker_map[selected_kicker]))
        ]
        if not kicker_rows.empty:
            selected_kicker_points = float(kicker_rows["projected_points"].iloc[0])
    selected_defense_points = 0.0
    if selected_defense != "None":
        defense_rows = dst_projection_frame(dst_rankings, scoring_profile)
        defense_rows = defense_rows.loc[defense_rows["team"].eq(defense_map[selected_defense])]
        if not defense_rows.empty:
            selected_defense_points = float(defense_rows["projected_points"].iloc[0])
    lineup_total = offense_total + selected_kicker_points + selected_defense_points

    summary_columns = st.columns(3)
    with summary_columns[0]:
        render_summary_card("Projected lineup", f"{lineup_total:.2f}", "total points")
    with summary_columns[1]:
        render_summary_card("Offense", f"{offense_total:.2f}", f"{len(starter_rows)} starters")
    with summary_columns[2]:
        render_summary_card(
            "Special teams", f"{selected_kicker_points + selected_defense_points:.2f}", f"{scoring_profile} profile"
        )

    action_columns = st.columns([1, 1, 2])
    with action_columns[0]:
        if st.button("Save roster link", type="primary", use_container_width=True):
            st.query_params["roster"] = ",".join(roster_ids)
            st.query_params["platform"] = scoring_profile.upper()
            if selected_kicker != "None":
                st.query_params["kicker"] = str(kicker_map[selected_kicker])
            elif "kicker" in st.query_params:
                del st.query_params["kicker"]
            if selected_defense != "None":
                st.query_params["dst"] = str(defense_map[selected_defense])
            elif "dst" in st.query_params:
                del st.query_params["dst"]
            st.toast("Roster saved in this page link. Bookmark or share it.")
    roster_export = rankings.loc[
        rankings["player_id"].astype(str).isin(set(roster_ids)),
        ["player_display_name", "position", "team", "opponent", "display_projected_fantasy_points_ppr"],
    ]
    with action_columns[1]:
        st.download_button(
            "Download roster",
            roster_export.to_csv(index=False).encode("utf-8"),
            file_name=f"sunday_edge_{season}_week_{week}_roster.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with action_columns[2]:
        st.caption("Saved links store player IDs in the URL. No account or private league data is uploaded.")

    st.markdown("#### Bye-week planner")
    roster_byes = bye_week_frame(rankings, season_schedule, roster_ids, week)
    if roster_byes.empty:
        st.caption("Add roster players to see bye-week conflicts.")
    else:
        st.dataframe(
            roster_byes,
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "position": "POS",
                "team": "Team",
                "bye_week": "Bye",
                "bye_status": "Status",
            },
        )
    st.markdown(
        '<div class="se-caveat"><b>Injury status:</b> The 2026 weekly injury source is not available yet. Use the manual unavailable list above and confirm official game status in ESPN or Yahoo before kickoff.</div>',
        unsafe_allow_html=True,
    )

with compare_tab:
    section_intro(
        "Decision lab",
        "Compare the choices that matter",
        "Use the weekly model for start/sit calls or the current-rate outlook for trade planning.",
    )
    compare_mode = st.radio(
        "Comparison type", ["Start / Sit", "Trade"], horizontal=True, label_visibility="collapsed", key="compare_mode"
    )
    if compare_mode == "Start / Sit":
        comparison_labels = st.multiselect(
            "Players to compare",
            list(player_map),
            max_selections=4,
            placeholder="Select up to four players",
            key="comparison_players",
        )
        comparison = comparison_frame(rankings, [player_map[label] for label in comparison_labels])
        if comparison.empty:
            st.info("Select at least one player to compare.")
        else:
            render_player_board(comparison)
            if len(comparison) >= 2:
                leader = comparison.iloc[0]
                runner_up = comparison.iloc[1]
                edge = float(
                    leader["display_projected_fantasy_points_ppr"]
                    - runner_up["display_projected_fantasy_points_ppr"]
                )
                overlaps = float(leader["projection_floor_ppr"]) <= float(runner_up["projection_ceiling_ppr"])
                confidence = "Close call - ranges overlap" if overlaps else "Clear projected edge"
                render_summary_card(
                    "Recommended start",
                    str(leader["player_display_name"]),
                    f"+{edge:.2f} PPR - {confidence}",
                )
    else:
        full_outlook = season_outlook_frame(rankings, season_schedule, week, limit=1000)
        trade_columns = st.columns(2)
        with trade_columns[0]:
            side_a_labels = st.multiselect(
                "Side A", list(player_map), max_selections=5, placeholder="Players received by Side A", key="trade_side_a"
            )
        with trade_columns[1]:
            side_b_labels = st.multiselect(
                "Side B", list(player_map), max_selections=5, placeholder="Players received by Side B", key="trade_side_b"
            )
        side_a_ids = [player_map[label] for label in side_a_labels]
        side_b_ids = [player_map[label] for label in side_b_labels]
        if set(side_a_ids) & set(side_b_ids):
            st.warning("A player cannot appear on both sides of a trade.")
        summary_a = trade_side_summary(full_outlook, side_a_ids)
        summary_b = trade_side_summary(full_outlook, side_b_ids)
        summary_columns = st.columns(2)
        with summary_columns[0]:
            render_summary_card(
                "Side A value", f"{summary_a['ros_points_proxy']:.1f}", f"ROS proxy - {summary_a['weekly_projection']:.1f} weekly"
            )
        with summary_columns[1]:
            render_summary_card(
                "Side B value", f"{summary_b['ros_points_proxy']:.1f}", f"ROS proxy - {summary_b['weekly_projection']:.1f} weekly"
            )
        if side_a_ids and side_b_ids and not (set(side_a_ids) & set(side_b_ids)):
            difference = float(summary_a["ros_points_proxy"]) - float(summary_b["ros_points_proxy"])
            favored = "Side A" if difference > 0 else "Side B" if difference < 0 else "Neither side"
            st.success(f"{favored} leads the current-rate ROS proxy by {abs(difference):.1f} points.")
        st.caption(
            "Trade value is a planning proxy: this week's projection multiplied by scheduled games remaining. "
            "It does not predict future injuries, depth-chart changes, or weekly matchup shifts."
        )

with games_tab:
    section_intro(
        "Game center",
        f"Every matchup in Week {week}",
        "Kickoff, venue, betting context, and weather risk in one weekly board.",
    )
    status_cards = st.columns(4)
    with status_cards[0]:
        render_summary_card("Projections", "Ready", f"{len(rankings)} player rows")
    weather_ready = int(
        game_context["forecast_status"]
        .isin(["FORECAST_AVAILABLE", "RECORDED_GAME_WEATHER"])
        .sum()
    )
    weather_pending = int(game_context["forecast_status"].eq("FORECAST_NOT_AVAILABLE_YET").sum())
    with status_cards[1]:
        render_summary_card("Weather", f"{weather_ready} ready", f"{weather_pending} waiting on forecast window")
    with status_cards[2]:
        render_summary_card("Injuries", "Manual", "2026 source not published")
    with status_cards[3]:
        render_summary_card("Live scoring", "Not connected", "provider credentials required")
    render_game_cards(game_context)
    st.markdown(
        """
        <div class="se-live-note">
          <b>About live tracking</b>
          <span>True in-game scoring needs a licensed live-stat feed. Yahoo roster sync also needs each user's OAuth approval; ESPN does not provide a supported public fantasy-league API. The app keeps these states explicit instead of showing delayed data as live.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

with season_tab:
    section_intro(
        "Season room",
        "Results, outlook, and model scorecard",
        "Review what happened, plan the schedule ahead, and see how the projection model performed.",
    )
    season_view = st.radio(
        "Season view",
        ["Results", "Totals", "ROS Outlook", "Bye Weeks", "Model Accuracy"],
        horizontal=True,
        label_visibility="collapsed",
        key="season_view",
    )
    if season_view == "Results":
        result_type = st.radio("Result type", ["Players", "Kickers", "D/ST"], horizontal=True)
        if result_type == "Players":
            prior_seasons = sorted(completed_results["season"].astype(int).unique(), reverse=True)
            filters = st.columns(3)
            with filters[0]:
                prior_season = st.selectbox("Season", prior_seasons, key="history_season")
            available_weeks = sorted(
                completed_results.loc[completed_results["season"].eq(prior_season), "week"].astype(int).unique(),
                reverse=True,
            )
            with filters[1]:
                prior_week = st.selectbox("Week", available_weeks, key="history_week")
            with filters[2]:
                prior_position = st.selectbox(
                    "Position", ["All", "QB", "RB", "WR", "TE"], key="history_position"
                )
            previous = filter_completed_results(completed_results, prior_season, prior_week, prior_position)
            st.dataframe(
                previous[["player_display_name", "position", "team", "opponent", "fantasy_points_ppr"]],
                hide_index=True,
                width="stretch",
                column_config={
                    "player_display_name": "Player",
                    "position": "POS",
                    "team": "Team",
                    "opponent": "Opponent",
                    "fantasy_points_ppr": st.column_config.NumberColumn("Actual PPR", format="%.2f"),
                },
            )
        elif result_type == "Kickers":
            kicker_seasons = sorted(completed_kicker_results["season"].astype(int).unique(), reverse=True)
            filters = st.columns(2)
            with filters[0]:
                kicker_season = st.selectbox("Season", kicker_seasons, key="k_history_season")
            kicker_weeks = sorted(
                completed_kicker_results.loc[completed_kicker_results["season"].eq(kicker_season), "week"].astype(int).unique(),
                reverse=True,
            )
            with filters[1]:
                kicker_week = st.selectbox("Week", kicker_weeks, key="k_history_week")
            previous_kickers = filter_completed_kicker_results(
                completed_kicker_results, kicker_season, kicker_week, scoring_profile
            )
            st.dataframe(previous_kickers, hide_index=True, width="stretch")
        else:
            dst_seasons = sorted(completed_dst_results["season"].astype(int).unique(), reverse=True)
            filters = st.columns(2)
            with filters[0]:
                dst_season = st.selectbox("Season", dst_seasons, key="dst_history_season")
            dst_weeks = sorted(
                completed_dst_results.loc[completed_dst_results["season"].eq(dst_season), "week"].astype(int).unique(),
                reverse=True,
            )
            with filters[1]:
                dst_week = st.selectbox("Week", dst_weeks, key="dst_history_week")
            previous_dst = filter_completed_dst_results(
                completed_dst_results, dst_season, dst_week, scoring_profile
            )
            st.dataframe(previous_dst, hide_index=True, width="stretch")
    elif season_view == "Totals":
        total_seasons = sorted(
            set(completed_results["season"].astype(int))
            | set(completed_kicker_results["season"].astype(int))
            | set(completed_dst_results["season"].astype(int)),
            reverse=True,
        )
        filters = st.columns(2)
        with filters[0]:
            totals_season = st.selectbox("Season", total_seasons, key="totals_season")
        with filters[1]:
            totals_position = st.selectbox(
                "Position", ["All", "QB", "RB", "WR", "TE", "FLEX", "K", "D/ST"], key="totals_position"
            )
        totals = season_totals_frame(
            completed_results,
            completed_kicker_results,
            totals_season,
            totals_position,
            scoring_profile,
            completed_dst_results,
            scoring_profile,
        )
        st.dataframe(
            totals,
            hide_index=True,
            width="stretch",
            column_config={
                "player_display_name": "Player",
                "position": "POS",
                "team": "Latest Team",
                "total_points": st.column_config.NumberColumn("Season Points", format="%.2f"),
            },
        )
    elif season_view == "ROS Outlook":
        outlook_position = st.selectbox(
            "Position", ["All", "QB", "RB", "WR", "TE", "FLEX"], key="outlook_position"
        )
        outlook = season_outlook_frame(rankings, season_schedule, week, outlook_position, 100)
        st.dataframe(
            outlook[
                [
                    "player_display_name",
                    "position",
                    "team",
                    "bye_week",
                    "games_remaining",
                    "display_projected_fantasy_points_ppr",
                    "ros_points_proxy",
                ]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                **PLAYER_COLUMN_CONFIG,
                "bye_week": "Bye",
                "games_remaining": "Games Left",
                "ros_points_proxy": st.column_config.NumberColumn("ROS Proxy", format="%.2f"),
            },
        )
        st.caption(
            "ROS Proxy equals this week's projection times scheduled games remaining. "
            "It is a transparent planning baseline, not a weekly reforecast."
        )
    elif season_view == "Bye Weeks":
        byes = team_bye_weeks(season_schedule)
        st.dataframe(
            byes, hide_index=True, width="stretch", column_config={"team": "Team", "bye_week": "Bye Week"}
        )
    else:
        st.caption(
            "Held-out 2025 results. Lower MAE and RMSE are better; higher rank correlation and interval coverage are better."
        )
        accuracy_display = model_accuracy.rename(
            columns={
                "position": "Position",
                "row_count": "Players",
                "mae": "MAE",
                "rmse": "RMSE",
                "spearman": "Rank correlation",
                "test_coverage_pct": "80% range coverage",
            }
        )[["Position", "Players", "MAE", "RMSE", "Rank correlation", "80% range coverage"]]
        st.dataframe(accuracy_display, hide_index=True, width="stretch")
        overall = model_accuracy.loc[model_accuracy["position"].eq("ALL")].iloc[0]
        accuracy_cards = st.columns(3)
        with accuracy_cards[0]:
            render_summary_card("Overall MAE", f"{float(overall['mae']):.2f}", "fantasy points")
        with accuracy_cards[1]:
            render_summary_card("Rank correlation", f"{float(overall['spearman']):.2f}", "held-out 2025")
        with accuracy_cards[2]:
            render_summary_card("Range coverage", f"{float(overall['test_coverage_pct']):.1f}%", "target interval: 80%")

st.markdown(
    """
    <footer class="se-footer">
      <b>Sunday Edge</b>
      <span>Full-PPR offense - ESPN & Yahoo specialist profiles - Decisions, not noise.</span>
    </footer>
    """,
    unsafe_allow_html=True,
)
