# NFL Fantasy Football Advisor

A SQL and Python portfolio project that analyzes NFL player performance and produces transparent, data-supported recommendations for season-long fantasy
football.

The first version targets a default 12-team, full-PPR redraft league. A later phase will reuse the player projections for daily fantasy sports analysis.

## Project status

Work in progress. The project brief, default league configuration, Python environment, dependency versions, and repository safeguards are complete.
Source-data profiling and extraction are next.

## Decisions supported

The completed advisor will help a fantasy manager decide:

- Which players to target during a preseason snake draft
- Which players to start or sit each week
- Which RB, WR, or TE should fill the FLEX position
- Which available players are promising waiver-wire candidates
- Which players have favorable or unfavorable matchups
- Why one player is recommended over another

See the complete project brief (docs/project_brief.md).

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

The primary source will be nflverse data (https://github.com/nflverse/nflverse-data), accessed with the maintained nflreadpy
(https://github.com/nflverse/nflreadpy) Python package.

Source files, update dates, seasons, row counts, licenses, and availability limitations will be documented before analysis begins.

Large raw and processed files are excluded from Git. Small reproducible samples and final analytical outputs may be included when appropriate.

## Methodology safeguards

- The primary historical grain is one row per season + week + player.
- Weekly features may use only information available before the predicted game.
- Future-week information must not leak into training or backtesting.
- Model evaluation will use chronological validation rather than random row splits.
- Every projection model will be compared with a simple rolling-average baseline.
- Missing values will not automatically be treated as zero.
- Projections will include uncertainty and plain-language explanations.
- Recommendations will be tailored to the documented league settings.

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

Path                Purpose
━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
config/             League, scoring, and future model settings
──────────────────  ──────────────────────────────────────────────────────────
data/raw/           Original downloaded source data
──────────────────  ──────────────────────────────────────────────────────────
data/cache/         Local nflreadpy download cache
──────────────────  ──────────────────────────────────────────────────────────
data/processed/     Cleaned and feature-ready data
──────────────────  ──────────────────────────────────────────────────────────
data/sample/        Small GitHub-safe samples
──────────────────  ──────────────────────────────────────────────────────────
docs/               Project brief, source profile, methodology, and findings
──────────────────  ──────────────────────────────────────────────────────────
models/             Local trained model artifacts
──────────────────  ──────────────────────────────────────────────────────────
notebooks/          Reproducible exploration and model experiments
──────────────────  ──────────────────────────────────────────────────────────
results/tables/     Validated analytical outputs
──────────────────  ──────────────────────────────────────────────────────────
results/figures/    Decision-relevant charts
──────────────────  ──────────────────────────────────────────────────────────
scripts/            Extraction, validation, modeling, and export scripts
──────────────────  ──────────────────────────────────────────────────────────
sql/                MySQL schema, transformations, audits, and analysis
──────────────────  ──────────────────────────────────────────────────────────
tests/              Automated calculation and data-quality tests

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