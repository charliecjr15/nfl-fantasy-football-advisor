# Historical Data Extraction and Validation

## Technical summary

The historical extraction pipeline successfully produced modeling-ready source tables for the 2018–2025 NFL seasons.

The pipeline created 48 Parquet partitions across six analytical datasets. All expected files were present and readable, partition row counts matched the
extraction manifest, duplicate analytical keys were eliminated, and configured full-PPR scoring reconciled with zero mismatches.

Schedule and roster join coverage reached 100% in every season. Snap-count coverage ranged from 99.77% to 100%, exceeding the configured 98% minimum.

These outputs are validated historical inputs. They are not yet final model features or fantasy projections.

## Scope and definitions

The extraction is controlled by ../config/data_settings.toml.

Setting                   Definition
━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━
Seasons                   2018–2025
────────────────────────  ─────────────────────────
Season type               Regular season
────────────────────────  ─────────────────────────
Core fantasy positions    QB, RB, WR, and TE
────────────────────────  ─────────────────────────
Prediction target         Full-PPR fantasy points
────────────────────────  ─────────────────────────
Prediction horizon        One week ahead
────────────────────────  ─────────────────────────
Training seasons          2018–2023
────────────────────────  ─────────────────────────
Validation season         2024
────────────────────────  ─────────────────────────
Test season               2025
────────────────────────  ─────────────────────────
Random splits             Disabled
────────────────────────  ─────────────────────────
Future features           Prohibited

The chronological split preserves the order in which information would have become available. This prevents future seasons from leaking into training
data.

## Extracted datasets

The pipeline processes six season-level analytical datasets.

Dataset                     Analytical grain                                   Processed rows
━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━
Weekly player statistics    One core fantasy player per regular-season week            45,693
──────────────────────────  ─────────────────────────────────────────────────  ────────────────
Schedules                   One regular-season game                                     2,127
──────────────────────────  ─────────────────────────────────────────────────  ────────────────
Weekly rosters              One player-team-week roster record                        362,959
──────────────────────────  ─────────────────────────────────────────────────  ────────────────
Injuries                    One player-team-week injury record                         43,561
──────────────────────────  ─────────────────────────────────────────────────  ────────────────
Depth charts                Source-format-aware player depth records                  796,273
──────────────────────────  ─────────────────────────────────────────────────  ────────────────
Snap counts                 One player-game snap record                               196,130

The totals should not be added together as a single analytical row count because the datasets represent different grains.

The nflverse player identity table is also loaded as a supporting lookup. It supplies the GSIS-to-PFR identifier bridge used to connect weekly statistics,
rosters, and snap counts. It does not create a separate season partition.

## Validation results

Every season passed the configured extraction controls.

Season    Core player-week rows    Schedule match    Roster match    Snap match    PPR mismatches
━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━  ━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━
    2018                    5,363           100.00%         100.00%       100.00%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2019                    5,411           100.00%         100.00%        99.89%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2020                    5,543           100.00%         100.00%       100.00%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2021                    5,866           100.00%         100.00%        99.90%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2022                    5,808           100.00%         100.00%        99.98%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2023                    5,801           100.00%         100.00%        99.90%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2024                    5,864           100.00%         100.00%        99.90%                 0
────────  ───────────────────────  ────────────────  ──────────────  ────────────  ────────────────
    2025                    6,037           100.00%         100.00%        99.77%                 0

The lowest observed snap-count match rate was 99.77%, which remained above the required 98% threshold.

Tables are used instead of charts here because the purpose is exact pipeline verification rather than trend interpretation.

## Final pipeline controls

The completed extraction produced the following audit results:

Control                                Result
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━
Expected season-dataset partitions         48
────────────────────────────────────  ─────────
Manifest records                           48
────────────────────────────────────  ─────────
Parquet files                              48
────────────────────────────────────  ─────────
Missing or unreadable files                 0
────────────────────────────────────  ─────────
Manifest row-count differences              0
────────────────────────────────────  ─────────
Duplicate manifest keys                     0
────────────────────────────────────  ─────────
Duplicate analytical key groups             0
────────────────────────────────────  ─────────
Full-PPR scoring mismatches                 0
────────────────────────────────────  ─────────
Minimum schedule match rate           100.00%
────────────────────────────────────  ─────────
Minimum roster match rate             100.00%
────────────────────────────────────  ─────────
Minimum snap-count match rate          99.77%
────────────────────────────────────  ─────────
CSV sample rows per dataset               500

These controls establish that the historical partitions are structurally consistent and suitable for the next feature-engineering stage.

## Source compatibility decisions

### Injury schema differences

Older injury files do not always contain season_type. The pipeline treats that field as optional and uses game_type as the consistent regular-season
filter.

