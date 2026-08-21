# Final 2025 Test Evaluation Protocol

## Purpose

This document freezes the procedure for the one-time evaluation of the selected
NFL fantasy projection model on the reserved 2025 test season.

The test results will measure how the already-selected model generalizes to a
future season. They will not be used to select another algorithm, change
features, tune hyperparameters, or revise the evaluation rules.

## Frozen model selection

The model specification was selected using the 2024 validation season and
committed before final-test evaluation.

- Selection commit: d47de6a
- Selected model: position_champion
- Selection metric: validation MAE
- Selected baseline: rolling five-game average

The position-specific champion mapping is frozen as follows:

Position    Selected algorithm
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QB          Histogram gradient boosting
──────────  ─────────────────────────────
RB          Random forest
──────────  ─────────────────────────────
WR          Ridge regression
──────────  ─────────────────────────────
TE          Ridge regression

The final-evaluation script must verify that selection commit d47de6a is an
ancestor of the current Git commit.

## Chronological boundary

Purpose                                            Seasons      Split
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━  ━━━━━━━━━━━━
Initial model fitting and selection development    2018-2023    Training
─────────────────────────────────────────────────  ───────────  ────────────
Model selection                                    2024         Validation
─────────────────────────────────────────────────  ───────────  ────────────
Final evaluation                                   2025         Test

For final evaluation, the frozen position-specific pipelines will be refitted
using the combined 2018-2024 development data. Preprocessing will also be
refitted using only those development rows.

The refitted models will then generate predictions for the 2025 test rows.

## Test-data status before evaluation

The 2025 source data have already been ingested and subjected to structural,
grain, join, scoring, feature-timing, and missingness controls.

However, 2025 target outcomes have not been used to:

- Select candidate algorithms
- Select the position champions
- Tune model hyperparameters
- Choose the baseline
- Compare model performance
- Revise the final-test procedure

Structural validation of the test rows is not the same as examining their model
performance.

## One-time execution safeguards

The final evaluation requires all of the following:

1. The configuration must name position_champion.
2. The frozen position-to-algorithm mapping must match this document.
3. The development fit splits must be training and validation.
4. The evaluation split must be test.
5. The normal training workflow must continue to prohibit test evaluation.
6. The final workflow must explicitly permit test evaluation.
7. Selection commit d47de6a must be an ancestor of the current commit.
8. The Git working tree must be clean.
9. None of the final-test output files may already exist.
10. The explicit confirmation token FINAL_TEST_2025 must be supplied.

Existing final-test outputs must never be overwritten by the script.

## Expected evaluation population

The expected test population is:

- Season: 2025
- Rows: 6,037 player-weeks
- Positions: QB, RB, WR, and TE
- Weeks: 1 through 18
- Required grain: one row per season, week, and player
- Missing prediction targets allowed: zero
- Duplicate prediction keys allowed: zero

## Evaluation metrics

The frozen model and rolling five-game baseline will be evaluated using:

- Mean absolute error
- Root mean squared error
- Spearman rank correlation
- Mean weekly Spearman rank correlation
- Mean weekly top-N overlap

Metrics will be reported overall and by position. Weekly metrics will also be
written for each position and week.

Expected output sizes are:

Artifact                            Expected rows
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━
Final predictions                           6,037
──────────────────────────────────  ───────────────
Summary metrics                                10
──────────────────────────────────  ───────────────
Weekly metrics                                144
──────────────────────────────────  ───────────────
Model-versus-baseline comparison                1
──────────────────────────────────  ───────────────
Run manifest                                   20

## Output artifacts

The one-time run will create:

- results/tables/final_test_predictions.csv
- results/tables/final_test_metrics.csv
- results/tables/final_test_weekly_metrics.csv
- results/tables/final_test_vs_baseline.csv
- results/tables/final_test_run_manifest.csv

The run manifest will record the relevant Git commits, frozen configuration,
position mapping, row counts, and hashes of the configuration, evaluation
script, and input modeling dataset.

## Interpretation rule

The 2025 results are an honest final estimate for the frozen modeling approach.

Regardless of whether performance is better or worse than validation:

- No candidate model will be reselected.
- No position champion will be replaced.
- No feature will be added or removed based on the test results.
- No hyperparameter will be changed based on the test results.
- No test row will be moved into development and evaluated again as test data.

Any later modeling improvement must be labeled as a new model version with a
new chronological evaluation design.

## Known limitations

The final metrics describe predictive performance on one NFL season. They do
not establish causal effects and may be sensitive to season-specific injuries,
role changes, schedule conditions, player turnover, and changes in league
environment.

The evaluation covers only QB, RB, WR, and TE player-week projections under the
configured full-PPR scoring rules.

## Authorized execution command

Only after this protocol, the configuration, the evaluation script, and the
README update have been committed with a clean working tree, run:

    python scripts\evaluate_final_test.py --confirm-final-test FINAL_TEST_2025

This command is intended to be executed once.

After saving, run only:

git diff --check
git status --short

Expected status at this checkpoint:

M config/model_settings.toml
?? docs/final_test_protocol.md
?? scripts/evaluate_final_test.py