"""Build compact, source-backed context artifacts for the public advisor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIRECTORY = PROJECT_ROOT / "results" / "public"
METADATA_PATH = PUBLIC_DIRECTORY / "latest_run.json"
VALIDATION_PREDICTIONS_PATH = (
    PROJECT_ROOT / "results" / "tables" / "model_validation_predictions.csv"
)
TEST_PREDICTIONS_PATH = (
    PROJECT_ROOT / "results" / "tables" / "final_test_predictions.csv"
)
TEST_METRICS_PATH = (
    PROJECT_ROOT / "results" / "tables" / "final_test_metrics.csv"
)
VENUE_LOCATIONS_PATH = PROJECT_ROOT / "config" / "stadium_locations.csv"
CALIBRATION_PATH = PUBLIC_DIRECTORY / "projection_calibration.csv"
ACCURACY_PATH = PUBLIC_DIRECTORY / "model_accuracy.csv"
SCHEDULE_PATH = PUBLIC_DIRECTORY / "season_schedule.csv"
GAME_CONTEXT_PATH = PUBLIC_DIRECTORY / "game_context.csv"
CONTEXT_MANIFEST_PATH = PUBLIC_DIRECTORY / "advisor_context.json"

POSITIONS = ["QB", "RB", "WR", "TE"]
INDOOR_ROOFS = {"dome", "closed"}
OPEN_AIR_ROOFS = {"outdoors", "open"}
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_SOURCE_URL = "https://open-meteo.com/en/docs"
SCHEDULE_SOURCE_URL = (
    "https://github.com/nflverse/nfldata/blob/master/data/games.csv"
)
VENUE_SOURCE_URL = (
    "https://github.com/nflverse/nflverse-data/issues/57"
)


def parse_arguments() -> argparse.Namespace:
    """Parse optional overrides used by local verification and automation."""

    parser = argparse.ArgumentParser(
        description="Build projection calibration, schedule, and game context."
    )
    parser.add_argument("--season", type=int)
    parser.add_argument("--week", type=int)
    parser.add_argument(
        "--as-of",
        help="UTC-aware ISO-8601 build time; defaults to the current time.",
    )
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Build game context without calling the forecast API.",
    )
    parser.add_argument("--calibration-output")
    parser.add_argument("--accuracy-output")
    parser.add_argument("--schedule-output")
    parser.add_argument("--game-context-output")
    parser.add_argument("--manifest-output")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of one file."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for block in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write_csv(dataframe: pd.DataFrame, path: Path) -> None:
    """Write a CSV through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="",
        suffix=".csv",
        prefix=f".{path.stem}_",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        dataframe.to_csv(temporary, index=False, lineterminator="\n")
    os.replace(temporary_path, path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    """Write deterministic JSON through a same-directory temporary file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        suffix=".json",
        prefix=f".{path.stem}_",
        dir=path.parent,
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(payload, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
    os.replace(temporary_path, path)


def parse_as_of(value: str | None) -> datetime:
    """Return an explicitly timezone-aware UTC timestamp."""

    if value is None:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("--as-of must include a timezone offset.")
    return parsed.astimezone(timezone.utc)


def build_projection_calibration(
    validation_predictions: pd.DataFrame,
    test_predictions: pd.DataFrame,
    lower_quantile: float = 0.10,
    upper_quantile: float = 0.90,
) -> pd.DataFrame:
    """Calibrate residual ranges on 2024 and evaluate coverage on 2025."""

    required = {
        "position",
        "target_fantasy_points_ppr",
        "prediction_position_champion",
    }
    for name, dataframe in [
        ("validation", validation_predictions),
        ("test", test_predictions),
    ]:
        missing = sorted(required - set(dataframe.columns))
        if missing:
            raise ValueError(
                f"{name} predictions are missing columns: "
                + ", ".join(missing)
            )
    if not 0 < lower_quantile < upper_quantile < 1:
        raise ValueError("Calibration quantiles must satisfy 0 < lower < upper < 1.")

    rows: list[dict[str, Any]] = []
    for position in POSITIONS:
        calibration = validation_predictions.loc[
            validation_predictions["position"].eq(position)
        ].copy()
        tested = test_predictions.loc[
            test_predictions["position"].eq(position)
        ].copy()
        if calibration.empty or tested.empty:
            raise ValueError(f"Missing calibration or test rows for {position}.")
        residual = (
            calibration["target_fantasy_points_ppr"]
            - calibration["prediction_position_champion"]
        )
        lower = float(residual.quantile(lower_quantile))
        upper = float(residual.quantile(upper_quantile))
        test_lower = tested["prediction_position_champion"] + lower
        test_upper = tested["prediction_position_champion"] + upper
        covered = tested["target_fantasy_points_ppr"].between(
            test_lower, test_upper, inclusive="both"
        )
        rows.append(
            {
                "position": position,
                "interval_level": round(upper_quantile - lower_quantile, 2),
                "lower_residual": round(lower, 4),
                "upper_residual": round(upper, 4),
                "calibration_rows": len(calibration),
                "test_rows": len(tested),
                "test_coverage_pct": round(float(covered.mean() * 100), 2),
                "mean_interval_width": round(upper - lower, 4),
                "calibration_season": int(calibration["season"].min()),
                "evaluation_season": int(tested["season"].min()),
            }
        )
    return pd.DataFrame(rows)


def build_accuracy_metrics(
    test_metrics: pd.DataFrame, calibration: pd.DataFrame
) -> pd.DataFrame:
    """Return one compact frozen-test accuracy row per position and overall."""

    selected = test_metrics.loc[
        test_metrics["model_name"].eq("position_champion")
    ].copy()
    if set(selected["position"]) != {"ALL", *POSITIONS}:
        raise ValueError("Frozen test metrics do not cover ALL, QB, RB, WR, and TE.")
    selected = selected[
        [
            "position",
            "row_count",
            "mae",
            "rmse",
            "spearman_rank_correlation",
            "mean_weekly_spearman",
            "mean_top_n_overlap_pct",
        ]
    ].rename(
        columns={
            "spearman_rank_correlation": "spearman",
            "mean_weekly_spearman": "weekly_spearman",
            "mean_top_n_overlap_pct": "top_n_overlap_pct",
        }
    )
    selected = selected.merge(
        calibration[["position", "test_coverage_pct"]],
        on="position",
        how="left",
        validate="one_to_one",
    )
    coverage_by_rows = float(
        (
            calibration["test_coverage_pct"]
            * calibration["test_rows"]
        ).sum()
        / calibration["test_rows"].sum()
    )
    selected.loc[
        selected["position"].eq("ALL"), "test_coverage_pct"
    ] = round(coverage_by_rows, 2)
    order = {"ALL": 0, "QB": 1, "RB": 2, "WR": 3, "TE": 4}
    selected["_order"] = selected["position"].map(order)
    numeric = [
        "mae",
        "rmse",
        "spearman",
        "weekly_spearman",
        "top_n_overlap_pct",
        "test_coverage_pct",
    ]
    selected[numeric] = selected[numeric].round(4)
    return selected.sort_values("_order").drop(columns="_order").reset_index(
        drop=True
    )


def validate_regular_season_schedule(
    schedule: pd.DataFrame, season: int
) -> pd.DataFrame:
    """Validate the full regular-season schedule before public use."""

    required = {
        "game_id",
        "season",
        "game_type",
        "week",
        "gameday",
        "weekday",
        "gametime",
        "away_team",
        "home_team",
        "roof",
        "surface",
        "stadium_id",
        "stadium",
    }
    missing = sorted(required - set(schedule.columns))
    if missing:
        raise ValueError("Schedule is missing columns: " + ", ".join(missing))
    regular = schedule.loc[
        schedule["season"].eq(season) & schedule["game_type"].eq("REG")
    ].copy()
    if len(regular) != 272:
        raise ValueError(f"Expected 272 regular-season games, observed {len(regular)}.")
    if regular["game_id"].duplicated().any():
        raise ValueError("Regular-season game_id values are not unique.")
    if set(pd.to_numeric(regular["week"], errors="raise").astype(int)) != set(
        range(1, 19)
    ):
        raise ValueError("Regular-season schedule must cover Weeks 1-18.")
    if regular["away_team"].eq(regular["home_team"]).any():
        raise ValueError("A scheduled team cannot play itself.")
    teams = set(regular["away_team"]) | set(regular["home_team"])
    if len(teams) != 32:
        raise ValueError(f"Expected 32 scheduled teams, observed {len(teams)}.")
    appearances = pd.concat(
        [
            regular[["week", "away_team"]].rename(
                columns={"away_team": "team"}
            ),
            regular[["week", "home_team"]].rename(
                columns={"home_team": "team"}
            ),
        ],
        ignore_index=True,
    )
    games_per_team = appearances.groupby("team").size()
    if not games_per_team.eq(17).all():
        raise ValueError("Every team must have exactly 17 regular-season games.")
    if appearances[["week", "team"]].duplicated().any():
        raise ValueError("A team cannot have two games in the same week.")
    regular["week"] = pd.to_numeric(regular["week"], errors="raise").astype(int)
    regular["gameday"] = pd.to_datetime(
        regular["gameday"], errors="raise"
    ).dt.strftime("%Y-%m-%d")
    return regular.sort_values(["week", "gameday", "gametime", "game_id"])


def load_venue_locations(path: Path) -> pd.DataFrame:
    """Load and validate the checked-in stadium location mapping."""

    locations = pd.read_csv(path)
    required = {
        "match_type",
        "match_value",
        "venue_label",
        "latitude",
        "longitude",
        "timezone",
        "location_source",
    }
    missing = sorted(required - set(locations.columns))
    if missing:
        raise ValueError("Venue mapping is missing columns: " + ", ".join(missing))
    if locations[["match_type", "match_value"]].duplicated().any():
        raise ValueError("Venue mapping keys are not unique.")
    return locations


def attach_venue_locations(
    schedule: pd.DataFrame, locations: pd.DataFrame
) -> pd.DataFrame:
    """Prefer exact international venue matches, then stable stadium IDs."""

    name_map = locations.loc[locations["match_type"].eq("stadium_name")].set_index(
        "match_value"
    )
    id_map = locations.loc[locations["match_type"].eq("stadium_id")].set_index(
        "match_value"
    )
    rows: list[dict[str, Any]] = []
    for record in schedule.to_dict("records"):
        stadium = str(record["stadium"])
        stadium_id = str(record["stadium_id"])
        if stadium in name_map.index:
            location = name_map.loc[stadium]
        elif stadium_id in id_map.index:
            location = id_map.loc[stadium_id]
        else:
            raise ValueError(
                f"No location mapping for {stadium} ({stadium_id})."
            )
        enriched = dict(record)
        for column in [
            "venue_label",
            "latitude",
            "longitude",
            "timezone",
            "location_source",
        ]:
            enriched[column] = location[column]
        rows.append(enriched)
    return pd.DataFrame(rows)


def public_schedule_frame(
    schedule: pd.DataFrame, locations: pd.DataFrame, season: int
) -> pd.DataFrame:
    """Return the bounded schedule fields required by the public app."""

    regular = validate_regular_season_schedule(schedule, season)
    enriched = attach_venue_locations(regular, locations)
    optional = ["spread_line", "total_line", "temp", "wind"]
    for column in optional:
        if column not in enriched:
            enriched[column] = pd.NA
    columns = [
        "season",
        "week",
        "game_id",
        "gameday",
        "weekday",
        "gametime",
        "away_team",
        "home_team",
        "stadium_id",
        "stadium",
        "roof",
        "surface",
        "spread_line",
        "total_line",
        "temp",
        "wind",
        "venue_label",
        "latitude",
        "longitude",
        "timezone",
        "location_source",
    ]
    result = enriched[columns].copy()
    for column in ["roof", "surface", "stadium"]:
        result[column] = result[column].fillna("unknown").astype(str)
    return result.reset_index(drop=True)


def default_weather_fetcher(
    latitude: float, longitude: float
) -> dict[str, Any]:
    """Fetch one current hourly forecast from Open-Meteo."""

    parameters = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": (
            "temperature_2m,precipitation_probability,weather_code,"
            "wind_speed_10m,wind_gusts_10m"
        ),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "UTC",
        "forecast_days": 16,
    }
    request = Request(
        f"{WEATHER_API_URL}?{urlencode(parameters)}",
        headers={"User-Agent": "Sunday-Edge-Fantasy-Advisor/2.0"},
    )
    with urlopen(request, timeout=20) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def kickoff_utc(game: pd.Series) -> datetime:
    """Interpret nflverse gametime as U.S. Eastern and return UTC."""

    game_date = date.fromisoformat(str(game["gameday"]))
    parsed_time = time.fromisoformat(str(game["gametime"]))
    eastern = datetime.combine(
        game_date, parsed_time, tzinfo=ZoneInfo("America/New_York")
    )
    return eastern.astimezone(timezone.utc)


def classify_weather_risk(
    temperature_f: float | None,
    wind_mph: float | None,
    gust_mph: float | None,
    precip_probability: float | None,
) -> str:
    """Classify a small set of fantasy-relevant weather warnings."""

    flags: list[str] = []
    if wind_mph is not None and wind_mph >= 20:
        flags.append("HIGH_WIND")
    if gust_mph is not None and gust_mph >= 30:
        flags.append("STRONG_GUSTS")
    if precip_probability is not None and precip_probability >= 60:
        flags.append("PRECIPITATION")
    if temperature_f is not None and temperature_f <= 32:
        flags.append("FREEZING")
    if temperature_f is not None and temperature_f >= 90:
        flags.append("EXTREME_HEAT")
    return " | ".join(flags) if flags else "LOW_WEATHER_RISK"


def forecast_for_game(
    game: pd.Series,
    as_of: datetime,
    fetcher: Callable[[float, float], dict[str, Any]],
    skip_weather: bool = False,
) -> dict[str, Any]:
    """Return one display-only environment record for a scheduled game."""

    roof = str(game["roof"]).strip().lower()
    base: dict[str, Any] = {
        "forecast_status": "",
        "temperature_f": None,
        "wind_mph": None,
        "gust_mph": None,
        "precip_probability": None,
        "weather_code": None,
        "weather_risk": "",
        "forecast_note": "",
    }
    if roof in INDOOR_ROOFS:
        return {
            **base,
            "forecast_status": "INDOORS",
            "weather_risk": "INDOORS",
            "forecast_note": "Indoor venue; outdoor weather is not expected to matter.",
        }
    if pd.notna(game.get("temp")) or pd.notna(game.get("wind")):
        temperature = (
            float(game["temp"]) if pd.notna(game.get("temp")) else None
        )
        wind = float(game["wind"]) if pd.notna(game.get("wind")) else None
        return {
            **base,
            "forecast_status": "RECORDED_GAME_WEATHER",
            "temperature_f": temperature,
            "wind_mph": wind,
            "weather_risk": classify_weather_risk(
                temperature, wind, None, None
            ),
            "forecast_note": "Recorded game weather from the schedule source.",
        }
    game_kickoff = kickoff_utc(game)
    days_until = (game_kickoff.date() - as_of.date()).days
    if skip_weather:
        return {
            **base,
            "forecast_status": "FORECAST_SKIPPED",
            "weather_risk": "FORECAST_UNAVAILABLE",
            "forecast_note": "Forecast retrieval was disabled for this build.",
        }
    if days_until < 0:
        return {
            **base,
            "forecast_status": "PAST_GAME_NO_RECORDED_WEATHER",
            "weather_risk": "FORECAST_UNAVAILABLE",
            "forecast_note": "The game is past and recorded weather is unavailable.",
        }
    if days_until > 16:
        return {
            **base,
            "forecast_status": "FORECAST_NOT_AVAILABLE_YET",
            "weather_risk": "FORECAST_PENDING",
            "forecast_note": "Kickoff is beyond the supported 16-day forecast window.",
        }
    try:
        payload = fetcher(float(game["latitude"]), float(game["longitude"]))
        hourly = payload["hourly"]
        timestamps = pd.to_datetime(hourly["time"], utc=True, errors="raise")
        if len(timestamps) == 0:
            raise ValueError("Forecast response contains no hourly timestamps.")
        nearest = int(
            abs(timestamps - pd.Timestamp(game_kickoff)).argmin()
        )
        temperature = float(hourly["temperature_2m"][nearest])
        wind = float(hourly["wind_speed_10m"][nearest])
        gust = float(hourly["wind_gusts_10m"][nearest])
        precip = float(hourly["precipitation_probability"][nearest])
        weather_code = int(hourly["weather_code"][nearest])
    except (KeyError, TypeError, ValueError, OSError) as error:
        return {
            **base,
            "forecast_status": "FORECAST_FETCH_FAILED",
            "weather_risk": "FORECAST_UNAVAILABLE",
            "forecast_note": f"Forecast retrieval failed: {type(error).__name__}.",
        }
    return {
        **base,
        "forecast_status": "FORECAST_AVAILABLE",
        "temperature_f": round(temperature, 1),
        "wind_mph": round(wind, 1),
        "gust_mph": round(gust, 1),
        "precip_probability": round(precip, 1),
        "weather_code": weather_code,
        "weather_risk": classify_weather_risk(
            temperature, wind, gust, precip
        ),
        "forecast_note": "Display-only Open-Meteo forecast near scheduled kickoff.",
    }


def build_game_context(
    schedule: pd.DataFrame,
    week: int,
    as_of: datetime,
    fetcher: Callable[[float, float], dict[str, Any]] = default_weather_fetcher,
    skip_weather: bool = False,
) -> pd.DataFrame:
    """Build target-week matchup and weather context at one row per game."""

    games = schedule.loc[schedule["week"].eq(week)].copy()
    if games.empty:
        raise ValueError(f"No regular-season games are scheduled in Week {week}.")
    weather_rows = [
        forecast_for_game(row, as_of, fetcher, skip_weather)
        for _, row in games.iterrows()
    ]
    weather = pd.DataFrame(weather_rows, index=games.index)
    result = pd.concat([games, weather], axis="columns")
    result["matchup"] = (
        result["away_team"].astype(str)
        + " @ "
        + result["home_team"].astype(str)
    )
    result["kickoff_et"] = result.apply(
        lambda row: kickoff_utc(row)
        .astimezone(ZoneInfo("America/New_York"))
        .strftime("%a, %b %d - %I:%M %p ET"),
        axis="columns",
    )
    result["forecast_retrieved_at_utc"] = as_of.isoformat()
    columns = [
        "season",
        "week",
        "game_id",
        "matchup",
        "kickoff_et",
        "away_team",
        "home_team",
        "stadium",
        "venue_label",
        "roof",
        "surface",
        "spread_line",
        "total_line",
        "forecast_status",
        "temperature_f",
        "wind_mph",
        "gust_mph",
        "precip_probability",
        "weather_code",
        "weather_risk",
        "forecast_note",
        "forecast_retrieved_at_utc",
    ]
    return result[columns].reset_index(drop=True)


def load_metadata(path: Path) -> dict[str, Any]:
    """Load the current validated publication metadata."""

    with path.open("r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def main() -> None:
    """Build all durable public context artifacts."""

    arguments = parse_arguments()
    metadata = load_metadata(METADATA_PATH)
    season = int(arguments.season or metadata["season"])
    week = int(arguments.week or metadata["week"])
    if week < 1 or week > 18:
        raise ValueError("Target week must be between 1 and 18.")
    as_of = parse_as_of(arguments.as_of)

    calibration_path = Path(arguments.calibration_output or CALIBRATION_PATH)
    accuracy_path = Path(arguments.accuracy_output or ACCURACY_PATH)
    schedule_path = Path(arguments.schedule_output or SCHEDULE_PATH)
    game_context_path = Path(arguments.game_context_output or GAME_CONTEXT_PATH)
    manifest_path = Path(arguments.manifest_output or CONTEXT_MANIFEST_PATH)

    validation_predictions = pd.read_csv(
        VALIDATION_PREDICTIONS_PATH, low_memory=False
    )
    test_predictions = pd.read_csv(TEST_PREDICTIONS_PATH, low_memory=False)
    test_metrics = pd.read_csv(TEST_METRICS_PATH, low_memory=False)
    calibration = build_projection_calibration(
        validation_predictions, test_predictions
    )
    accuracy = build_accuracy_metrics(test_metrics, calibration)

    import nflreadpy as nfl

    schedule_source = nfl.load_schedules([season])
    if hasattr(schedule_source, "to_pandas"):
        schedule_source = schedule_source.to_pandas()
    locations = load_venue_locations(VENUE_LOCATIONS_PATH)
    schedule = public_schedule_frame(schedule_source, locations, season)
    game_context = build_game_context(
        schedule,
        week,
        as_of,
        skip_weather=arguments.skip_weather,
    )

    atomic_write_csv(calibration, calibration_path)
    atomic_write_csv(accuracy, accuracy_path)
    atomic_write_csv(schedule, schedule_path)
    atomic_write_csv(game_context, game_context_path)

    status_counts = {
        str(key): int(value)
        for key, value in game_context["forecast_status"].value_counts().items()
    }
    manifest = {
        "artifact_version": "v1_advisor_context",
        "built_at_utc": as_of.isoformat(),
        "season": season,
        "week": week,
        "projection_calibration": {
            "path": str(calibration_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "rows": len(calibration),
            "sha256": sha256_file(calibration_path),
            "calibration_source": str(
                VALIDATION_PREDICTIONS_PATH.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
            "evaluation_source": str(
                TEST_PREDICTIONS_PATH.relative_to(PROJECT_ROOT)
            ).replace("\\", "/"),
        },
        "model_accuracy": {
            "path": str(accuracy_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "rows": len(accuracy),
            "sha256": sha256_file(accuracy_path),
        },
        "season_schedule": {
            "path": str(schedule_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "rows": len(schedule),
            "sha256": sha256_file(schedule_path),
            "source": SCHEDULE_SOURCE_URL,
        },
        "game_context": {
            "path": str(game_context_path.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "rows": len(game_context),
            "sha256": sha256_file(game_context_path),
            "forecast_status_counts": status_counts,
            "weather_source": WEATHER_SOURCE_URL,
        },
        "venue_mapping": {
            "path": str(VENUE_LOCATIONS_PATH.relative_to(PROJECT_ROOT)).replace(
                "\\", "/"
            ),
            "sha256": sha256_file(VENUE_LOCATIONS_PATH),
            "source": VENUE_SOURCE_URL,
        },
        "context_status": "PASS",
    }
    atomic_write_json(manifest, manifest_path)
    print(f"advisor_context_status={manifest['context_status']}")
    print(f"calibration_rows={len(calibration)}")
    print(f"accuracy_rows={len(accuracy)}")
    print(f"schedule_rows={len(schedule)}")
    print(f"game_context_rows={len(game_context)}")
    print(f"forecast_status_counts={json.dumps(status_counts, sort_keys=True)}")


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    main()
