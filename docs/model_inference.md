# Version 1 Model Inference

## Status

The target-free inference workflow, controlled historical smoke test, and first
live 2026 Week 1 inference run are complete.

The smoke test ran from inference commit `967d88b` on the 6,037 frozen 2025 test
rows. All position and overall reconciliation checks passed with zero prediction
or source-model mismatches. The maximum absolute prediction difference was
`7.105427357601002e-15`, below the configured `1e-10` tolerance.

The run excluded the target from the inference frame, performed no model fitting
or model reselection, and did not recalculate evaluation metrics. Its tracked
sample, verification table, and run manifest preserve the reviewable evidence.

The live run scored all 808 rows in the frozen 2026 Week 1 future-feature
snapshot from inference commit `10d4a68`. It produced one finite prediction per
input row with no duplicate or unavailable keys. The target was absent, and the
workflow performed no fitting or model reselection. The tracked live manifest
preserves the input hash, prediction hash, bundle lineage, position routing,
package contract, and run controls.

## Purpose

This workflow loads the frozen Version 1 position-specific model bundle and generates full-PPR fantasy-point projections without fitting models, selecting
models, or loading the target column.

It supports:

1. A controlled historical smoke test against the committed 2025 predictions.
2. General batch inference from a target-free Parquet or CSV feature file.

The smoke test validates inference plumbing and prediction reproducibility. It does not recalculate test metrics or perform another model evaluation.

## Frozen model specification

Position    Frozen algorithm
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QB          Histogram gradient boosting
──────────  ─────────────────────────────
RB          Random forest
──────────  ─────────────────────────────
WR          Ridge regression
──────────  ─────────────────────────────
TE          Ridge regression

The frozen bundle version is v1_evaluated_2025.

The models were fitted on the combined training and validation splits covering the 2018-2024 seasons. Model selection was completed before the 2025 test
split was opened.

Inference does not permit model reselection.

## Lineage controls

The inference configuration freezes the following lineage:

Item                             Value
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bundle protocol commit           9f8f72b
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Bundle evidence commit           11730dc
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Bundle manifest SHA-256          f9b222521a7bd04bca879537ebe80432fe1ea29bfebeaf74e2a90cabf92d6ce9
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Bundle verification SHA-256      a4478a73a94d47f9928aafddcf9fe2edb99995bfaa9908cc2522af67eb7772c5
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Bundle metadata SHA-256          96c8d238c16bf2d1e34a7059273243480b083464bd8a07725abacb9e4be9ad31
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Smoke-test model data SHA-256    6733ff26d86b8966d0c3aa76c592c2f41b35e555433c99738ccb4c01b42f3fe3
───────────────────────────────  ──────────────────────────────────────────────────────────────────
Reference predictions SHA-256    b371778f5dc51963292d97e0fe977b9353540f13170e48874b84310e3843f1c4

The workflow verifies these hashes before using the corresponding files.

## Artifact trust boundary

Joblib model files use Python pickle-based serialization. Loading an untrusted artifact can execute malicious code.

The inference workflow therefore:

1. Verifies the committed bundle manifest and verification evidence.
2. Verifies the bundle metadata hash.
3. Verifies each model artifact against its recorded SHA-256 hash.
4. Loads the model artifact only after its hash passes.
5. Rejects missing, unexpected, or altered artifacts.

Only locally built artifacts from the validated v1_evaluated_2025 bundle should be loaded.

## Target-free input contract

Inference requires:

- Nine metadata columns.
- Six categorical predictor columns.
- Ninety-six numeric predictor columns.
- Exactly 102 predictor features in total.

Required metadata columns:

- season
- week
- game_id
- game_date
- player_id
- player_display_name
- position
- team
- opponent

The authoritative predictor list comes from config/model_settings.toml.

The target column target_fantasy_points_ppr is not part of the inference contract and is not loaded into the inference frame.

For the historical Parquet smoke test, the source file contains the historical target, but the reader selects only the permitted metadata and predictor
columns. The target is therefore excluded before prediction.

Supported input formats are:

- Parquet
- CSV

Supported positions are:

- QB
- RB
- WR
- TE

## Input quality controls

Before prediction, the workflow requires:

- All configured metadata and predictor columns are present.
- No unexpected predictor contract changes exist.
- The predictor count equals 102.
- Key columns contain no unavailable values.
- Player-week keys contain no duplicates.
- Positions are restricted to QB, RB, WR, and TE.
- Numeric predictors contain no infinite values.
- Model artifacts exist and match their recorded hashes.
- Bundle metadata matches the current package and feature contracts.
- The output path does not already exist.

The player-week key is:

season, week, player_id

Missing feature values are allowed when the saved preprocessing pipeline was designed to handle them.

## Position routing

Each row is routed using its position value:

QB -> hist_gradient_boosting
RB -> random_forest
WR -> ridge
TE -> ridge

The output records the selected algorithm in projection_source_model.

The prediction column is projected_fantasy_points_ppr.

Input row order is preserved.

## Historical smoke-test mode

The smoke test reads the 2025 test rows from:

data/processed/modeling/model_player_weeks.parquet

Expected smoke-test rows:

6,037

The workflow makes target-free predictions and reconciles them against the already committed frozen predictions in:

results/tables/final_test_predictions.csv

Reference column:

prediction_position_champion

Reference source-model column:

position_champion_source_model

The reconciliation tolerance is:

0.0000000001

The smoke test does not:

