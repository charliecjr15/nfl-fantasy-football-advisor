# Future-Week Feature Preparation

## Status

The target-free future-week feature builder is implemented but has not yet been
executed as a controlled run.

The historical replay must be run only after the configuration, script,
documentation, and README are committed with a clean Git worktree. Live feature
preparation must wait until the replay evidence passes and is committed.

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

## Live candidate sources

Live mode uses the installed `nflreadpy` package to load:

- The target season schedule.
- The current season roster.
- Timestamped depth charts.

The script immediately restricts each source to an explicit allowlist and saves
the selected source snapshots under `data/processed/`. The snapshots and full
feature file are Git-ignored, while their hashes and compact evidence are
recorded in tracked artifacts.

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

Run the historical replay only after the protocol commit leaves
`git status --short` empty:

```powershell
python scripts\build_future_features.py --replay --confirm-build BUILD_V1_FUTURE_FEATURES
```

After the replay evidence is committed, live 2026 Week 1 preparation requires
an explicit UTC-aware cutoff:

```powershell
$asOfUtc = (Get-Date).ToUniversalTime().ToString('o')
python scripts\build_future_features.py --live --season 2026 --week 1 --as-of $asOfUtc --confirm-build BUILD_V1_FUTURE_FEATURES
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
