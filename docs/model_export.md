# Model Dataset Export

## Purpose

The model export converts the validated MySQL `model_player_weeks` table into a local Parquet dataset for Python modeling.

The export is controlled by `config/model_settings.toml` and executed by `scripts/export_model_data.py`.

## Source

- Database: `nfl_fantasy_advisor`
- Source table: `model_player_weeks`
- Feature version: `v1_prior_game`
- Grain: one row per season, week, and player
- Positions: QB, RB, WR, and TE
- Target: `target_fantasy_points_ppr`

Database credentials are loaded from the local `.env` file and are never written to exported artifacts.

## Modeling contract

The configuration defines:

- 13 metadata-only columns
- 6 categorical predictors
- 96 numeric predictors
- 102 total predictors
- 1 supervised-learning target
- 116 total source columns

The predictor allowlist has no overlap with the forbidden-column list.

The export fails if the live MySQL schema differs from the configured 116-column contract.

## Chronological splits

- Training: 2018-2023, 33,792 rows
- Validation: 2024, 5,864 rows
- Test: 2025, 6,037 rows
- Total: 45,693 rows

Random train-test splitting is prohibited.

Preprocessing and model fitting must use only training data. Model selection may use validation data. The test period remains untouched until final
evaluation.

## Export command

From the repository root with the virtual environment active:

```powershell
python scripts\export_model_data.py

## Exported artifacts

### Full Parquet dataset

Path:

data/processed/modeling/model_player_weeks.parquet

Observed export:

- 45,693 rows
- 116 columns
- Approximately 7.86 MB
- Snappy-compressed Parquet
- Deterministically ordered by season, week, and player ID

The full Parquet file is excluded from Git because it is a generated artifact.

### GitHub-safe sample

Path:

data/sample/model_player_weeks_model_sample.csv

The sample contains 500 rows and all 116 columns.

It is deterministically stratified across:

- Training QB, RB, WR, and TE
- Validation QB, RB, WR, and TE
- Test QB, RB, WR, and TE

Each split-position group contributes either 41 or 42 rows.

### Export manifest

Path:

data/sample/model_export_manifest.csv

The manifest contains one row for each split-position group, for a total of 12 rows.

It records:

- Export timestamp
- Source database and table
- Feature version
- Parquet path
- Source-column count
- Predictor count
- Split and position
- Minimum and maximum season
- Row count
- Distinct player count
- Missing target count
- Average target PPR

## Blocking quality controls

The exporter stops before writing artifacts if any of these controls fail:

- Live schema differs from the configured schema
- Row count differs from 45,693
- Column count differs from 116
- Duplicate season-week-player keys exist
- Required key values are unavailable
- Target values are missing
- Split counts differ from configuration
- A season appears in the wrong chronological split
- Feature versions differ from v1_prior_game
- A configured numeric feature has a nonnumeric type
- Infinite numeric values are present
- A forbidden column appears in the predictor allowlist

## Observed export validation

The successful export returned:

- Schema contract: PASS
- Model rows: 45,693
- Model columns: 116
- Duplicate key groups: 0
- Unavailable key rows: 0
- Missing target rows: 0
- Split mismatch rows: 0
- Invalid feature-version rows: 0
- Nonnumeric configured features: 0
- Infinite numeric rows: 0
- Export status: PASS

## Independent artifact reconciliation

The written Parquet and CSV files were reopened after export.

Observed results:

- Parquet rows: 45,693
- Parquet columns: 116
- Parquet duplicate keys: 0
- Parquet missing targets: 0
- Sample rows: 500
- Sample columns: 116
- Sample split-position groups: 12
- Manifest rows: 12
- Manifest row-count total: 45,693
- Manifest missing-target total: 0
- Artifact reconciliation: PASS

## Modeling safeguards

The following columns remain in the exported dataset for identification, auditing, or evaluation but must not enter the predictor matrix:

- Target
- Season
- Game and player identifiers
- Player names
- Game date
- Split label
- Feature version
- Previous-game identifiers and dates
- Audit timestamp

Modeling code must select predictors from the configuration allowlist rather than dropping a small number of known columns from the full dataframe.

## Known limitations

- The labeled dataset includes players appearing in weekly statistics and is not yet an upcoming-week candidate list.
- Missing historical features remain NULL and require training-only preprocessing.
- Same-week injury and depth-chart information remains excluded.
- The 2018 rows have less historical coverage because pre-2018 data is unavailable.
- The 2025 WR distribution differs from the training period and requires explicit test evaluation.
- The local Parquet file must be regenerated after rebuilding the MySQL feature table.