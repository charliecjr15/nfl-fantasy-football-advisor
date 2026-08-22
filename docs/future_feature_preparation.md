# Future-Week Feature Preparation

## Status

The target-free future-week feature builder and its controlled historical replay
are complete.

The replay ran from future-feature commit `0b86159` for the 350 observed player
rows in 2025 Week 18. All 107 unique output columns reconciled with zero
mismatched rows. The maximum absolute numeric difference was
`7.105427357601002e-15`, below the configured `1e-10` tolerance.

The run loaded 45,343 player-history rows and 16,867 opponent-history rows, all
from weeks strictly earlier than the target. It loaded no target-week outcome,
produced no duplicate or unavailable key, contained no infinite value, and
passed its reopened-output and hash controls.

Live 2026 Week 1 feature preparation is also complete. The corrected run used
future-feature commit `d585a92` and a source cutoff of
`2026-08-22 07:46:47.668866 UTC`.

It produced 808 candidates across all 32 teams and 16 games:

Position  Candidates
--------  ----------
QB        110
RB        179
WR        344
TE        175

The live output contains 252 players without prior validated game history. All
808 rows correctly lack 2026 season-to-date history before Week 1. These values
remain missing for the frozen model pipelines to impute; they are not treated as
zero.

## Purpose

This workflow creates the exact frozen Version 1 inference input for one future
regular-season week. It converts validated completed-game history plus current
roster, depth-chart, and schedule context into:

- Nine required metadata fields.
- Six configured categorical predictors.
- Ninety-six configured numeric predictors.
- Exactly 102 predictors in total.
- One unique row per `season + week + player_id`.

Because `week`, `position`, `team`, and `opponent` serve both metadata and model
roles, the physical output contains 107 unique columns rather than 111 repeated
columns.

The target `target_fantasy_points_ppr` is not part of the output contract.

## Authoritative lineage

The builder freezes the following inputs:

Item                       Value
-------------------------  ----------------------------------------------------------------
Historical feature commit  `75db96b`
Model settings SHA-256     `67cda074536f1c047b752567eb62e7332a6c240b7ee5785dc6c6f7a3479bf623`
Feature SQL SHA-256        `b684da06d5e1df447e5e585efd5b552fdfd1c4ea75f4a60f29709b3e844d48b6`
Replay source SHA-256      `6733ff26d86b8966d0c3aa76c592c2f41b35e555433c99738ccb4c01b42f3fe3`
Feature definition         `v1_prior_game`
Future builder version     `v1_prior_game_future`

The predictor names and order remain authoritative in
`config/model_settings.toml`.

## Historical sources

The workflow reads two validated MySQL tables:

- `player_game_history`: one observed core fantasy player per completed game.
- `opponent_position_week_history`: one defense-position summary per completed
  game.

The tables retain the previously reconciled player statistics, fantasy points,
snap measures, schedule context, and opponent-by-position totals used by the
historical feature pipeline.

Prior completed fantasy outcomes are legitimate historical predictors. The
outcome for the target week is never loaded.

## Leakage-safe cutoff

The only permitted history rows satisfy:

```text
history season < target season
OR
history season = target season AND history week < target week
```

The cutoff is deliberately week-level rather than game-time-level. It prevents
an early game from the target week from becoming a feature for a later game in
the same week.

The builder separately verifies that the maximum loaded history date is before
the earliest target game date.

## Feature calculation parity

Player rolling windows use the previous one, three, or five observed player
games. Season-to-date windows reset for the target season. Opponent windows use
the previous one, three, or five games for the target defense and offensive
position.

Protected efficiency ratios aggregate their numerators and denominators over
the prior three games before division. A zero or unavailable denominator
produces a missing value, not zero or infinity.

MySQL returns `AVG()` of integer columns to four decimal places in the validated
historical table. The Python builder explicitly reproduces that behavior before
the replay comparison. Averages of floating-point measures retain their normal
floating-point precision.

Missing history remains missing. The frozen model pipelines own imputation.

## Historical replay

Replay mode uses the 350 observed player rows from 2025 Week 18 only as safe
target-row anchors. It reads the metadata and current-game context allowlist from
the committed model Parquet file; it does not load the Week 18 target.

The builder then reconstructs every feature from MySQL rows through Week 17 and
compares all 107 unique output columns with the committed Week 18 reference.

The replay passes only when:

- Exactly 350 rows are rebuilt.
- All keys reconcile one-to-one.
- All metadata and categorical values match.
- Every numeric feature matches within `1e-10`.
- No target column is loaded or written.
- No same-week history row is loaded.
- No duplicate or unavailable key exists.
- No numeric feature contains infinity.
- Reopened written outputs and hashes reconcile.

