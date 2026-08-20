# Clean Analytical Layer and Validation

## Technical summary

The MySQL clean analytical layer is ready for leakage-safe feature engineering. All ten clean tables reconciled exactly to their expected row counts,
contained no duplicate intended keys, had no unavailable required keys, passed their domain rules, and followed the configured chronological data split.

The core player_weeks fact table contains 45,693 regular-season QB, RB, WR, and TE observations from 2018 through 2025. Every row reconciled exactly to
the configured full-PPR scoring formula. Player-to-game, player-to-team-week, roster, schedule, and identity relationships all passed.

Several small source limitations remain, but none indicate a failed transformation:

- 349 of 196,130 snap records lack a GSIS player match, producing 99.82% coverage.
- 12 of 43,561 injury records lack a same-team weekly roster match, producing 99.97% coverage.
- 186 of 548,638 timestamped depth-chart records lack a roster-derived player-dimension match, producing 99.97% coverage.
- The 2025 injury feed does not provide update timestamps.
- Timestamped depth charts extend beyond the regular season and require an as-of join.
- Legacy depth charts contain week-19 snapshots that do not correspond to regular-season game facts.

These limitations require explicit feature-engineering safeguards but do not prevent the clean layer from supporting the next modeling phase.

## Validated table inventory

Each table has its own analytical grain. Row counts across these tables must not be interpreted as one combined population.

- `games`: 2,127 rows — one regular-season NFL game — PASS
- `team_weeks`: 4,254 rows — one team per regular-season game week — PASS
- `player_weeks`: 45,693 rows — one core fantasy player per regular-season week — PASS
- `roster_player_weeks`: 362,828 rows — one player-team roster record per week — PASS
- `players`: 7,920 rows — one descriptive record per GSIS player ID — PASS
- `player_week_id_crosswalk`: 352,455 rows — one GSIS-to-PFR mapping per player-team-week — PASS
- `injury_player_weeks`: 43,561 rows — one player-team injury record per week — PASS
- `snap_player_weeks`: 196,130 rows — one player-team snap record per week — PASS
- `depth_chart_legacy_weeks`: 242,058 rows — one legacy player-position-rank record per week — PASS
- `depth_chart_snapshots`: 548,638 rows — one player-position-slot record per timestamp — PASS

## Scope and definitions

The clean layer covers the 2018 through 2025 NFL regular seasons.

The modeling split is chronological:

- `2018-2023`: `training` — model fitting and historical feature construction
- `2024`: `validation` — model selection and tuning
- `2025`: `test` — final out-of-time evaluation

The primary fantasy-outcome population contains the following positions:

- Quarterback (QB)
- Running back (RB)
- Wide receiver (WR)
- Tight end (TE)

The roster, injury, snap, and depth-chart tables retain additional NFL positions when those records are useful for identity, team context, or data-quality
reconciliation.

A player is identified primarily by the NFL GSIS ID. PFR IDs are retained as a secondary identifier because the snap-count source uses PFR identifiers.

## Transformation design

### Games and team weeks

games is derived from stg_schedules at one row per game_id.

team_weeks expands every game into two records:

- One home-team record
- One away-team record

Every game produced exactly two reciprocal team records. Scores, opponents, game IDs, locations, and result margins reconcile to the parent game.

The source spread_line remains stored as source_spread_line. It has not yet been interpreted as a team-relative spread because that interpretation must
account for the source convention and home/away direction.

### Core player weeks

player_weeks is derived from stg_weekly_player_stats.

Its primary grain is:

season + week + player_id

The table contains only regular-season QB, RB, WR, and TE records.

The observed `fantasy_points_ppr` value is the outcome for the same player-week. It is not a permissible current-week predictor. Feature engineering must
shift the outcome forward or otherwise align it as the future target.

### Weekly rosters and player identity

`roster_player_weeks` retains records with an available GSIS ID. The staging table contained 362,959 rows, and 131 rows without an available GSIS ID were
excluded from the clean roster table.

The `players` table selects one latest descriptive roster record for each GSIS ID. It is intended for names, display fields, and identity lookup.

Because it represents the latest observed record, the following `players` fields must not be used as historical model features without temporal
reconstruction:

- Latest team
- Latest position
- Latest status
- Latest roster season
- Latest roster week

Time-varying roster features must come from `roster_player_weeks`.

### GSIS-to-PFR crosswalk

`player_week_id_crosswalk` preserves GSIS-to-PFR identity at the following grain:

