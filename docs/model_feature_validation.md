# Model Feature Validation Report

## Technical summary

The Version 1 modeling dataset is ready for export and baseline modeling.

The final model_player_weeks table contains 45,693 player-week observations at the intended grain of one row per season, week, and player. It reconciles
exactly with the clean player_weeks source table and contains 116 columns.

All tested row-count, grain, target, split, range, missingness, history, opponent, and temporal-leakage controls passed. Eight individual boundary cases
also passed.

This result means the feature table is structurally ready for predictive modeling. It does not mean a trained model has been evaluated or is ready for
production use.

## Final readiness evidence

- Expected model rows: 45,693 - PASS
- Actual model rows: 45,693 - PASS
- Distinct season-week-player keys: 45,693 - PASS
- Expected columns: 116 - PASS
- Actual columns: 116 - PASS
- Model rows without a source row: 0 - PASS
- Source rows missing from the model table: 0 - PASS
- Target mismatches: 0 - PASS
- Missing required values: 0 - PASS
- Invalid domain rows: 0 - PASS
- History-integrity failures: 0 - PASS
- Player-feature leakage rows: 0 - PASS
- Opponent-feature leakage rows: 0 - PASS
- Invalid range or context rows: 0 - PASS
- Forbidden same-game columns: 0 - PASS
- Boundary cases passed: 8 of 8 - PASS
- Final readiness result: `READY_FOR_MODEL_EXPORT` - PASS

## Chronological modeling splits

The dataset uses chronological splits rather than random row sampling.

- Training: 2018-2023, 33,792 rows, used to fit models and preprocessing.
- Validation: 2024, 5,864 rows, used to select features and model settings.
- Test: 2025, 6,037 rows, reserved for final untouched evaluation.
- Total: 2018-2025, 45,693 labeled player-week rows.

The 2024 validation and 2025 test targets must not be used to fit training-period models.

## Prediction target and row population

The supervised-learning target is the player’s full-PPR fantasy score for the game represented by the row:

target_fantasy_points_ppr

The initial population contains regular-season QB, RB, WR, and TE player-weeks appearing in the weekly player-statistics source.

This population is appropriate for historical model development, but it is not yet a future-week candidate list. A separate prediction-time process must
identify eligible players from upcoming schedules and active rosters.

## Leakage-safe feature alignment

Every predictor is aligned to information from games completed before the target game.

Player-history features include:

- Previous-game fantasy production
- Rolling three-game and five-game production
- Season-to-date production
- Passing, rushing, receiving, and opportunity volume
- Usage-share measures
- Offensive snap participation
- Position-specific efficiency measures
- Previous-team and rest context

Opponent features include:

- Previous-game PPR allowed by position
- Rolling three-game and five-game PPR allowed
- Season-to-date PPR allowed
- Opportunities allowed
- Passing, rushing, and receiving production allowed
- Offensive touchdowns allowed

Pregame context includes:

- Home or away status
- Team and opponent rest
- Point spread
- Game total
- Stadium roof
- Playing surface
- Temperature and wind when published

Same-game player statistics, snap counts, outcomes, injuries, and depth-chart results are not included as predictors.

## Temporal validation results

The validation queries confirmed:

- No previous-game date is equal to or later than its target-game date.
- No same-season prior week is equal to or later than its target week.
- No player rolling window includes the target game.
- No opponent rolling window includes the target game.
- First observed games do not contain prior-game or rolling features.
- First games of a season do not contain same-season history.
- Prior-season history may support a later season.
- Future-season history never supports an earlier target.
- Team changes preserve the player’s chronological history and identify the change.
- Missing prior snap records remain missing rather than being replaced with fabricated values.

## Boundary-case validation

Eight individual records were traced through the feature pipeline.

