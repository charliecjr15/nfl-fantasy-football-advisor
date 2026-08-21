# Baseline Fantasy-Point Evaluation

## Purpose

This evaluation establishes the minimum performance that future trained models
must exceed.

The baselines predict weekly full-PPR fantasy points for quarterbacks, running
backs, wide receivers, and tight ends. They are benchmarks, not final fantasy
recommendations.

## Chronological data boundary

| Split | Seasons | Rows | Use |
|---|---:|---:|---|
| Training | 2018-2023 | 33,792 | Calculate training-only reference values |
| Validation | 2024 | 5,864 | Compare baselines and select the benchmark |
| Test | 2025 | 6,037 | Reserved for final evaluation |

The evaluator loaded no test rows and calculated no test metrics.

The analytical grain is one row per season, week, and player.

## Evaluated baselines

### Training position mean

Predicts the average training-period fantasy score for the player's position.

This provides a simple context-free benchmark.

### Previous game

Uses the player's fantasy points from their most recent prior game.

When unavailable, it falls back to the training position mean.

### Rolling three games

Uses the player's mean fantasy points from their three most recent games.

Its fallback sequence is:

1. Rolling three-game average
2. Previous game
3. Training position mean

### Rolling five games

Uses the player's mean fantasy points from their five most recent games.

Its fallback sequence is:

1. Rolling five-game average
2. Rolling three-game average
3. Previous game
4. Training position mean

All history features were calculated strictly from games occurring before the
predicted game.

## Evaluation metrics

- MAE: Mean absolute prediction error in full-PPR points. Lower is better.
- RMSE: Root mean squared error, which penalizes large misses more heavily.
Lower is better.

- Spearman rank correlation: Measures how well predictions preserve player
ordering. Higher is better.

- Mean weekly Spearman: Average ranking correlation within weekly position
groups. Higher is better.

- Top-N overlap: Percentage of actual top players also selected by the
baseline. The weekly cutoffs are QB12, RB24, WR24, and TE12.

## Overall validation results

| Baseline | Rows | Raw coverage | Fallback rows | MAE | RMSE | Spearman | Mean weekly Spearman | Top-N overlap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rolling five games | 5,864 | 98.00% | 117 | 4.6813 | 6.4654 | 0.6489 | 0.5827 | 52.95% |
| Rolling three games | 5,864 | 98.00% | 117 | 4.7804 | 6.6623 | 0.6392 | 0.5720 | 51.50% |
| Previous game | 5,864 | 98.00% | 117 | 5.5544 | 7.8848 | 0.5692 | 0.4960 | 45.37% |
| Training position mean | 5,864 | 100.00% | 0 | 6.1495 | 7.7329 | 0.2064 | Not applicable | 26.50% |

The training position mean produces the same prediction for players at the same
position. Therefore, within-position weekly rank correlation is not defined.

## Leading rolling-baseline comparison by position

| Position | Baseline | MAE | RMSE | Spearman | Top-N overlap |
|---|---|---:|---:|---:|---:|
| QB | Rolling three games | 6.5141 | 8.3691 | 0.4906 | 53.24% |
| QB | Rolling five games | 6.5560 | 8.3133 | 0.4695 | 53.70% |
| RB | Rolling three games | 4.6385 | 6.4746 | 0.6726 | 62.50% |
| RB | Rolling five games | 4.5618 | 6.2852 | 0.6798 | 62.73% |
| WR | Rolling three games | 4.8863 | 6.8635 | 0.6077 | 44.44% |
| WR | Rolling five games | 4.7521 | 6.6369 | 0.6173 | 45.37% |
| TE | Rolling three games | 3.8061 | 5.3031 | 0.5278 | 45.83% |
| TE | Rolling five games | 3.6722 | 5.0374 | 0.5605 | 50.00% |

Rolling three games has slightly better QB MAE and rank correlation. Rolling
five games has better QB RMSE and top-12 overlap and performs better for RB,
WR, and TE.

## Weekly stability

The validation period contains 72 position-week groups: 18 weeks multiplied by
four positions.

There were no ties for the lowest weekly MAE.

| Baseline | Position-week groups won |
|---|---:|
| Rolling five games | 51 |
| Rolling three games | 18 |
| Training position mean | 2 |
| Previous game | 1 |

Rolling five games won 70.83% of the position-week comparisons.

## Baseline selection

`rolling_5_game` is the selected primary baseline.

It produced the best overall MAE, RMSE, global rank correlation, mean weekly
rank correlation, and top-N overlap. It also won most weekly comparisons and
led the rolling-three baseline for three of the four positions.

Future trained models must be compared against this baseline on the validation
split before the test split is opened.

## Validation controls

The completed evaluation confirmed:

- 33,792 training rows
- 5,864 validation rows
- Zero test rows loaded or evaluated
- Zero duplicate training or validation keys
- Zero missing targets
- Complete predictions for every baseline
- 5,864 exported validation predictions
- 20 exported summary metric rows
- 288 exported weekly metric rows
- Selected primary baseline matched the validation leader

The evaluation returned:

```text
development_data_quality=PASS
validation_predictions_complete=PASS
test_split_untouched=PASS
baseline_evaluation_status=PASS
```

## Reproduction

Run the evaluation from the project root:

```powershell
python scripts\evaluate_baselines.py
```

The script reads:

```text
config/model_settings.toml
data/processed/modeling/model_player_weeks.parquet
```

It writes:

```text
results/tables/baseline_validation_predictions.csv
results/tables/baseline_validation_metrics.csv
results/tables/baseline_validation_weekly_metrics.csv
```

## Limitations

- These results measure predictive performance on the 2024 validation season.
- The 2025 test results remain unknown.
- A baseline does not account for every injury, depth-chart, coaching, weather,
or roster change.

- Ranking correlation and starter overlap do not guarantee correct individual
start/sit decisions.

- The evaluation is predictive and descriptive, not causal.
- Selecting rolling five games on validation means it must not be reselected
after observing the final test results.