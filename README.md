# NFL Fantasy Football Advisor

A SQL and Python portfolio project that analyzes NFL player performance and produces transparent, data-supported recommendations for season-long fantasy
football.

The first version targets a default 12-team, full-PPR redraft league. A later phase will reuse the player projections for daily fantasy sports analysis.

## Project status

Work in progress. Project setup, source inspection, historical extraction, MySQL
staging, clean analytical tables, full-PPR reconciliation, leakage-safe feature
engineering, model-data export, baseline evaluation, and validation-only trained
model selection are complete.

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

The one-time 2025 final-test protocol is prepared but has not been executed.
The selected position-specific specification is frozen at commit `d47de6a`. It
will be refitted using the 2018-2024 development data and evaluated once on the
2025 test season without model reselection or output overwriting.

The execution safeguards, expected controls, output contract, and interpretation
rules are documented in [the final-test protocol](docs/final_test_protocol.md).

The trained candidate definitions, position-level selection rules, validation
results, safeguards, and remaining limitations are documented in
[the trained-model evaluation report](docs/model_training_evaluation.md).

## Decisions supported

The completed advisor will help a fantasy manager decide:

- Which players to target during a preseason snake draft
- Which players to start or sit each week
- Which RB, WR, or TE should fill the FLEX position
- Which available players are promising waiver-wire candidates
- Which players have favorable or unfavorable matchups
- Why one player is recommended over another

See the complete project brief (docs/project_brief.md).

The leakage-safe feature definitions and timing rules are documented in [the feature-engineering specification](docs/feature_engineering.md).

See [model feature validation](docs/model_feature_validation.md) for the completed evidence, limitations, and readiness decision.

The model configuration, export artifacts, and reproducibility controls are documented in [the model export guide](docs/model_export.md).

The baseline definitions, validation results, selection decision, and limitations
are documented in [the baseline evaluation report](docs/baseline_evaluation.md).

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

Kicker and defense projections will follow the validated QB, RB, WR, and TE workflow.

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
- The selected specification is frozen at commit `d47de6a`; the 2025 test workflow requires an explicit confirmation token, a clean working tree, and
absent final outputs.
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
- Git and GitHub

## Project structure

- `config/`: League, scoring, and future model settings
- `data/raw/`: Original downloaded source data
- `data/cache/`: Local nflreadpy download cache
- `data/processed/`: Cleaned and feature-ready data
- `data/sample/`: Small GitHub-safe samples
- `docs/`: Project brief, source profile, methodology, and findings
- `models/`: Local trained model artifacts
- `notebooks/`: Reproducible exploration and model experiments
- `results/tables/`: Validated analytical outputs
- `results/figures/`: Decision-relevant charts
- `scripts/`: Extraction, validation, modeling, and export scripts
- `sql/`: MySQL schema, transformations, audits, and analysis
- `tests/`: Automated calculation and data-quality tests

## Local setup

From PowerShell in the repository root:

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env

Open .env and replace the placeholder MySQL credentials with local values. Never commit the real .env file.

## Important limitations

Fantasy projections are uncertain and are not guarantees. Injuries, coaching decisions, weather, trades, and changing player roles can make historical
trends less useful.

The advisor will support decisions but will not automatically manage a roster. The later DFS phase will not promise profits or eliminate financial risk.