```text
season + week + team + player_id

This time-aware grain prevents a current identifier or team assignment from being applied incorrectly to earlier seasons or weeks.

The crosswalk is used to attach GSIS IDs to snap-count records.

### Injury reports

injury_player_weeks retains one record per player, team, and week.

The table includes explicit availability flags:

- has_final_report_status
- has_practice_status
- has_update_timestamp

A missing final injury-report status does not mean the player was healthy. Across seasons, final report status is missing for approximately 51% to 55% of
injury rows. This rate is stable across the historical period and reflects source behavior rather than a sudden pipeline failure.

The date_modified_utc field is populated for 2018 through 2024. The 2025 source does not provide that timestamp.

### Snap counts

snap_player_weeks retains every valid PFR player-game record from staging.

When the weekly identity crosswalk finds a GSIS ID, the record receives:

player_id_match_status = matched

When no GSIS ID can be resolved, the snap record is retained with:

player_id_match_status = unmatched

Retaining unmatched evidence prevents silent row loss and makes coverage measurable.

### Depth charts

The project uses two separate depth-chart tables because the source format changes over time.

depth_chart_legacy_weeks contains weekly records from 2018 through 2024. These records do not provide a precise within-week update timestamp.

depth_chart_snapshots contains timestamped 2025 records. These snapshots support an as-of join using the latest record available at or before the
prediction cutoff.

The two formats must not be combined under one assumed temporal rule.

## Validation evidence

### Row retention and grain

All clean tables matched their expected row counts exactly.

Every intended primary or composite key had zero duplicate groups.

Every table had zero rows with unavailable required key values.

These results show that the transformation did not introduce unexpected row loss, duplicated grains, or invalid primary identifiers.

### Domain and split validity

All ten clean tables returned zero domain-invalid rows.

The validation covered:

- Regular-season week ranges
- Allowed fantasy positions
- Home and away flags
- Injury availability flags
- Snap match statuses
- Nonnegative snap counts
- Percentage ranges with source rounding tolerance
- Legacy and timestamped depth-chart rules
- Chronological data-split assignments

Every row followed the configured training, validation, or test split.

### Full-PPR scoring

All 45,693 core player-week rows contained an observed full-PPR result.

The clean table’s configured full-PPR calculation was compared with the source full-PPR value using a tolerance of 0.01 points.

Results:

- Player-week rows: 45,693
- Missing PPR rows: 0
- PPR mismatch rows: 0
- Maximum absolute difference: 0.0
- Validation: PASS

### Schedule consistency

All schedule and matchup controls passed:

- Every game has exactly two team-week records.
- Game totals equal the combined team scores.
- Game results equal the home-team scoring margin.
- Team-week records have reciprocal opponents.
- Every player-week record has a parent game.
- Every player-week record has a matching team-week.
- Player opponents agree with the schedule.
- Every snap record has a matching team-week.
- Snap opponents agree with the schedule.

### Player identity integrity

All core player rows have both a player-dimension record and a same-team weekly roster record.

All crosswalk rows have matching weekly roster and player-dimension records.

No PFR ID maps to multiple GSIS players within the same team-week, and no populated PFR ID maps to multiple GSIS IDs in the player dimension.

The source also contains three expected identity conditions:

- Multi-team roster player-week groups: 13 — expected transaction-week behavior
- Weekly roster rows flagged for PFR conflict: 68 — retained and explicitly flagged
- Player-dimension records without a PFR ID: 1,250 — GSIS remains the authoritative ID

## Documented source limitations

### Snap-count identity coverage

Of 196,130 snap records:

- 195,781 matched a GSIS player.
- 349 remained unmatched.
- Match coverage is 99.82%.

This is a low-severity identity limitation. Unmatched rows remain available for aggregate team or position analysis but cannot be used as player-level
GSIS features without additional identity resolution.

### Injury-to-roster coverage

Of 43,561 injury records:

- 43,549 matched a same-team weekly roster row.
- 12 remained unmatched.
- Six unmatched records involved QB, RB, WR, or TE players.
- Match coverage is 99.97%.

The unmatched cases are primarily associated with transaction or trade weeks. They must not be forced onto a different team merely to increase the match
rate.

### Depth-chart identity coverage

All 242,058 legacy depth-chart records matched the roster-derived player dimension.

Of 548,638 timestamped depth-chart records:

- 548,452 matched the player dimension.
- 186 records remained unmatched.
- The unmatched rows represent three players.
- Match coverage is 99.97%.

This is a small and localized source limitation.

### Injury timestamp limitations

The 2025 injury feed contains 5,783 records, and none provide an update timestamp.

Across the dated 2018–2024 injury records, 23 updates occurred on a calendar date after the corresponding game date. These records are definitively
unavailable for pregame prediction and must be excluded from same-game features.

A same-date injury update is not automatically safe. A future phase must align the update timestamp with a correctly normalized game-kickoff timestamp
before treating it as pregame evidence.

### Legacy week-19 depth records

The legacy source includes 7,221 week-19 depth records:

- 2021: 1,749 rows
- 2022: 1,853 rows
- 2023: 1,807 rows
- 2024: 1,812 rows

These are retained as valid source snapshots. Regular-season game and player facts stop at week 18, so week-19 depth records must not join to a
nonexistent game week.

### Timestamped depth records extend beyond the season

The timestamped depth-chart feed ranges from August 3, 2025 through March 14, 2026.

The final regular-season game date in the clean schedule is January 4, 2026. There are 183,817 timestamped depth records after that date, representing
approximately one-third of the timestamped table.

This proves that selecting a player’s globally latest depth-chart record would leak postseason or offseason information into regular-season predictions.

## Leakage-safe feature requirements

The next feature-engineering phase must enforce the following rules.

### Fantasy outcomes

For a prediction made for week t, the observed PPR result from week t is the target, not a feature.

Rolling fantasy statistics must use only games completed before the week-t prediction cutoff.

### Snap counts

Snap counts are postgame evidence.

A week-t prediction may use snap information only from games completed before the week-t cutoff. Same-week snap values must never be used to predict the
same game.

### Weekly roster information

Historical roster features must come from roster_player_weeks.

The latest-record fields in players are descriptive lookup values only and must not be treated as historically known attributes.

### Injury information

For 2018 through 2024, injury records may be used only when their update timestamp is at or before the prediction cutoff.

The 23 records known to occur after their game date must be excluded from pregame features.

Because 2025 injury records lack update timestamps, the initial safe approach is to use prior-week injury information or exclude same-week injury features
from the 2025 test set.

### Timestamped depth charts

For each 2025 game, the feature pipeline must select the latest depth snapshot available at or before the prediction cutoff.

Snapshots after that cutoff must be excluded, including all postseason and offseason updates.

### Legacy depth charts

Because 2018–2024 legacy depth rows do not provide precise within-week timestamps, the safest initial implementation is to lag legacy depth features by at
least one week.

Week-19 legacy rows must not join to regular-season player outcomes unless a corresponding scheduled game exists.

## Fitness-for-use decision

The clean layer is fit for the next phase of the project.

Confidence is high for:

- Table grains
- Required identifiers
- Row retention
- Full-PPR scoring
- Schedule joins
- Core player identity
- Chronological data splits

The remaining risks are temporal rather than structural. They can be controlled through explicit prior-week and as-of feature rules.

This validation does not establish that a future fantasy model will be accurate. It establishes that the clean data foundation is internally consistent
and suitable for building and testing a prediction pipeline without avoidable join errors or known scoring discrepancies.

## Reproducibility

The clean layer is rebuilt by running:

sql/04_create_clean_tables.sql

The complete read-only validation is run with:

sql/05_validate_clean_tables.sql

Both scripts use the MySQL database:

nfl_fantasy_advisor

The clean transformation preserves all six staging tables and can be rerun from the validated staging layer.

Validation evidence in this document was observed on August 20, 2026.

## Recommended next steps

1. Build a player-week modeling frame with a clearly defined prediction week and target week.
2. Create lagged and rolling player-performance features using only completed prior games.
3. Add prior-week snap and opportunity features.
4. Implement conservative injury features that respect timestamp availability.
5. Create separate temporal rules for legacy and timestamped depth charts.
6. validate every engineered feature against its prediction cutoff.
7. Train only on 2018–2023, tune on 2024, and reserve 2025 for final out-of-time testing.

## Further questions

- Should the first model predict every rostered player or only players meeting a recent-usage threshold?
- Should next-week targets follow calendar week numbers or each player’s next actual game after a bye?
- Which injury variables remain reliable when precise update timestamps are unavailable?
- Should legacy depth-chart features initially be excluded, or included only with a one-week lag?
- What minimum snap, target, or carry threshold should define a draft-relevant player population?