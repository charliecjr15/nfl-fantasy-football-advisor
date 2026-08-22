# NFL Fantasy Football Advisor

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://sunday-edge-fantasy-advisor.streamlit.app/)

[Launch the live Sunday Edge Fantasy Advisor](https://sunday-edge-fantasy-advisor.streamlit.app/)

A SQL and Python portfolio project that analyzes NFL player performance and produces transparent, data-supported recommendations for season-long fantasy
football.

The first version targets a default 12-team, full-PPR redraft league. A later phase will reuse the player projections for daily fantasy sports analysis.

## Project status

Work in progress. The Version 1 historical data pipeline, MySQL staging layer,
clean analytical tables, leakage-safe feature engineering, model-data export,
baseline evaluation, validation-only model selection, one-time final test
evaluation, reproducible evaluated model bundle, and target-free historical
inference smoke test are complete. A leakage-safe future-week feature builder is
implemented, documented, and validated by a controlled historical parity
replay. The first live 2026 Week 1 target-free feature snapshot is also complete
and validated. The frozen Version 1 bundle has scored that snapshot, producing
the first live 2026 Week 1 projections. A protected position and FLEX ranking
workflow, portable weekly history refresh, one-command scoring orchestrator,
publication gate, Streamlit application, and scheduled GitHub Actions workflow
are now implemented. The repository, verified model release, configured weekly
GitHub Actions workflow, and public Streamlit deployment are live. The first
cloud workflow completed successfully on August 22, 2026.

The Version 1 model dataset contains 45,693 player-week observations, 116
columns, and a strict 102-feature predictor allowlist. Its schema, chronological
splits, keys, targets, feature timing, missingness, and written artifacts passed
the documented validation controls.

The rolling five-game benchmark produced a 4.6813 MAE on the 2024 validation
season. Ridge regression, random forest, and histogram gradient boosting were
then fitted separately for QB, RB, WR, and TE using only 2018-2023 training
data.

The selected `position_champion` combines histogram gradient boosting for QB,
random forest for RB, and Ridge for WR and TE. It achieved a 4.4580 validation
MAE, 6.1075 RMSE, 0.6933 Spearman rank correlation, and 53.88% mean top-N
overlap.


The frozen `position_champion` was refitted using the 2018-2024 development
data and evaluated once on the reserved 2025 test season. It achieved a 4.4470
MAE, 6.0605 RMSE, 0.6813 Spearman rank correlation, and 51.22% mean top-N
overlap. It outperformed the rolling five-game baseline on every reported
overall test metric, and no model reselection was performed.

The complete results, position-level findings, validation controls, and
limitations are documented in
[the final-test evaluation report](docs/final_test_evaluation.md). The frozen
execution rules remain documented in
[the final-test protocol](docs/final_test_protocol.md).

The evaluated Version 1 model bundle was built from the frozen 2018-2024
development fit and validated against all 6,037 committed 2025 predictions.
All four saved pipelines reproduced their predictions with zero mismatches and
a maximum absolute difference of `7.11e-15`. The binary artifacts remain local
and Git-ignored, while their hashes and verification results are tracked. The
artifact contract, security rules, and reproducibility evidence are documented
in [the model-bundle guide](docs/model_bundle.md).

The target-free inference workflow verifies the tracked bundle evidence and
model-artifact hashes before deserialization, loads only the permitted metadata
and 102 predictors, routes rows through the frozen position-specific models, and
prevents output replacement. Its input contract and execution modes are
documented in [the inference guide](docs/model_inference.md). The historical
smoke test reproduced all 6,037 frozen 2025 projections with zero prediction or
source-model mismatches and a maximum absolute difference of `7.11e-15`. It did
not load the target, fit models, reselect models, or recalculate test metrics.

The future-week feature builder reads only strictly earlier-week rows from the
validated player and opponent history tables, combines them with target-week
candidate and schedule context, and emits the exact frozen target-free feature
contract. Its timing rules, replay controls, live candidate policy, and current
limitations are documented in
[the future-feature preparation guide](docs/future_feature_preparation.md).
The 2025 Week 18 replay rebuilt all 350 rows and reconciled all 107 unique output
columns with zero mismatched rows and a maximum absolute numeric difference of
`7.11e-15`.

The live 2026 Week 1 snapshot was frozen at `2026-08-22 07:46:47 UTC`. It
contains 808 active-roster, depth-matched candidates across all 32 teams and 16
games. The 107-column target-free frame passed its key, timing, contract,
missingness, infinity, reopened-output, and hash controls.

The frozen position models then generated 808 live Week 1 projections: 110 QB,
179 RB, 344 WR, and 175 TE rows. The run loaded no target, fit no model,
reselected no model, produced no missing or infinite predictions, and preserved
the exact feature-input hash in its tracked manifest. Three raw TE projections
were negative because the ridge model extrapolated for players with unusually
long gaps since their last recorded game. Those raw values remain unchanged for
auditability and will be flagged and floored only in the later decision layer.

The protected weekly ranking workflow is now implemented and has completed its
first 2026 Week 1 run. It separates raw
conditional-on-appearance projections from depth-based role eligibility, applies
the documented 12-team position and FLEX demand, and preserves confidence and
availability caveats. The 808-row output contains 283 role-eligible players and
exactly 84 provisional lineup slots: 12 QB, 24 RB, 24 WR, 12 TE, and 12 FLEX.
Current 2026 injury context remains unavailable, so these are not final start/sit
calls. See [the weekly-ranking guide](docs/weekly_rankings.md).

The public application reads only the last manifest-validated snapshot. It
uses a compact layout for top projections, a manual-roster lineup optimizer,
player comparison, a dedicated RB/WR/TE FLEX list, ESPN/Yahoo kicker and D/ST
rankings, all target-week games, previous-week results, and full-season player
totals. Projection tables show only player, position, team, opponent, and
projected points. Completed outcomes are published in separate display-only
files and cannot enter target-week model inputs. The portable history path
reproduced the complete 2025 Week 18 frozen feature replay with zero text or
numeric mismatches at the `1e-10` acceptance tolerance. See
[weekly app operations](docs/weekly_operations.md) and
[D/ST methodology](docs/dst_rankings.md), and
[kicker methodology](docs/kicker_rankings.md) for local use, weekly scoring,
model-release packaging, GitHub automation, and deployment.

## Run the application

From PowerShell in the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.txt
python scripts\run_weekly_pipeline.py --season 2026 --week 1 --publish-existing
python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

## Decisions supported

The completed advisor will help a fantasy manager decide:

- Which players to target during a preseason snake draft
- Which players to start or sit each week
- Which RB, WR, or TE should fill the FLEX position
- Which kicker or D/ST to start under ESPN or Yahoo default scoring
- Which players have accumulated the most points over a completed season
- Which available players are promising waiver-wire candidates
- Which players have favorable or unfavorable matchups
- Why one player is recommended over another

See the complete project brief (docs/project_brief.md).

The leakage-safe feature definitions and timing rules are documented in [the feature-engineering specification](docs/feature_engineering.md).

See [model feature validation](docs/model_feature_validation.md) for the completed evidence, limitations, and readiness decision.

The model configuration, export artifacts, and reproducibility controls are documented in [the model export guide](docs/model_export.md).

The baseline definitions, validation results, selection decision, and limitations
are documented in [the baseline evaluation report](docs/baseline_evaluation.md).

The trained candidate definitions, position-level selection rules, validation
results, and remaining limitations are documented in
[the trained-model evaluation report](docs/model_training_evaluation.md).

## Default league

- 12 teams
- Redraft
- Snake draft
- Full PPR
- 1 QB
- 2 RB
- 2 WR
- 1 TE
- 1 FLEX
- 1 K
- 1 DST
- 6 bench positions
- 1 injured-reserve position

The machine-readable scoring and roster rules are stored in config/league_settings.toml (config/league_settings.toml).

## Version 1 scope

Version 1 will include:

1. Historical player-week statistics
2. Reproducible full-PPR fantasy-point calculations
3. Weekly roster, schedule, injury, depth-chart, and snap-count context
4. Leakage-safe rolling performance and opportunity features
5. Baseline weekly fantasy-point projections
6. Chronological backtesting
7. Position and FLEX rankings
8. Start, sit, and waiver-wire recommendation tiers
9. Preseason draft rankings
10. Exported tables, charts, and a weekly recommendation interface

Defense/Special Teams projections now support ESPN and Yahoo public default
scoring. Kicker projections remain a later extension.

## Data source

The primary source is [nflverse data](https://github.com/nflverse/nflverse-data), accessed with the maintained [nflreadpy](https://github.com/nflverse/
nflreadpy) Python package.

The validated 2025 source grains, row counts, identifier coverage, join controls, scoring reconciliation, and limitations are documented in [the source profile](docs/source_profile.md).

Large raw and processed files are excluded from Git. Small reproducible samples and final analytical outputs may be included when appropriate.

## Methodology safeguards

- The primary historical grain is one row per season + week + player.
- Weekly features may use only information available before the predicted game.
- Future-week information must not leak into training or backtesting.
- Model evaluation will use chronological validation rather than random row splits.
- Every trained projection model will be compared with the selected rolling five-game baseline.
- Missing values will not automatically be treated as zero.
- Projections will include uncertainty and plain-language explanations.
- Recommendations will be tailored to the documented league settings.
- Position-model selection uses MAE with RMSE, rank correlation, and top-N overlap guardrails.
- The selected specification was frozen at commit `d47de6a` and evaluated once under protocol commit `5d4bc9e`; the final outputs are locked against
accidental overwrite.
- The evaluated local model bundle must reproduce every committed 2025 prediction within `1e-10` before its artifacts are accepted.
- Inference verifies every evidence and model-artifact hash before calling `joblib.load()`, excludes `target_fantasy_points_ppr` from the inference frame,
and never fits or reselects a model.

## Technology

- Python 3.11
- nflreadpy
- Polars
- pandas
- PyArrow
- MySQL 8
- SQLAlchemy and PyMySQL
- scikit-learn
- Matplotlib and Seaborn
- pytest
- Streamlit
- GitHub Actions
- Git and GitHub
- joblib

## Project structure

- `config/`: League, extraction, modeling, bundle, inference, and future-feature settings
- `data/raw/`: Original downloaded source data
- `data/cache/`: Local nflreadpy download cache
- `data/processed/`: Cleaned and feature-ready data
- `data/sample/`: Small GitHub-safe samples
- `docs/`: Project brief, source profile, methodology, and findings
- `models/`: Local trained model artifacts
- `notebooks/`: Reproducible exploration and model experiments
- `results/tables/`: Validated analytical outputs
- `results/public/`: Last validated snapshot served by the application
- `results/figures/`: Decision-relevant charts
- `scripts/`: Extraction, validation, modeling, weekly automation, and export scripts
- `sql/`: MySQL schema, transformations, audits, and analysis
- `tests/`: Automated calculation and data-quality tests

## Local setup

From PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Open .env and replace the placeholder MySQL credentials with local values. Never commit the real .env file.

## Important limitations

Fantasy projections are uncertain and are not guarantees. Injuries, coaching decisions, weather, trades, and changing player roles can make historical
trends less useful.

The advisor will support decisions but will not automatically manage a roster. The later DFS phase will not promise profits or eliminate financial risk.
