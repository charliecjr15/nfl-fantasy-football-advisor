# Kicker rankings

## Decision supported

The Kickers view ranks one selected kicker for every team playing in the target
week. Users can switch between ESPN and Yahoo public default scoring. Custom
league settings can produce different totals.

## Scoring profiles

The machine-readable rules and official source links are stored in
`config/kicker_settings.toml`.

ESPN standard scoring awards 3 points for a made field goal from 0-39 yards, 4
from 40-49, 5 from 50-59, 6 from 60 or more, and 1 per made PAT. A missed field
goal is -1. Yahoo public default scoring awards 3 points from 0-39, 4 from
40-49, 5 for every field goal of at least 50 yards, and 1 per made PAT; the
public default table does not apply a missed-field-goal penalty.

The rules were verified against the official
[ESPN scoring guide](https://support.espn.com/hc/en-us/articles/360003914032-Scoring-Formats)
and [Yahoo default settings](https://help.yahoo.com/kb/SLN6489.html).

## Historical player-game facts

The source is nflverse weekly player statistics plus schedules. The table keeps
one recorded kicker row per:

```text
season + week + game_id + player_id
```

Field-goal distance buckets must sum to total makes. Makes, misses, and blocks
must sum to attempts. PAT makes, misses, and blocks must also sum to attempts.
Publication recalculates ESPN and Yahoo points from these event fields.

The 2025 public history contains 543 kicker rows. One NYJ team-game with no
recorded kicking event has no nflverse kicker-stat row; omitting that zero-event
row does not change any player season point total. The public history still
covers all 18 weeks and rejects target-week or future outcomes.

## Target kicker selection

The builder joins the latest depth chart at the source cutoff to the active
season roster. It selects the primary `PK` depth-chart player when available.
If the feeds do not match, it selects one active-roster kicker and records
`ACTIVE_ROSTER_FALLBACK` in the audit evidence.

The current 2026 Week 1 snapshot contains 32 unique kickers for 32 teams and 16
games. It has 31 primary depth-chart selections, one active-roster fallback,
and three players without prior NFL kicking history. Users should confirm the
final team depth chart before kickoff.

## Projection method

Six strict-prior-game recent-form candidates combine the team's last three or
five recorded kicker scores with the last five kicker scores allowed by the
opponent. Candidate selection uses only 2024. Both profiles selected:

```text
60% team last-five average + 40% opponent last-five average
```

The selected method was evaluated without reselection on 543 kicker rows from
2025:

| Profile | 2024 validation MAE | 2025 test MAE | 2025 test RMSE |
|---|---:|---:|---:|
| ESPN | 4.0260 | 3.9168 | 4.9320 |
| Yahoo | 3.9425 | 3.8415 | 4.8269 |

Kicker scoring is volatile because it depends on drives stalling within field
goal range. Use the values as comparative rankings, not guaranteed totals.

## App behavior

The My Lineup view includes a separate kicker selector. Previous Weeks shows
actual kicker points under either profile. Season Totals combines completed
full-PPR offense with kicker points from the selected profile; D/ST remains a
team entry and is intentionally excluded from the player totals table.
