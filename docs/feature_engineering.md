# Leakage-Safe Feature Engineering

## Purpose

This document defines the first model-ready player-week dataset for the NFL Fantasy Football Advisor.

The feature pipeline will convert the validated clean analytical tables into predictors that could have been known before each target game. Its purpose is
to prevent future results, same-game statistics, and later source updates from leaking into historical predictions.

## Version 1 prediction task

Version 1 will predict a player’s full-PPR fantasy points for an upcoming regular-season game.

The initial model includes:

- Quarterbacks
- Running backs
- Wide receivers
- Tight ends

The outcome is:

```text
target_fantasy_points_ppr

“One-week-ahead” means that a row for NFL week t predicts the player’s fantasy result in week t using only information from games completed before that
week.

## Modeling grain

The modeling dataset will contain one row per:

season + week + player_id

Each row represents one player’s target game and includes:

- Target season
- Target week
- Player identifier
- Player name
- Position
- Team
- Opponent
- Game identifier
- Home or away status
- Chronological data split
- Observed target fantasy points
- Features calculated only from earlier games

The combination of season, week, and player_id must be unique.

## Initial labeled population

The first labeled modeling frame will be anchored to the validated player_weeks table.

This provides 45,693 regular-season QB, RB, WR, and TE observations with:

- Valid player identifiers
- Valid schedule matches
- Valid team and opponent values
- Reconciled full-PPR outcomes

A missing player_weeks record will not automatically be converted to zero fantasy points.

This initial population therefore predicts fantasy production conditional on a player appearing in the weekly statistics source. A later candidate-
generation phase will use weekly rosters, schedules, recent usage, and availability evidence to identify players who should receive a projection before a
game.

## Target and feature alignment

For a modeling row in target week t:

- target_fantasy_points_ppr comes from the player’s observed week-t result.
- Week-t statistics are never predictors for that same row.
- Rolling player features use only games before week t.
- Snap-count features use only previously completed games.
- Injury and depth-chart features use conservative prior-week rules unless a trustworthy pregame timestamp is available.
- Current-game scores and postgame results are never model features.

The current target does not need to be physically shifted into a later row if every feature window explicitly ends before the target row.

## Prediction cutoff

The initial feature pipeline will use a conservative week-level cutoff.

For target week t, Version 1 will use only records associated with weeks earlier than t.

This rule intentionally excludes same-week:

- Player statistics
- Snap counts
- Final game results
- Injury updates
- Depth-chart information

A later production version may use exact pregame timestamps when schedule and source timestamps have been normalized to the same timezone and
independently validated.

## Chronological data split

Rows will retain the split assigned to their target season:

- 2018-2023: training
- 2024: validation
- 2025: test

Feature calculations may use historical games from an earlier split when that history would genuinely have been known before the target game.

Model fitting and evaluation must still respect the target-row split:

- Training targets are used to fit models.
- Validation targets are used for model selection and tuning.
- Test targets remain hidden until final evaluation.

## Feature naming convention

Feature names will describe both the measure and its historical window.

Examples:

- `fantasy_points_ppr_prev_game`
- `fantasy_points_ppr_avg_last_3_games`
- `fantasy_points_ppr_avg_last_5_games`
- `fantasy_points_ppr_season_to_date`
- `targets_avg_last_3_games`
- `offense_pct_prev_game`

The phrase `last_3_games` means the player’s previous three recorded games, not necessarily the previous three NFL week numbers. This distinction
preserves useful history across bye weeks and missed games.

## Player-history controls

The modeling frame will include history controls that describe how much prior evidence supports each prediction:

- `prior_games_count`
- `prior_games_current_season`
- `previous_game_season`
- `previous_game_week`
- `previous_game_date`
- `days_since_previous_game`
- `is_first_observed_game`
- `is_first_observed_game_of_season`

These controls help distinguish an established player from a rookie, newly active player, or player returning after an extended absence.

Missing history will remain `NULL`. It will not automatically be converted to zero.

## Fantasy-performance features

The initial fantasy-performance features will include:

- Previous-game full-PPR points
- Average full-PPR points over the previous three games
- Average full-PPR points over the previous five games
- Standard deviation of full-PPR points over the previous five games
- Minimum full-PPR points over the previous five games
- Maximum full-PPR points over the previous five games
- Season-to-date average full-PPR points
- Season-to-date standard deviation of full-PPR points

Every window must end at the game immediately before the target game.

## Opportunity and volume features

The initial opportunity measures will include:

- Passing attempts
- Carries
- Targets
- Receptions
- Touches
- Position-adjusted opportunities
- Passing yards
- Rushing yards
- Receiving yards
- Yards from scrimmage
- Passing touchdowns
- Rushing touchdowns
- Receiving touchdowns

Derived definitions:

```text
touches = carries + receptions