When multiple injury records exist for the same player, team, and week, the pipeline retains the latest record using date_modified. This resolved two
repeated 2024 injury groups without arbitrarily selecting a row.

An injury record represents the latest weekly source observation. Feature engineering must still enforce an as-of cutoff so information published after a
fantasy decision cannot leak into a historical prediction.

### Depth-chart schema change

The depth-chart source uses two materially different formats:

- The 2018–2024 data is a legacy weekly format.
- The 2025 data uses timestamped depth-chart snapshots.

The pipeline preserves a depth_source_format indicator and the fields appropriate to each format. It does not invent timestamps for legacy weekly records.

The much larger 2025 depth-chart row count reflects the more granular timestamped feed, not a comparable increase in players. Future feature engineering
must use format-aware joins and select only the latest depth information available before each game.

### Team abbreviation normalization

Historical team abbreviations are normalized before joins. For example, OAK is converted to LV so franchise relocation does not create false unmatched
records.

### Player identity mapping

GSIS identifiers are the primary player keys. PFR identifiers are attached through the nflverse player identity table for snap-count joins.

The weekly roster PFR identifier remains available as a fallback. The pipeline also records the source of each mapping and flags conflicts instead of
silently overwriting them.

### Multi-team roster weeks

The 2019 roster data contains 13 player-week groups with records for more than one team. These records are retained because player-team-week remains the
valid roster grain.

Multi-team weeks must not be collapsed to player-week without a documented team-selection rule.

### Missing snap-count matches

A small number of player-week rows do not match a snap-count record. Because coverage remains above the configured threshold, these rows are retained.

Snap-derived model features must include a missingness indicator rather than treating an unavailable snap percentage as zero.

## Full-PPR scoring reconciliation

The extraction recalculates fantasy points using the configured full-PPR scoring rules and compares the result with the source fantasy_points_ppr value.

Across all 45,693 core player-week rows:

- Rows outside the 0.01-point tolerance: 0
- Maximum observed difference: 0.00 points

This confirms that the project’s configured offensive scoring logic matches the source for the extracted historical data.

## Generated outputs

Processed Parquet files follow this structure:

data/processed/historical/<dataset>/<dataset>_<season>.parquet

Examples:

```text
data/processed/historical/weekly_player_stats/weekly_player_stats_2025.parquet
data/processed/historical/schedules/schedules_2025.parquet
data/processed/historical/weekly_rosters/weekly_rosters_2025.parquet

The extraction also creates tracked CSV samples and a manifest in data/sample/:

data/sample/weekly_player_stats_sample.csv
data/sample/schedules_sample.csv
data/sample/weekly_rosters_sample.csv
data/sample/injuries_sample.csv
data/sample/depth_charts_sample.csv
data/sample/snap_counts_sample.csv
data/sample/historical_extraction_manifest.csv

The manifest records the season, data split, source rows, processed rows, unavailable keys, duplicate controls, join coverage, scoring reconciliation, and
output path for every partition.

## Reproducing the extraction

From the project root, activate the virtual environment and run:

.\.venv\Scripts\Activate.ps1
python scripts\extract_history.py

The extraction settings can be changed in ../config/data_settings.toml. The implementation is located in ../scripts/extract_history.py.

Additional source inspection and validation decisions are documented in docs/source_profile.md (source_profile.md).

## Limitations and modeling safeguards

The extracted data is historical and descriptive. It does not yet constitute a forecasting model or establish that any feature causes future fantasy
performance.

The next stage must address the following risks:

- Rolling features must use only weeks before the prediction week.
- Injury information must be limited to what was available at the prediction cutoff.
- Depth-chart joins must follow the correct source-format rule.
- Missing snap-count data must remain distinguishable from a true zero.
- Bye weeks and games missed because of injury must not be interpreted as ordinary zero-point performances.
- Training, validation, and test seasons must remain chronologically separated.
- Model evaluation must be compared with simple baselines, not only reported in isolation.

## Recommended next steps

1. Build a unified player-week modeling table at one row per player and prediction week.
2. Create lagged and rolling features using prior weeks only.
3. Add opponent, usage, roster, injury, depth-chart, and snap-count context.
4. Create explicit availability and missingness indicators.
5. Establish simple historical-average baselines.
6. Train models using 2018–2023.
7. Tune model choices using 2024 only.
8. Perform the final untouched evaluation on 2025.

## Further questions

The modeling stage should determine:

- How many prior weeks provide the strongest signal for each position?
- Should QB, RB, WR, and TE use separate models?
- How should early-season projections incorporate prior-season history?
- How should traded players and multi-team weeks be represented?
- How much predictive value do injuries, depth position, and snap share add beyond recent fantasy production?
- Which evaluation measures best reflect useful draft and weekly lineup decisions?