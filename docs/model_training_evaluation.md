# Trained Fantasy-Point Model Evaluation

## Purpose

This evaluation compares trained fantasy-point projection models against the
selected rolling five-game baseline.

The goal is to select a validation champion for QB, RB, WR, and TE projections
without using the reserved 2025 test season.

These results support model development. They are not final test results or
production-readiness evidence.

## Chronological data boundary

| Split | Seasons | Rows | Use |
|---|---:|---:|---|
| Training | 2018-2023 | 33,792 | Fit preprocessing and candidate models |
| Validation | 2024 | 5,864 | Compare candidates and select position winners |
| Test | 2025 | 6,037 | Reserved for one final evaluation |

The training script loaded only training and validation rows. It loaded and
evaluated zero test rows.

## Modeling population

The model predicts one-game-ahead full-PPR fantasy points for:

- Quarterbacks
- Running backs
- Wide receivers
- Tight ends

The analytical grain is one row per season, week, and player.

The labeled population contains players appearing in the historical weekly
statistics source. A separate future-week candidate-generation process is still
required before the model can produce live weekly recommendations.

## Predictor contract

Each candidate uses the same 102 leakage-safe predictors:

- 6 categorical features
- 96 numeric features

Categorical features are imputed with the most frequent training value and
one-hot encoded.

Numeric features are imputed with training medians. Missingness indicators are
preserved. Numeric features are standardized for Ridge regression.

Every preprocessing pipeline is fitted independently on training data for its
position. Validation values do not influence imputation, encoding, scaling, or
model fitting.

## Candidate models

### Ridge regression

Ridge provides a regularized linear model and an interpretable trained
benchmark.

Configured alpha: 10.0.

### Random forest

Random forest captures nonlinear relationships and interactions through an
ensemble of decision trees.

Configured controls include:

- 300 trees
- Minimum leaf size of 5
- 70% feature sampling
- Random seed 42

### Histogram gradient boosting

Histogram gradient boosting builds sequential nonlinear trees that correct
earlier prediction errors.

Configured controls include:

- Learning rate of 0.05
- 300 boosting iterations
- 31 maximum leaf nodes
- Minimum leaf size of 20
- L2 regularization of 1.0
- Random seed 42
- Random internal early stopping disabled

## Position-specific training

Each algorithm fits a separate pipeline for QB, RB, WR, and TE.

The validation champion combines the best eligible algorithm for each position.
This allows different positions to use different statistical relationships
while retaining one auditable projection column.

## Selection rule

The primary selection metric is MAE, with RMSE as the tiebreaker.

A candidate must also satisfy these guardrails relative to the rolling
five-game baseline for its position:

- MAE cannot be worse than the baseline
- Spearman correlation cannot decline by more than 0.01
- Mean top-N overlap cannot decline by more than 2 percentage points

The composite is named `position_champion`.

## Selected position models

| Position | Selected algorithm | Candidate MAE | Baseline MAE | MAE improvement | Spearman | Top-N overlap |
|---|---|---:|---:|---:|---:|---:|
| QB | Histogram gradient boosting | 6.1046 | 6.5560 | 0.4514 | 0.5353 | 52.31% |
| RB | Random forest | 4.3717 | 4.5618 | 0.1902 | 0.7181 | 65.05% |
| WR | Ridge | 4.5586 | 4.7521 | 0.1935 | 0.6529 | 46.76% |
| TE | Ridge | 3.4713 | 3.6722 | 0.2009 | 0.6159 | 51.39% |

Random forest produced the lowest QB MAE, but its QB top-12 overlap was 2.31
percentage points below the baseline. That exceeded the configured two-point
decline limit. Histogram gradient boosting was therefore the lowest-MAE
eligible QB candidate.

## Overall validation results

| Model | MAE | RMSE | Spearman | Mean weekly Spearman | Mean top-N overlap |
|---|---:|---:|---:|---:|---:|
| Position champion | 4.4580 | 6.1075 | 0.6933 | 0.6263 | 53.88% |
| Ridge | 4.4813 | 6.1562 | 0.6862 | 0.6295 | 54.40% |
| Random forest | 4.5175 | 6.0939 | 0.6942 | 0.6289 | 53.07% |
| Histogram gradient boosting | 4.5465 | 6.2000 | 0.6840 | 0.6164 | 52.26% |
| Rolling five-game baseline | 4.6813 | 6.4654 | 0.6489 | 0.5828 | 52.95% |

The position champion has the best overall MAE, which is the configured primary
selection metric.

Random forest has a slightly better overall RMSE and Spearman correlation.
Ridge has a slightly better mean weekly Spearman and top-N overlap. The
position champion provides the best configured balance after applying the
position-level guardrails.

## Improvement over baseline

Compared with the rolling five-game baseline, the position champion produced:

| Measure | Improvement |
|---|---:|
| MAE | 0.2234 points lower |
| MAE percentage | 4.77% lower |
| RMSE | 0.3579 points lower |
| RMSE percentage | 5.54% lower |
| Spearman correlation | 0.0443 higher |
| Mean top-N overlap | 0.93 percentage points higher |

The position champion had lower MAE than the baseline in 57 of 72
position-week groups.

Its average signed validation error was approximately zero, indicating little
overall directional bias. This does not mean individual player projections are
unbiased or consistently accurate.

## Validation controls

The completed run confirmed:

- 33,792 training rows
- 5,864 validation rows
- Zero test rows loaded or evaluated
- Zero duplicate training or validation keys
- Zero unavailable keys
- Zero missing targets
- 102 configured predictors present
- All numeric predictors had numeric dtypes
- Complete predictions for every candidate
- Complete position-champion predictions
- Complete source-model labels
- 25 summary metric rows
- 360 weekly metric rows
- 4 overall comparison rows
- 12 position-selection rows
- Zero duplicated result-table keys
- Written CSV files reopened successfully

The evaluation returned:

- `development_data_quality=PASS`
- `validation_predictions_complete=PASS`
- `position_selection_quality=PASS`
- `metric_output_quality=PASS`
- `test_split_untouched=PASS`
- `trained_model_evaluation_status=PASS`

## Reproduction

From the project root, run:

`python scripts\train_models.py`

The script reads:

- `config/model_settings.toml`
- `data/processed/modeling/model_player_weeks.parquet`
- `results/tables/baseline_validation_predictions.csv`

It writes:

- `results/tables/model_validation_predictions.csv`
- `results/tables/model_validation_metrics.csv`
- `results/tables/model_validation_weekly_metrics.csv`
- `results/tables/model_vs_baseline_comparison.csv`
- `results/tables/model_position_selection.csv`

## Interpretation

The trained features add useful predictive information beyond recent fantasy
points alone.

The improvement is meaningful but modest, which is realistic for noisy weekly
fantasy outcomes. No model eliminates uncertainty from touchdowns, injuries,
coaching decisions, game scripts, weather, or unexpected role changes.

The validation champion should be treated as a ranking and decision-support
input rather than a guarantee of player performance.

## Limitations and remaining work

- All reported trained-model metrics come from the 2024 validation season.
- The 2025 test results remain unknown.
- The position-composite design was finalized after reviewing position-level
validation performance. This makes the validation result a development
estimate that may be optimistic.
- The test season must be evaluated only once after the model specification is
frozen.
- The current labeled population is conditional on appearing in historical
weekly statistics.
- A future-week player candidate table is still required.
- Injury, depth-chart, and roster information must be joined using a defined
pregame cutoff.
- Prediction intervals or another uncertainty estimate are still required.
- Model explanations and recommendation rules are not yet implemented.
- These results are predictive and descriptive, not causal.