position_adjusted_opportunities =
    attempts + carries              for quarterbacks
    carries + targets               for running backs
    targets                         for wide receivers and tight ends

yards_from_scrimmage = rushing_yards + receiving_yards

These measures will receive previous-game, previous-three-game, previous-five-game, and season-to-date summaries where useful.

## Efficiency features

The initial efficiency measures will include:

- Completion percentage
- Passing yards per attempt
- Rushing yards per carry
- Receiving yards per target
- Receiving yards per reception
- Fantasy points per position-adjusted opportunity
- Total yards per position-adjusted opportunity

Ratios must use a protected denominator. A zero or unavailable denominator produces NULL, not zero and not an infinite value.

Rolling efficiency should be calculated from rolling numerators and denominators rather than by averaging individual-game ratios.

## Usage-share and snap features

The initial usage measures will include:

- Target share
- Air-yards share
- Weighted opportunity rating
- Offensive snap count
- Offensive snap percentage

Snap counts are postgame evidence. The target game’s snap values are forbidden.

Snap features may use:

- Previous-game offensive snaps
- Previous-game offensive snap percentage
- Average offensive snaps over the previous three games
- Average offensive snap percentage over the previous three games
- Average offensive snap percentage over the previous five games

An unavailable GSIS match or missing snap record remains NULL and receives an explicit availability flag.

## Pregame schedule and matchup context

The following target-game values are known before the game and may be used as predictors:

- Home or away status
- Team rest days
- Opponent rest days
- Divisional-game flag
- Pregame point spread
- Pregame total
- Roof
- Surface

Temperature and wind may be added only after confirming that their historical values represent information available before kickoff.

The following target-game values are outcomes and are forbidden as predictors:

- Team points scored
- Opponent points scored
- Result margin
- Game total calculated from final scores
- Overtime result
- Home score
- Away score

## Opponent-strength features

Opponent-strength features will be calculated from games completed before the target week.

The initial measures will include:

- Opponent average full-PPR points allowed to the player’s position
- Opponent three-game average full-PPR points allowed to the player’s position
- Opponent season-to-date average full-PPR points allowed to the player’s position
- Opponent season-to-date passing yards allowed
- Opponent season-to-date rushing yards allowed
- Opponent season-to-date receiving yards allowed

Opponent features must first be aggregated to one row per:

season + week + defensive_team + position

Historical windows must then exclude the target week before joining back to the player modeling frame.

## Conservative availability features

Version 1 may use the following only from a prior week:

- Weekly roster status
- Weekly roster status-description abbreviation
- Injury-report status
- Practice status
- Depth-chart position
- Depth-chart rank

Current-week injury and depth information is excluded from the initial historical model because timestamp availability is inconsistent across seasons.

The project may later add true as-of pregame features after all source timestamps and game kickoff times have been normalized and validated.

## Forbidden feature sources

The following fields must never be used directly as predictors for their own target row:

- Current-week fantasy points
- Current-week player statistics
- Current-week snap counts
- Final target-game scores
- Final target-game result
- Current-week points for or points against
- Current-week overtime result
- Later injury updates
- Later depth-chart snapshots
- Postseason or offseason depth-chart snapshots
- Latest-record team, position, or status values from players
- Target values from validation or test rows
- Database creation timestamps
- The data_split label

Identifiers such as player name, player ID, game ID, team, and opponent may be retained for auditing and output, but they are not automatically numerical
model features.

## Missing-value treatment

The feature table will preserve the difference between:

- A true observed zero
- No prior player history
- A source field that is unavailable
- A failed or unavailable identifier match
- A feature that is not applicable to the player’s position

Rules:

- No prior game produces `NULL` lag and rolling values.
- Missing snap matches produce `NULL` snap features.
- Missing historical injury or depth records do not imply that a player was healthy or first string.
- Position-inapplicable measures may remain zero only when the source explicitly records an observed zero.
- Ratio denominators of zero produce `NULL`.
- Every important optional source receives an availability flag.
- Statistical imputation will occur later in the Python modeling pipeline, not silently inside the SQL transformation.

