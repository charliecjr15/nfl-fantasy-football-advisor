# Version 1 Evaluated Model Bundle

## Status

The Version 1 model-bundle procedure is prepared but has not yet been executed.

The bundle must be committed as a reproducible protocol before its confirmation
token is supplied.

## Purpose

This bundle packages the exact position-specific model specification that was
evaluated on the reserved 2025 test season.

The bundle is intended to:

- Recreate the frozen 2018-2024 development fit
- Reproduce the committed 2025 position-champion predictions
- Save one reusable preprocessing-and-model pipeline per position
- Record artifact hashes, package versions, feature names, and lineage
- Provide a stable starting point for the weekly inference workflow

It does not perform model selection, hyperparameter tuning, feature selection,
or another test evaluation.

## Evaluated bundle versus future production refit

The evaluated Version 1 bundle fits on:

Split         Seasons      Use
━━━━━━━━━━━━  ━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Training      2018-2023    Development fitting
────────────  ───────────  ───────────────────────────────────────────
Validation    2024         Development fitting after model selection
────────────  ───────────  ───────────────────────────────────────────
Test          2025         Prediction reproduction only

The 2025 target is not used for fitting. The bundle script does not recalculate
test metrics or select another model. It only verifies that newly generated
predictions match the predictions already committed by the one-time final-test
workflow.

A future production model may refit the same specification using all completed
seasons, including 2025. That will be a separately named production artifact.
It cannot claim a new independent 2025 test result because 2025 would then be
part of its fitting data.

## Frozen model mapping

Position    Algorithm
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QB          Histogram gradient boosting
──────────  ─────────────────────────────
RB          Random forest
──────────  ─────────────────────────────
WR          Ridge regression
──────────  ─────────────────────────────
TE          Ridge regression

The bundle script must reject any configuration that changes this mapping.

## Frozen lineage

The bundle is connected to three earlier Git checkpoints:

Checkpoint             Commit     Purpose
━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Model selection        d47de6a    Frozen position-level selection
─────────────────────  ─────────  ────────────────────────────────────────
Final-test protocol    5d4bc9e    One-time evaluation rules
─────────────────────  ─────────  ────────────────────────────────────────
Final-test evidence    cff6832    Committed 2025 predictions and metrics

All three commits must be ancestors of the bundle-build commit.

## Frozen input files

The bundle uses:

- config/model_settings.toml
- data/processed/modeling/model_player_weeks.parquet
- results/tables/final_test_predictions.csv
- results/tables/final_test_run_manifest.csv

The configured SHA-256 value for each input must match before model data are
used.

This is especially important for config/model_settings.toml. It must not be
modified for the bundle workflow because its exact hash is part of the
committed final-test evidence.

Bundle-specific settings are stored separately in:

- config/model_bundle_settings.toml

## Build safeguards

The script requires all of the following before fitting begins:

1. The explicit confirmation token BUILD_V1_EVALUATED_BUNDLE
2. A clean Git working tree
3. The selection, test-protocol, and test-evidence commits in Git history
4. Exact hashes for all four frozen inputs
5. The original frozen position mapping
6. Exactly 102 configured predictor features
7. Exactly 39,656 development rows
8. Exactly 6,037 verification rows
9. No existing artifact directory
10. No existing bundle manifest or verification output
11. No stale temporary bundle directory

The script must refuse to overwrite an existing Version 1 bundle.

## Reproduction method

For each position, the script will:

1. Select the frozen algorithm.
2. Rebuild its preprocessing and estimator pipeline.
3. Fit the pipeline using only the 2018-2024 development rows.
4. Generate predictions for the 2025 verification predictors.
5. Align the predictions to the committed player-week keys.
6. Compare them with the committed final-test predictions.
7. Require every absolute difference to be no greater than 1e-10.
8. Save the fitted pipeline to a temporary artifact directory.
9. Reload the saved pipeline.
10. Generate the verification predictions again.
11. Require the reloaded predictions to pass the same tolerance.
12. Record the artifact SHA-256 hash and row counts.

Only after all four position pipelines pass may the temporary directory become
the final bundle directory.

## Expected model artifacts

The local bundle directory will be:

models/v1_evaluated_2025/

It will contain:

- `qb_pipeline.joblib`
- `rb_pipeline.joblib`
- `wr_pipeline.joblib`
- `te_pipeline.joblib`
- `bundle_metadata.json`

Each `.joblib` file contains the fitted preprocessing and estimator pipeline
for one position.

The metadata file records:

- Bundle name and version
- Build timestamp
- Source commits
- Fit and verification splits
- Model mapping
- Predictor names
- Predictor count
- Target name
- Source hashes
- Artifact hashes
- Development and verification row counts
- Python and package versions
- Prediction-reproduction differences
- Fit and verification timing

## Tracked verification evidence

The bundle build will create two Git-trackable CSV files:

- `results/tables/model_bundle_manifest.csv`
- `results/tables/model_bundle_verification.csv`

The manifest is expected to contain four rows, one for each position artifact.

The verification file is expected to contain five rows:

- QB
- RB
- WR
- TE
- Overall

Every row must report:

- Zero committed-prediction mismatches
- Zero reloaded-artifact mismatches
- A maximum absolute difference within the configured tolerance
- A `PASS` status

## Why binary model files remain local

The repository intentionally ignores `.joblib`, `.pkl`, `.pickle`, and other
binary model formats.

The fitted pipelines remain local because:

- Binary artifacts can be large.
- They are tied to specific Python and library versions.
- They are not meaningfully reviewable in a Git diff.
- They can be rebuilt from the committed configuration, scripts, data contract,
and evidence.
- Loading an untrusted pickle-compatible artifact can execute malicious code.

Only locally generated artifacts should be loaded. Their SHA-256 values should
be verified against the bundle manifest before inference.

The small metadata, manifest, verification, documentation, and build code are
the durable Git evidence.

## Reproducibility boundary

Fixed random seeds and frozen package versions support deterministic
reproduction. The expected prediction values must match on the current
environment within the configured tolerance.

Exact binary file hashes may differ if the artifact is rebuilt with a different
Python, scikit-learn, NumPy, pandas, or joblib version. A rebuild in a changed
environment must therefore be treated as a new artifact-build event and must
still pass prediction reconciliation.

The bundle does not guarantee indefinite cross-version deserialization.
Environment versions are recorded so the evaluated artifact can be recreated.

## Authorized build command

Only after the bundle configuration, script, dependency declaration, this
document, and the model-directory README have been committed with a clean
working tree, run:

```text
python scripts\build_model_bundle.py --confirm-build BUILD_V1_EVALUATED_BUNDLE

The command should be run once for this local Version 1 bundle.

## Expected completion controls

A successful run must finish with:

frozen_input_hashes=PASS
development_refit_quality=PASS
committed_prediction_reproduction=PASS
artifact_reload_quality=PASS
model_reselection_performed=False
test_metrics_recalculated=False
model_bundle_status=PASS

The final bundle is acceptable only if every control passes.

## Next boundary

After the evaluated bundle is saved and validated, the next task is building an
inference contract for new player-week feature rows.

That workflow must:

- Require the same 102 predictors
- Route each player to the correct position pipeline
- Reject unsupported positions
- Preserve player-week identifiers
- Produce complete finite predictions
- Verify artifact hashes before loading
- Avoid depending on target values at prediction time
- Keep any future all-data production refit separate from this evaluated bundle