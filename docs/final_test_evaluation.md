# Final 2025 Test Evaluation

## Technical summary

The frozen position_champion model passed its one-time evaluation on the
reserved 2025 test season.

Across 6,037 QB, RB, WR, and TE player-week observations, the champion achieved
a 4.4470 MAE versus 4.6177 for the selected rolling five-game baseline. This is
a 0.1708-point, or 3.70%, reduction in average absolute prediction error.

The champion also improved overall RMSE, Spearman rank correlation, mean weekly
Spearman correlation, and mean top-N overlap. It produced lower MAE and RMSE
and higher Spearman correlation at every position.

The result closely matched validation performance: champion MAE changed from
4.4580 on the 2024 validation season to 4.4470 on the 2025 test season.

The frozen model specification was not changed or reselected after the test
results were opened.

## The frozen model beat the baseline overall

Metric                       Position champion    Rolling five-game baseline                 Difference
━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━
Rows                                     6,037                         6,037                          0
───────────────────────────  ───────────────────  ────────────────────────────  ─────────────────────────
MAE                                     4.4470                        4.6177                    -0.1708
───────────────────────────  ───────────────────  ────────────────────────────  ─────────────────────────
RMSE                                    6.0605                        6.4469                    -0.3863
───────────────────────────  ───────────────────  ────────────────────────────  ─────────────────────────
Spearman rank correlation               0.6813                        0.6393                    +0.0420
───────────────────────────  ───────────────────  ────────────────────────────  ─────────────────────────
Mean weekly Spearman                    0.6182                        0.5650                    +0.0532
───────────────────────────  ───────────────────  ────────────────────────────  ─────────────────────────
Mean top-N overlap                      51.22%                        49.88%    +1.33 percentage points

Lower MAE and RMSE indicate smaller fantasy-point prediction errors. Higher
Spearman correlation indicates better ordering of players by expected fantasy
performance. Top-N overlap measures how often the predicted top players matched
the actual top players within each weekly position group.

The champion outperformed the baseline on every reported overall metric.

## Error and ranking improved at every position

Position    Champion MAE    Baseline MAE    MAE improvement    Champion RMSE    Baseline RMSE    Champion Spearman    Baseline Spearman
━━━━━━━━━━  ━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━
QB                6.6610          7.1302             0.4692           8.2023           8.8960               0.5099               0.3986
──────────  ──────────────  ──────────────  ─────────────────  ───────────────  ───────────────  ───────────────────  ───────────────────
RB                4.5163          4.5843             0.0680           6.1709           6.5200               0.7242               0.6831
──────────  ──────────────  ──────────────  ─────────────────  ───────────────  ───────────────  ───────────────────  ───────────────────
WR                4.2682          4.4259             0.1577           5.8139           6.1435               0.6501               0.6168
──────────  ──────────────  ──────────────  ─────────────────  ───────────────  ───────────────  ───────────────────  ───────────────────
TE                3.5687          3.7367             0.1680           5.0031           5.3355               0.6118               0.5700

The largest MAE improvement occurred at quarterback. Running back produced the
smallest MAE improvement, but its RMSE and ranking correlation still improved.

The results support retaining the frozen position-specific model mapping for
Version 1. They do not justify changing any individual position model after
examining the test season.

## Weekly performance was broadly consistent

The champion produced lower MAE than the baseline in 53 of the 72 evaluated
position-week groups.

Position    Weeks with lower champion MAE    Evaluated weeks    Win rate
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━  ━━━━━━━━━━
QB                                     14                 18      77.78%
──────────  ───────────────────────────────  ─────────────────  ──────────
RB                                     12                 18      66.67%
──────────  ───────────────────────────────  ─────────────────  ──────────
WR                                     13                 18      72.22%
──────────  ───────────────────────────────  ─────────────────  ──────────
TE                                     14                 18      77.78%
──────────  ───────────────────────────────  ─────────────────  ──────────
Overall                                53                 72      73.61%

This consistency matters because the overall improvement was not produced by
only one position or one isolated week.

Weekly wins are descriptive comparisons. Position-week results are not
independent observations, so the win rate should not be interpreted as a formal
probability that the champion will win in a future week.

## Top-N performance had one position-level exception

Position    Champion top-N overlap    Baseline top-N overlap                 Difference
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━
QB                          49.07%                    46.30%    +2.78 percentage points
──────────  ────────────────────────  ────────────────────────  ─────────────────────────
RB                          63.43%                    61.34%    +2.08 percentage points
──────────  ────────────────────────  ────────────────────────  ─────────────────────────
WR                          46.06%                    47.92%    -1.85 percentage points
──────────  ────────────────────────  ────────────────────────  ─────────────────────────
TE                          46.30%                    43.98%    +2.31 percentage points

Top-N overlap improved for QB, RB, and TE but declined for WR. The WR champion
still improved MAE, RMSE, and Spearman correlation, so the exception is specific
to the weekly top-player cutoff rather than general WR prediction quality.

For lineup-ranking decisions, this WR limitation should remain visible rather
than being hidden by the positive aggregate result.

## Test performance remained close to validation

Model                         2024 validation MAE    2025 test MAE    Test minus validation
━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━
Position champion                          4.4580           4.4470                  -0.0110
────────────────────────────  ─────────────────────  ───────────────  ───────────────────────
Rolling five-game baseline                 4.6813           4.6177                  -0.0636

The champion’s test MAE was only 0.0110 points lower than its validation MAE.
This stability reduces concern that the selected validation result was an
isolated one-season improvement.

Spearman correlation declined modestly from 0.6933 on validation to 0.6813 on
test, but it remained above the test baseline value of 0.6393.

