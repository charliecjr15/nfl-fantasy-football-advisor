# Defense/Special Teams rankings

## Decision supported

The D/ST view ranks all defenses playing in the target week under either ESPN
or Yahoo public default scoring. It is intended for weekly start, sit, and
streaming decisions. Custom league settings can produce different totals.

## Scoring profiles

The machine-readable rules are stored in `config/league_settings.toml`.

Both profiles award:

- 1 point per sack
- 2 points per interception
- 2 points per opponent-fumble recovery
- 6 points per defensive or special-teams touchdown
- 2 points per blocked kick
- 2 points per safety

ESPN and Yahoo use different points-allowed bands. ESPN standard scoring also
uses total-yards-allowed bands; Yahoo public default scoring does not. The rules
were verified against the official
[ESPN scoring guide](https://support.espn.com/hc/en-us/articles/360003914032-Scoring-Formats)
and [Yahoo default settings](https://help.yahoo.com/kb/SLN6489.html).

## Historical team-game facts

The source is nflverse weekly player statistics plus schedules. Player-level
defensive and special-teams statistics are aggregated to one row per:

```text
season + week + game_id + team
```

Every completed game must produce two reciprocal team rows. Points allowed are
the opponent's final score less six points for each opponent defensive-return
touchdown. Opponent special-teams touchdowns remain included because they count
against D/ST. Total yards allowed use net passing yards plus rushing yards.

Team sacks use the opponent's official times-sacked total. Individual defender
sack credits were one lower in 30 of 1,632 audited team-games from 2023-2025,
while the offensive times-sacked field preserved the team event count. Team
interceptions reconciled exactly to opponent interceptions thrown in all 1,632
team-games.

The public completed-results file is limited to the prior season and completed
weeks of the current season. Target-week and future outcomes are rejected.

## Projection method

Six strict-prior-game recent-form candidates are evaluated. They combine a
defense's last three or five results with the last five D/ST results allowed by
its upcoming opponent. Candidate selection uses only the 2024 validation
season. Both scoring profiles selected:

```text
40% defense last-five average + 60% opponent last-five average
```

The selected method was then evaluated without reselection on 544 team-games
from the 2025 season:

| Profile | 2024 validation MAE | 2025 test MAE | 2025 test RMSE |
|---|---:|---:|---:|
| ESPN | 4.7002 | 4.7441 | 6.0480 |
| Yahoo | 4.2718 | 4.4755 | 5.7387 |

These errors make the output more appropriate for comparative rankings than
precise point forecasts. D/ST touchdowns and turnovers are volatile, and the
projection is not a guarantee.

## Weekly controls

Publication fails when keys are missing or duplicated, a game does not contain
two defenses, ranks are incomplete, projections or results are non-finite,
history contains the target week, platform rules differ from the manifest hash,
or D/ST schedule coverage differs from player-ranking coverage.