- Fit any model.
- Select or tune any model.
- Load the target column.
- Recalculate MAE, RMSE, rank correlation, or other test metrics.
- Change the frozen position-to-model mapping.

## Smoke-test outputs

A successful smoke test writes:

Output                                                                  Purpose                                       Git treatment
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━
data/processed/inference/v1_evaluated_2025_smoke_predictions.parquet    Complete 6,037-row inference output           Ignored generated artifact
──────────────────────────────────────────────────────────────────────  ────────────────────────────────────────────  ────────────────────────────
data/sample/model_inference_smoke_sample.csv                            Reviewable 500-row sample                     Tracked
──────────────────────────────────────────────────────────────────────  ────────────────────────────────────────────  ────────────────────────────
results/tables/model_inference_smoke_verification.csv                   Position and overall reproduction evidence    Tracked
──────────────────────────────────────────────────────────────────────  ────────────────────────────────────────────  ────────────────────────────
results/tables/model_inference_smoke_manifest.csv                       Run lineage and quality controls              Tracked

Existing outputs are never overwritten.

If an expected output already exists, the workflow stops so that previous evidence cannot be silently replaced.

## Smoke-test acceptance criteria

The smoke test passes only when:

- Exactly 6,037 test rows are processed.
- All player-week keys are available and unique.
- All positions use their frozen source model.
- Every row receives a finite prediction.
- No prediction differs from the committed reference beyond the configured tolerance.
- Reopened output files match the in-memory results.
- No target column was loaded.
- No model fitting or model selection occurred.
- All lineage and artifact hashes pass.

Observed final controls:

bundle_hash_validation=PASS
artifact_hash_validation=PASS
target_free_input_contract=PASS
prediction_completeness=PASS
smoke_reference_reconciliation=PASS
model_fitting_performed=False
model_reselection_performed=False
inference_status=PASS

## Smoke-test command and rerun guard

The completed smoke test was run only after the inference protocol had been
committed and `git status --short` was empty:

python scripts\predict_with_bundle.py --smoke-test --confirm-inference RUN_V1_BUNDLE_INFERENCE

Because output replacement is disabled and the completed evidence now exists,
do not rerun the smoke test. A rerun requires a separately justified protocol
and new non-conflicting output paths; prior evidence must not be replaced.

## General batch-inference mode

A future target-free Parquet input can be scored with:

python scripts\predict_with_bundle.py --input path\to\future_features.parquet --output path\to\future_predictions.parquet --confirm-inference
RUN_V1_BUNDLE_INFERENCE

A CSV input is also supported:

python scripts\predict_with_bundle.py --input path\to\future_features.csv --output path\to\future_predictions.csv --confirm-inference
RUN_V1_BUNDLE_INFERENCE

An optional `--manifest-output` may place the run manifest in a separate tracked
evidence directory. It does not change the prediction path supplied through
`--output`.

An optional split can be selected with:

--data-split SPLIT_NAME

A custom run-manifest path can be supplied with:

--manifest-output path\to\inference_manifest.csv

The requested prediction and manifest output paths must not already exist.

## Observed live 2026 Week 1 run

The completed live run used the feature snapshot documented in
`docs/future_feature_preparation.md`:

```powershell
.\.venv\Scripts\python.exe scripts\predict_with_bundle.py `
  --input data\processed\future_features\2026_week_01_features.parquet `
  --output data\processed\inference\2026_week_01_projections.parquet `
  --manifest-output results\tables\inference_2026_week_01_manifest.csv `
  --confirm-inference RUN_V1_BUNDLE_INFERENCE
```

Observed controls:

```text
input_rows=808
output_rows=808
position_rows=QB:110,RB:179,WR:344,TE:175
missing_predictions=0
infinite_predictions=0
duplicate_keys=0
unavailable_keys=0
source_contains_target_column=False
target_column_loaded=False
model_fitting_performed=False
model_reselection_performed=False
input_sha256=f88aac8b6e29e445728c5004e8a3263839b0c1443ae8a9d45d15a08e78cfb207
predictions_sha256=6dceb7908c51aec3666ba89eed8a7f5c2b5c4a1bd3bec855d11e2dc30d0c2802
inference_status=PASS
```

The complete 808-row Parquet output is generated and Git-ignored. Its tracked
manifest is:

```text
results/tables/inference_2026_week_01_manifest.csv
```

A distribution reasonableness check found three negative TE projections. The
affected players had 1,001 to 2,079 days since their last recorded game; the TE
ridge model extrapolated that feature downward. The raw inference output remains
unchanged so the saved-model result is auditable. A downstream ranking or user
display must flag these out-of-range cases and may floor their displayed points
at zero without replacing the raw prediction.

This is a structural and reasonableness validation, not an accuracy evaluation:
2026 Week 1 outcomes are not yet available.

## Interpretation

The projection is the model’s estimate of configured full-PPR fantasy points for the supplied player-week context.

The projection is not a guarantee of performance. It may be affected by injuries, depth-chart changes, weather, coaching decisions, role changes, late
inactive announcements, and other information not represented in the input features.

## Current limitation

The historical smoke test proves saved-artifact reproduction, while the live run
proves the feature-to-prediction path works on a frozen future-week snapshot.
Neither proves future forecast accuracy.

The current candidate set is intentionally broad. It includes active-roster,
depth-matched QB, RB, WR, and TE players, including backups and players with
little or stale history. Production recommendations must still incorporate
current role, injury, availability, and confidence controls, then distinguish
raw projections from display-adjusted ranking values.