- First observed game: Tom Brady, 2018 Week 1 - PASS
- At least five prior games: Tom Brady, 2018 Week 6 - PASS
- Week following a team bye: Alex Smith, 2018 Week 5 - PASS
- Player changed teams: Stacy Coley, 2018 Week 3 - PASS
- Week 1 using prior-season history: Tom Brady, 2019 Week 1 - PASS
- Validation-period row: Aaron Rodgers, 2024 Week 1 - PASS
- Test-period row: Aaron Rodgers, 2025 Week 1 - PASS
- Missing previous snap record: Fred Brown, 2019 Week 5 - PASS

These checks confirm that important chronology and missing-data boundaries behave as designed.

## Feature coverage

Historical feature availability increases after the beginning of the dataset.

In 2018, previous-game coverage by position ranged from approximately 88% to 90% because no pre-2018 history was included. By 2024 and 2025, previous-game
coverage generally ranged from approximately 98% to 98.3%.

Missing snap features are retained as NULL and paired with explicit availability flags. Ratio features also remain NULL when their denominator is zero.

This treatment distinguishes unavailable information from a genuine observed value of zero.

## Target distribution observations

Average full-PPR targets declined modestly between training and the later evaluation periods.

- QB: training 14.12, validation 13.77, test 13.36
- RB: training 8.14, validation 7.74, test 7.59
- WR: training 7.72, validation 7.46, test 6.67
- TE: training 5.57, validation 5.44, test 5.60

The largest observed shift is among 2025 wide receivers:

- Average target PPR decreased from 7.72 in training to 6.67 in testing.
- Median target PPR decreased from 5.4 to 4.3.
- Zero-point outcomes increased from 19.05% to 23.42%.
- Average recent opportunities decreased from 4.44 to 3.95.
- Average previous-game offensive snap share decreased from 0.5594 to 0.5203.

This does not indicate a pipeline failure. It is a potential distribution shift that must be considered when evaluating 2025 model generalization.

## Calculation robustness

The configured full-PPR calculation reconciles to the published source target for all 45,693 rows.

The maximum observed floating-point difference was approximately:

0.0000000000000071

This is harmless floating-point noise and is far below the validation tolerance.

During feature development, MySQL exact-decimal division caused some derived efficiency values to round prematurely. Ratio calculations were changed to
use 1E0 so MySQL performs floating-point division before the final comparison. After that correction, all efficiency reconciliations returned zero
mismatches.

## Known limitations

1. The labeled population includes player-weeks appearing in weekly statistics. Future-week candidate generation is still required.
2. The target, identifiers, split labels, feature version, and audit timestamps must be excluded from the predictor matrix.
3. Same-week injury and depth-chart features remain excluded until their prediction-time availability can be guaranteed.
4. Missing historical snap records remain NULL and require preprocessing during modeling.
5. The first modeled season has lower history coverage because pre-2018 data is unavailable.
6. The 2025 WR distribution differs from the training period and requires explicit test-set evaluation.
7. Future projections will represent predictive associations, not causal effects.

## Reproducibility

The feature layer is built by:

sql/06_create_model_features.sql

The independent read-only validation is performed by:

sql/07_validate_model_features.sql

The complete validation script was executed successfully from beginning to end after the final feature build.

## Recommended next steps

1. Export the model-ready table from MySQL.
2. Create an explicit predictor allowlist that excludes labels, identifiers, and audit fields.
3. Build a simple rolling-average baseline.
4. Build a regularized linear or tree-based baseline model.
5. Fit preprocessing only on the 2018–2023 training data.
6. Select model settings using only the 2024 validation data.
7. Evaluate the final selected model once on the untouched 2025 test data.
8. Report MAE, RMSE, rank correlation, and performance by position.

## Further questions

- Should separate models be trained for QB, RB, WR, and TE?
- How much does each feature family improve performance over the rolling-average baseline?
- Does recent opportunity volume outperform recent fantasy scoring?
- How stable is performance across early-season and late-season weeks?
- How much does the 2025 WR distribution shift reduce predictive accuracy?
- Which additional injury or depth-chart sources can be made safely available before kickoff?