### Observed replay controls

```text
replay_candidate_rows=350
player_history_rows=45,343
opponent_history_rows=16,867
same_week_history_rows_loaded=0
future_feature_columns=107
predictor_count=102
replay_verified_columns=107
replay_mismatch_rows=0
replay_maximum_absolute_difference=7.105427357601002e-15
historical_replay_reconciliation=PASS
```

## Live candidate sources

Live mode uses the installed `nflreadpy` package to load:

- The target season schedule.
- The current season roster.
- Timestamped depth charts.

The script immediately restricts each source to an explicit allowlist and saves
the selected source snapshots under `data/processed/`. The snapshots and full
feature file are Git-ignored, while their hashes and compact evidence are
recorded in tracked artifacts.

Known cross-source team aliases are normalized before joins. This includes the
current roster source's `AZ` value, which is mapped to the schedule and depth
source convention `ARI`. The workflow fails unless the final candidate frame
covers all 32 teams and all 16 target games.

For Version 1, a live candidate must:

- Have a roster position of QB, RB, WR, or TE.
- Have roster status `ACT`.
- Have a non-empty GSIS player ID.
- Appear on the latest team depth-chart snapshot at or before the UTC cutoff.
- Belong to a team scheduled in the target regular-season week.

The latest depth snapshot is selected independently for each of the 32 teams.
The cutoff must be before every target game date.

## Protected outputs

Replay mode writes:

Output                                                                     Git treatment
-------------------------------------------------------------------------  --------------------------
`data/processed/future_features/2025_week_18_replay_features.parquet`       Ignored generated artifact
`data/sample/future_features_2025_week_18_replay_sample.csv`                Tracked
`results/tables/future_features_2025_week_18_replay_verification.csv`       Tracked
`results/tables/future_features_2025_week_18_replay_manifest.csv`           Tracked

Live 2026 Week 1 mode writes:

Output                                                         Git treatment
-------------------------------------------------------------  --------------------------
`data/processed/future_features/2026_week_01_features.parquet`  Ignored generated artifact
`data/processed/future_features/snapshots/2026_week_01/`        Ignored source snapshots
`data/sample/future_features_2026_week_01_sample.csv`           Tracked
`results/tables/future_features_2026_week_01_manifest.csv`      Tracked

Existing outputs are never overwritten.

## Controlled commands

The completed historical replay was run after the protocol commit left
`git status --short` empty:

```powershell
python scripts\build_future_features.py --replay --confirm-build BUILD_V1_FUTURE_FEATURES
```

Do not rerun it now that the protected replay outputs exist. Prior evidence must
not be replaced.

The completed live 2026 Week 1 preparation used an explicit UTC-aware cutoff:

```powershell
$asOfUtc = (Get-Date).ToUniversalTime().ToString('o')
python scripts\build_future_features.py --live --season 2026 --week 1 --as-of $asOfUtc --confirm-build BUILD_V1_FUTURE_FEATURES
```

Do not rerun the live build now that its protected snapshot and evidence exist.
Later source updates require a newly versioned snapshot rather than replacement
of this cutoff.

### Observed live controls

```text
eligible_active_roster_rows=895
depth_matched_candidate_rows=808
depth_unmatched_candidate_rows=87
live_candidate_rows=808
candidate_teams=32
candidate_games=16
player_history_rows=45,693
opponent_history_rows=16,994
same_week_history_rows_loaded=0
future_feature_columns=107
predictor_count=102
future_feature_duplicate_keys=0
future_feature_unavailable_keys=0
future_feature_infinite_values=0
target_week_outcome_loaded=False
future_feature_status=PASS
```

The live feature Parquet can later be supplied to
`scripts/predict_with_bundle.py` only after its tracked evidence is committed
and the worktree is clean.

## Current limitations

- The frozen model was trained on players who appeared in weekly statistics.
  The live candidate set is broader, so a feature-ready row does not prove that
  the player will dress, play, or receive fantasy-relevant usage.
- Current roster status and depth-chart presence are availability screens, not
  playing-time guarantees.
- Injury reports are not yet used to remove or downgrade candidates.
- Training-camp and preseason rosters can remain much larger than the final
  53-player roster.
- Schedule lines, roster membership, and depth charts can change after the
  recorded cutoff. Every recommendation must state its data cutoff.
- The validated MySQL history currently ends with the 2025 regular season. It is
  sufficient for 2026 Week 1; later 2026 weeks require a separately validated
  current-season history refresh before feature preparation.
- This workflow prepares model inputs. It does not itself generate projections,
  uncertainty intervals, draft rankings, start/sit advice, or causal claims.
