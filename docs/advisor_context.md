# Advisor context and decision tools

## Purpose

The public app keeps the frozen player model unchanged while adding four
display and planning artifacts around each validated weekly snapshot:

- `projection_calibration.csv`: position-specific 80% residual intervals
  calibrated on the 2024 validation season and checked on the untouched 2025
  test season.
- `model_accuracy.csv`: the frozen 2025 test metrics plus observed interval
  coverage.
- `season_schedule.csv`: all 272 validated regular-season games, including
  venue, surface, betting-line, location, and timezone context.
- `game_context.csv`: the target week's 16 games plus kickoff labels and
  display-only weather status.

`advisor_context.json` records their row counts, hashes, season, week, source
links, and overall `PASS` status. The Streamlit app refuses to combine this
context with a different published projection week.

## Projection ranges

For each position, the builder calculates the 10th and 90th percentiles of
`actual PPR - predicted PPR` on the 2024 validation rows. Those residuals are
added to the current point projection, with the lower display value floored at
zero. The committed 2025 evaluation coverage is shown in the app. These ranges
describe historical model error; they are not confidence guarantees for an
individual player.

## Schedule, byes, and rest-of-season proxy

The schedule must contain 272 unique regular-season games, Weeks 1-18, 32
teams, and exactly 17 appearances per team. Each team's one missing week is its
bye. The rest-of-season planning proxy is intentionally simple and auditable:

`current weekly projection x scheduled games remaining`

It supports rough trade and schedule planning. It does not claim to forecast
future injuries, role changes, or opponent-specific projections.

## Weather

Indoor venues are labeled without an API request. Outdoor forecasts come from
Open-Meteo only when kickoff is inside its supported 16-day window. Before that
window, the app says the forecast is pending. Fetch failures remain visible as
unavailable and never block the validated player projections.

## External integrations

The current public release does not claim live scoring or automatic league
sync. True live tracking requires a reliable live-stat provider and its
credentials. Yahoo roster import requires user OAuth authorization and a
secure callback/state store. ESPN does not expose a supported public fantasy
league API. Until those dependencies are supplied and validated, the app uses
a shareable roster link, CSV download, and explicit connection-status cards.

## Build locally

```powershell
.\.venv\Scripts\python.exe scripts\build_advisor_context.py
```

Use `--skip-weather` for an offline build. The scheduled GitHub workflow runs
the builder after a weekly snapshot passes publication.
