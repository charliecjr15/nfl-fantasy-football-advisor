# Weekly app operations

## What is automated

The production workflow keeps the evaluated Version 1 position models frozen
and updates their inputs. It does not retrain or reselect models during the NFL
season.

One successful weekly run performs these operations in order:

1. Download completed regular-season statistics, schedules, weekly rosters, and
   snap counts through the prior week.
2. Rebuild portable player and opponent history at the exact grains required by
   the future-feature builder.
3. Download target-week schedule, roster, and depth-chart context.
4. Build the 102 target-free predictors using strict prior-week history.
5. Score the frozen position-specific model bundle.
6. Apply role eligibility plus 12-team position and FLEX demand.
7. Validate hashes, keys, coverage, predictions, and publication status.
8. Replace the public `latest` snapshot only after every required control passes.

If a stage fails, the existing public snapshot remains unchanged.

## Local app

From the project directory:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install --requirement requirements.txt
python scripts\publish_latest.py --season 2026 --week 1
python -m streamlit run app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

The app reads only:

- `results/public/latest_rankings.csv`
- `results/public/latest_run.json`

It does not connect to MySQL, load model objects, or expose credentials to a
visitor.

## Local weekly run

The full runner requires a clean committed worktree because it records that Git
revision in every controlled stage.

For an explicit target week:

```powershell
.\.venv\Scripts\python.exe scripts\run_weekly_pipeline.py `
    --season 2026 `
    --week 2 `
    --history-source-mode download
```

To resolve the target week from the live regular-season schedule:

```powershell
.\.venv\Scripts\python.exe scripts\run_weekly_pipeline.py `
    --season 2026 `
    --auto-week `
    --history-source-mode download
```

Use the existing prepared historical partitions for an offline development
check:

```powershell
.\.venv\Scripts\python.exe scripts\refresh_weekly_history.py `
    --season 2026 `
    --through-week 0 `
    --source-mode existing
```

Do not use `existing` for an automated in-season run unless the current-season
partitions were independently refreshed and validated.

## Frozen model release

The model files remain Git-ignored. Package them after validating their tracked
manifest hashes:

```powershell
.\.venv\Scripts\python.exe scripts\package_model_bundle.py
```

This creates two ignored local files:

- `dist/model_bundle_v1_evaluated_2025.zip`
- `dist/model_bundle_v1_evaluated_2025.zip.sha256`

Create a GitHub release and upload the ZIP file. In the GitHub repository,
create these Actions variables:

- `MODEL_BUNDLE_URL`: direct download URL for the release ZIP.
- `MODEL_BUNDLE_ARCHIVE_SHA256`: checksum printed by the packaging command.
- `NFL_SEASON`: current NFL season, initially `2026`.

The workflow verifies the archive checksum before extraction. The inference
script then independently verifies every individual model artifact against the
tracked model manifest before deserialization.

## GitHub automation

`.github/workflows/weekly-projections.yml` runs at `10:17 UTC` every Wednesday.
It also supports a manual run with explicit season/week inputs and a
`publish_existing` recovery mode.

If the archived rankings and manifest already exist and match the public
snapshot, the weekly runner treats the publication as complete and makes no
file changes. This makes scheduled retries safe.

The workflow requires repository `contents: write` permission because a
successful run commits only the compact public snapshot and tracked audit
evidence. Full historical data, source snapshots, prediction Parquet files, and
model objects remain ignored.

Do not enable the schedule until all three repository variables above are set.

## Streamlit Community Cloud

After the project is pushed to GitHub:

1. Sign in to Streamlit Community Cloud with GitHub.
2. Create an app from this repository.
3. Select the `main` branch.
4. Set the entrypoint to `app.py`.
5. Deploy the app.

No Streamlit secrets are required for the read-only public application. A
successful GitHub Actions commit updates the two public result files, which
causes the deployed app to refresh from the repository.

## Publication gates

The public snapshot is rejected when any of these conditions occurs:

- Ranking status does not begin with `PASS`.
- Ranking CSV hash differs from its manifest.
- Required public columns or keys are missing.
- Duplicate player-game keys exist.
- A selected starter or FLEX row is not role eligible.
- Display projections are missing or negative.
- Team, game, row, or lineup coverage differs from the upstream evidence.
- An observed target outcome appears in the public ranking file.

Schedule coverage is derived from the target-week source evidence rather than
hard-coded to 32 teams and 16 games, so regular-season bye weeks remain valid.

## Current limitation

The installed injury reader does not yet provide the 2026 injury report. The
workflow does not interpret missing injury data as healthy. Until a validated
replacement is added, the app displays the explicit injury warning and the
publication status remains `PASS_WITH_INJURY_CAVEAT`.
