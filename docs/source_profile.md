# NFL Fantasy Advisor Source Profile

## Status

Approved for player-week pipeline development with documented missing-data and temporal-join controls.

## Audit snapshot

- Audit date: 2026-08-20
- Audited season: 2025
- Season scope: Regular season only
- Core fantasy positions: QB, RB, WR, and TE
- Python version: 3.11
- nflreadpy version: 0.1.5
- Polars version: 1.43.2

The audit used cached source data loaded through the maintained nflreadpy (https://github.com/nflverse/nflreadpy) package. The underlying data comes from nflverse-data (https://github.com/nflverse/nflverse-data).

## Intended analytical grain

The main historical modeling table will contain one row per:

season + week + player_id

The 2025 regular-season source supports this grain. All 6,037 core-position player-stat rows were unique at both the player-week and player-game grains.

The source game_id will still be retained for schedule validation, game-level joins, and protection against unexpected future scheduling exceptions.

## Source datasets

- Weekly player statistics: 19,422 source rows; 18,540 regular-season rows; 6,037 core-position rows; player-game or player-week grain.
- Game schedules: 285 source rows; 272 regular-season games; one row per game.
- Weekly rosters: 46,849 source rows; 44,697 regular-season rows; 13,689 core-position rows; player-team-week grain.
- Injury reports: 6,068 source rows; 5,783 regular-season rows; 1,750 core-position rows; player-team-week grain.
- Depth charts: 554,215 source rows; 144,517 core-position rows; player-position-slot-snapshot grain.
- Snap counts: 26,612 source rows; 25,395 regular-season rows; 6,804 core-position rows; player-game grain.

The source datasets contain regular-season and postseason records. Every historical model input must explicitly filter to regular-season records.

## Candidate-key validation

All tested candidate keys were unique after excluding unavailable identifiers.

- Schedule `game_id`: 0 repeated key groups.
- Schedule `season + week + team`: 0 repeated key groups.
- Core statistics `season + week + player_id`: 0 repeated key groups.
- Core statistics `season + week + game_id + player_id`: 0 repeated key groups.
- Weekly roster `season + week + team + gsis_id`: 0 repeated key groups.
- Weekly roster `season + week + gsis_id`: 0 repeated key groups.
- Injury report `season + week + team + gsis_id`: 0 repeated key groups.
- Snap count `season + week + game_id + team + pfr_player_id`: 0 repeated key groups.
- Snap count `season + week + team + pfr_player_id`: 0 repeated key groups.
- Depth chart `dt + team + gsis_id + pos_abb + pos_slot`: 0 repeated key groups.

No exact duplicate core player-stat rows were found.

## Identifier quality

### Weekly player statistics

All 6,037 regular-season QB, RB, WR, and TE rows had an available GSIS player_id.

This identifier will be the main player key for the analytical player-week table.

### Weekly rosters

Among 13,689 core-position roster rows:

- 9 rows had an unavailable gsis_id, or approximately 0.07%.
- 955 rows had an unavailable pfr_id, or approximately 6.98%.
- No GSIS-to-PFR crosswalk key mapped to multiple PFR identifiers.

The full weekly roster must be used as the identity lookup even when the modeling population is limited to QB, RB, WR, and TE. Source position labels can differ across datasets.

For example, 13 Bo Melton player-week rows initially failed when the roster lookup was filtered to core positions. All 13 matched when the complete roster was used.

### Snap counts

All 6,804 core-position snap rows had an available pfr_player_id.

Snap counts use PFR identifiers rather than GSIS identifiers. Weekly rosters provide the required GSIS-to-PFR crosswalk.

### Depth charts

Among 144,517 core-position depth-chart rows:

- 1,964 had an unavailable gsis_id, or approximately 1.36%.
- No invalid depth-chart timestamps were found.
- There were 219 distinct snapshot dates.

Rows without a usable GSIS identifier cannot be used in direct player-level joins unless a separately validated mapping is available.

## Join coverage

- Player statistics to schedule: 6,037 of 6,037 matched; 100.00%.
- Player statistics to weekly roster: 6,037 of 6,037 matched; 100.00%.
- Injury reports to weekly roster: 1,750 of 1,750 matched; 100.00%.
- Core snap counts to weekly roster: 6,779 of 6,804 matched; 99.63%.
- Player statistics to snap counts through the PFR crosswalk: 6,023 of 6,037 matched; 99.77%.

The 14 player-stat rows without matched snap counts consist of:

- 11 rows without an available weekly-roster PFR mapping.
- 3 rows with a PFR mapping but no corresponding snap-count record.

These exceptions are small and localized. They do not justify removing valid player-week outcome rows.

Snap-count and snap-share features will remain nullable. The processed table will also include a snap-data availability flag so the model can distinguish missing snap evidence from a recorded zero.

## Injury-report interpretation

Among 1,750 core-position injury rows:

- 942 lacked a final report status, or 53.83%.
- 15 lacked a practice status, or 0.86%.
- All 1,750 matched a weekly roster row.

A missing final report status is part of the source reporting pattern and must not automatically be interpreted as a healthy player.

Final report status, practice participation, and record availability will be stored as separate fields. Missing injury-report information will not be silently converted to a definitive health classification.

## Depth-chart temporal controls

Depth-chart timestamps ranged from 2025-08-03 through 2026-03-14.

The source contains snapshots created after many 2025 games. Joining a final or future depth chart to an earlier game would leak information that was not available at prediction time.

For every player-game or player-week feature row, the depth-chart join must use:

latest depth-chart timestamp strictly before the applicable game timestamp

A transformed record must preserve the selected depth-chart timestamp so the as-of rule can be audited.

## Full-PPR scoring reconciliation

The configured scoring rules include:

- 0.04 points per passing yard
- 4 points per passing touchdown
- -2 points per interception
- 0.10 points per rushing yard
- 6 points per rushing touchdown
- 1 point per reception
- 0.10 points per receiving yard
- 6 points per receiving touchdown
- 6 points per individual special-teams touchdown
- 2 points per passing, rushing, or receiving two-point conversion
- -2 points per lost sack, rushing, or receiving fumble

The calculation follows the nflfastR player-stat formula (https://github.com/nflverse/nflfastR/blob/master/R/calculate_stats.R).

All 6,037 core player-week records reconciled to the source fantasy_points_ppr value within a tolerance of 0.01 points:

- Rows outside tolerance: 0
- Difference rate: 0.00%
- Maximum absolute difference: approximately 0.000000000000007 points

The tiny maximum difference is normal floating-point representation and is not an analytical discrepancy.

The broader fumbles_lost_total field will not be used to reproduce the nflverse fantasy-point calculation because it also includes fumbles outside the source formula's sack, rushing, and receiving categories.

## Data-quality findings

### Critical or high-severity issues

None identified in the audited 2025 sources.

### Medium-risk controls

1. Depth charts create a serious leakage risk if they are not joined with an as-of timestamp rule.

2. Missing final injury status has ambiguous meaning and must remain distinct from a confirmed healthy designation.

3. Identity lookups must use complete rosters rather than position-filtered rosters.

These are transformation and modeling controls rather than evidence that the underlying source is unusable.

### Low-severity exceptions

1. Nine core weekly-roster rows lack GSIS identifiers.
2. Some weekly-roster records lack PFR identifiers.
3. Fourteen core player-stat rows cannot be linked to snap data.
4. Some depth-chart rows lack GSIS identifiers.

These exceptions will be retained as documented missing values where appropriate. Valid player-week outcomes will not be dropped merely because an optional feature is unavailable.

## Required pipeline rules

The processing pipeline must:

1. Filter all applicable sources to regular-season records.
2. Limit the initial modeling population to QB, RB, WR, and TE.
3. Use GSIS player_id as the primary player identifier.
4. Retain game_id for schedule and game-level validation.
5. Use full weekly rosters for identity resolution.
6. Use roster pfr_id to connect GSIS player records to snap counts.
7. Prevent row multiplication during every join.
8. Preserve unmatched optional features as null.
9. Add availability flags for snap, injury, and depth-chart evidence.
10. Join depth charts using only snapshots available before game time.
11. Calculate fantasy points independently from component statistics.
12. Reconcile calculated fantasy points to source values.
13. Preserve source season, week, game, player, and extraction metadata.
14. Never use future-week or postgame information as a prediction feature.

## Recommended automated tests

Future extraction and transformation scripts should test:

- Required source columns are present.
- Core player-stat IDs are available.
- Player-week keys are unique.
- Schedule game IDs are unique.
- Schedule team-week appearances are unique.
- Roster, injury, and snap candidate keys are unique.
- Player-stat-to-schedule coverage is 100%.
- Player-stat-to-roster coverage is 100%.
- Joins do not increase the base-row count unexpectedly.
- Snap coverage remains above a documented monitoring threshold.
- Calculated fantasy points reconcile within 0.01 points.
- Selected depth-chart timestamps precede game timestamps.
- Processed modeling rows contain only regular-season weeks.
- Feature calculations use only information available before the target game.

## Reproduction commands

Activate the project virtual environment and run:

python scripts\inspect_source.py --season 2025
python scripts\audit_source.py --season 2025

The inspection script profiles source structure and missingness. The audit script validates candidate keys, joins, temporal fields, and fantasy-point calculations.

## Readiness decision

The audited sources are approved for the next project phase.

The next phase will define the historical extraction range, select the columns
needed for modeling, and produce reproducible processed source files. The documented missing-data and temporal controls must remain in place throughout that work.