## History and eligibility flags

All labeled rows will remain in the feature table, including rows with limited history.

The table will include:

- `has_previous_game`
- `has_3_prior_games`
- `has_5_prior_games`
- `has_previous_snap_record`
- `has_opponent_history`
- `has_prior_roster_record`
- `has_prior_injury_record`
- `has_prior_depth_record`

These flags allow the modeling pipeline to compare:

- All labeled player-weeks
- Players with at least one prior game
- Players with at least three prior games
- Players with at least five prior games

The initial three-game rolling baseline will be evaluated only where three prior games are available. More advanced models may retain lower-history rows
by using missing-value indicators and position-level priors.

## Planned analytical tables

The feature pipeline will build three analytical tables.

### `player_game_history`

Grain:

```text
season + week + player_id

This table will combine validated historical player results with schedule context and same-game snap evidence.

It is a postgame history source used to calculate later windows. It is not model-ready because its current-row statistics and snap values describe the
target game itself.

### opponent_position_week_history

Grain:

season + week + defensive_team + position

This table will aggregate the fantasy production and yardage allowed by each defense to each core fantasy position.

Its same-week values are postgame history. Only lagged and prior-game rolling summaries may enter the final modeling table.

### model_player_weeks

Grain:

season + week + player_id

This is the final model-ready table.

It will contain:

- Identifiers and audit fields
- Target-game pregame context
- The observed full-PPR target
- Prior-game player features
- Prior-game snap and usage features
- Prior-game opponent-strength features
- History and source-availability flags
- The chronological target-row split

It must not contain unshifted same-game player statistics, same-game snap values, or final game outcomes as predictors.

## SQL build order

The SQL implementation will be stored in:

sql/06_create_model_features.sql

The build order will be:

1. Confirm the active database.
2. Remove only the three feature-layer tables if they already exist.
3. Build player_game_history.
4. Reconcile its row count and grain with player_weeks.
5. Build opponent_position_week_history.
6. Calculate lagged and rolling player features.
7. Calculate lagged and rolling opponent features.
8. Build model_player_weeks.
9. Reconcile final targets, keys, splits, and row counts.

A separate read-only audit will be stored in:

sql/07_validate_model_features.sql

## Required validation controls

The feature layer must pass all of the following before modeling.

### Row retention and grain

- player_game_history contains exactly 45,693 rows.
- model_player_weeks contains exactly 45,693 rows.
- season + week + player_id has zero duplicate groups.
- Required player, game, team, opponent, position, and split values are available.

### Target reconciliation

- Every target equals the corresponding player_weeks.fantasy_points_ppr.
- Target mismatch rows equal zero.
- Missing target rows equal zero.
- Calculated full-PPR reconciliation remains exact.

### Join safety

- Schedule joins do not lose or multiply player rows.
- Snap joins do not multiply player rows.
- Opponent-history joins do not multiply player rows.
- Join-availability rates are reported by season and position.

### Temporal safety

- No lag feature comes from the target game.
- No rolling window includes the target row.
- Previous-game dates are earlier than target-game dates.
- Prior-season history may support a later season, but later-season history may never support an earlier target.
- Opponent features exclude the target week.
- Same-week snap, injury, and depth values are absent from model predictors.
- Validation and test targets are never used to fit earlier models.

### Range and missingness controls

- History counts are nonnegative.
- Availability flags contain only zero or one.
- Percentage features remain within documented source tolerances.
- Ratio features contain no infinite values.
- Null rates are summarized by season and position.
- Unexpected missingness changes are investigated before modeling.

### Boundary spot checks

The validation must trace individual examples for:

- A player’s first observed game
- A player with at least five prior games
- A week after a bye
- A player changing teams
- A week-1 row using earlier-season history
- A 2024 validation row
- A 2025 test row
- A player without a matched snap record

## Deferred features

The following are deferred until their sources and timing rules are independently validated:

- Same-week injury status
- Same-week practice participation
- Same-week depth-chart rank
- Red-zone opportunities
- Play-by-play usage
- Weather values
- External expert rankings
- Betting-line movement
- News and coaching reports

Deferring a feature means it is unavailable in Version 1. It must not be approximated with future or weakly timed information.