This is evidence of out-of-sample predictive stability across the two seasons.
It is not evidence that the same performance is guaranteed in later NFL
seasons.

## Evaluation scope and definitions

The evaluation population contains:

- Season: 2025
- Split: test
- Rows: 6,037 player-weeks
- Positions: QB, RB, WR, and TE
- Weeks: 1 through 18
- Grain: one row per season, week, and player
- Scoring: configured full-PPR fantasy points
- Missing targets: zero
- Missing predictions: zero
- Duplicate player-week keys: zero

The weekly starter cutoffs used for top-N overlap were:

Position    Weekly cutoff
━━━━━━━━━━  ━━━━━━━━━━━━━━━
QB                     12
──────────  ───────────────
RB                     24
──────────  ───────────────
WR                     24
──────────  ───────────────
TE                     12

The comparison baseline was the frozen rolling five-game baseline. It used the
rolling five-game prediction for 5,914 test rows and a development-only position
mean fallback for 123 rows without sufficient raw baseline history.

## Frozen model specification

The position-specific champion was selected using the 2024 validation season
before any 2025 model performance was examined.

Position    Frozen algorithm
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QB          Histogram gradient boosting
──────────  ─────────────────────────────
RB          Random forest
──────────  ─────────────────────────────
WR          Ridge regression
──────────  ─────────────────────────────
TE          Ridge regression

The final pipelines were refitted on the combined development population:

- Training split: 2018-2023
- Validation split: 2024
- Development rows: 39,656
- Test split: 2025
- Test rows: 6,037

Preprocessing and model fitting used only the 2018-2024 development rows. The
refitted pipelines then generated predictions for the untouched 2025
evaluation rows.

## One-time protocol controls passed

The final workflow verified the following before opening the test split:

- Protocol commit: 5d4bc9e
- Model-selection commit: d47de6a
- The selection commit was an ancestor of the protocol commit.
- The working tree was clean.
- No final-test output files already existed.
- The explicit confirmation token was supplied.
- The configured position mapping matched the frozen mapping.
- Model reselection was disabled.

After evaluation, the workflow confirmed:

- 6,037 complete test predictions
- Zero duplicate prediction keys
- Zero missing or infinite predictions
- Ten expected summary metric rows
- 144 expected weekly metric rows
- One expected comparison row
- Twenty expected manifest rows
- No model reselection
- Locked no-overwrite output files

## Independent reconciliation

The saved predictions were independently reopened and checked after the run.

The independent controls confirmed:

- 6,037 rows and 6,037 distinct player-week keys
- Zero missing targets
- Zero missing model or baseline predictions
- All 18 expected weeks
- All four expected positions
- Recomputed MAE, RMSE, and Spearman values consistent with the saved metrics
- All output row counts consistent with the protocol
- Configuration SHA-256 matched the run manifest
- Evaluation-script SHA-256 matched the run manifest
- Input-Parquet SHA-256 matched the run manifest

Small differences beyond the displayed metric precision reflect rounding in the
summary CSV rather than calculation disagreement.

## Evidence artifacts

The one-time evaluation produced:

- results/tables/final_test_predictions.csv
- results/tables/final_test_metrics.csv
- results/tables/final_test_weekly_metrics.csv
- results/tables/final_test_vs_baseline.csv
- results/tables/final_test_run_manifest.csv

The frozen procedure is documented in:

- docs/final_test_protocol.md
- scripts/evaluate_final_test.py
- config/model_settings.toml

The run manifest records the protocol commit, selection commit, frozen model
mapping, development and test populations, headline metrics, completion status,
and hashes of the configuration, script, and input dataset.

## Limitations and uncertainty

The findings should be interpreted with the following limitations:

1. The final test contains one NFL season. Season-specific injuries, role
    changes, player turnover, schedules, and league conditions may affect
    generalization.

2. Player-week and position-week observations are correlated. The reported
    comparisons are descriptive and do not constitute independent statistical
    trials.

3. No formal confidence interval or hypothesis test was included in the frozen
    final protocol.

4. WR top-N overlap declined even though WR error and overall ranking metrics
    improved.

5. The evaluation covers only QB, RB, WR, and TE under the configured full-PPR
    rules.

6. Predictive performance does not establish that any individual feature
    causes fantasy performance.

7. The test season must not be reused as an untouched selection set for later
    model changes.

These limitations do not invalidate the observed result, but they define how
strongly it can be generalized.

## Version 1 decision

The position_champion is accepted as the Version 1 projection model.

The evidence supporting this decision is:

- It was selected before test evaluation.
- It beat the frozen baseline on every overall test metric.
- It improved error and rank correlation at every position.
- It achieved lower weekly MAE in 53 of 72 position-week groups.
- Its test MAE closely matched its validation MAE.
- All frozen-protocol and artifact-integrity controls passed.

The model should now move into the advisor workflow without further tuning
against the 2025 test outcomes.

## Recommended next steps

1. Commit the final-test outputs and this report as immutable Version 1
    evidence.

2. Preserve the frozen position mapping and test results without rerunning or
    overwriting them.

3. Build the projection-serving workflow that applies the Version 1 pipelines
    to future weekly feature rows.

4. Add uncertainty estimates using development-only methodology.
5. Translate projections into draft, start/sit, FLEX, matchup, and waiver-wire
    decision outputs.

6. Treat any later model changes as Version 2 with a new chronological
    evaluation design.

## Further questions

Future work can investigate:

- How prediction uncertainty should be communicated for lineup decisions
- Whether early-season and low-history players need a separate treatment
- How to monitor drift as new seasons are added
- How projected points should be converted into position and FLEX rankings
- How injuries and depth-chart changes should affect recommendation confidence

These questions are future development tasks. They do not change the frozen
Version 1 test conclusion.