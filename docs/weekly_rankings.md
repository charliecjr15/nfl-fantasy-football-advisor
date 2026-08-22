# Weekly Projection Rankings

## Status

The protected Version 1 weekly ranking protocol is implemented. Its first live
run will use the already frozen 2026 Week 1 feature and projection snapshots.

## Decision and audience

The output supports a manager in the default 12-team full-PPR redraft league.
It answers a narrower question than the projection model:

> Which role-plausible players currently rank inside the league's QB, RB, WR,
> TE, and FLEX demand thresholds?

The output is provisional until current injury and availability context is
attached. It does not automatically manage a roster.

## Why raw projections are not enough

The Version 1 models predict fantasy points conditional on a player appearing in
a game. A high raw score for a deep backup does not mean the player is likely to
receive that opportunity.

The decision layer therefore preserves the raw model score and applies a
separate current-role eligibility control from the frozen depth-chart snapshot:

Position  Maximum eligible depth rank
--------  ---------------------------
QB        1
RB        3
WR        3
TE        2

These are explicit Version 1 screening rules, not learned model features.

## League-demand calculation

For 12 teams, the fixed starting demand is:

Position  Calculation  Slots
--------  -----------  -----
QB        12 x 1       12
RB        12 x 2       24
WR        12 x 2       24
TE        12 x 1       12

After those 72 players are selected, the 12 highest remaining role-eligible RB,
WR, and TE players receive the FLEX slots. The resulting projected lineup pool
contains exactly 84 players.

## Ranking fields

The output preserves:

- `projected_fantasy_points_ppr`: unchanged model output.
- `display_projected_fantasy_points_ppr`: the raw score floored at zero for a
  later user interface.
- `raw_position_rank`: rank among every projected player at that position.
- `position_rank`: rank among role-eligible players at that position.
- `overall_flex_rank`: rank among all role-eligible RB, WR, and TE players.
- `remaining_flex_rank`: rank after fixed-position starters are removed.
- `projected_lineup_slot`: QB, RB, WR, TE, FLEX, BENCH_DEPTH, or ROLE_FILTERED.
- `evidence_confidence`: historical-evidence coverage, not a probability of
  prediction accuracy.
- `risk_flags`: explicit role, history, injury-source, and display-floor flags.

## Evidence-confidence rules

`HIGH` requires at least five prior games, no more than 365 days since the last
recorded game, and a prior snap record.

`MEDIUM` requires at least three prior games and no more than 730 days since the
last recorded game.

All other rows are `LOW`.

These labels describe feature support. They are not calibrated prediction
intervals and do not mean a player has a stated chance of beating the
projection.

## Injury-context limitation

The installed `nflreadpy` 2026 injury request currently stops with:

```text
ValueError: Season must be between 2009 and 2025
```

The workflow must not interpret missing injury data as healthy. Every output row
therefore records:

```text
injury_context=SOURCE_UNAVAILABLE_FOR_2026_AT_BUILD
risk_flags=INJURY_CONTEXT_UNAVAILABLE;...
```

## Protected command

Commit the ranking protocol, confirm `git status --short` is empty, and run:

```powershell
.\.venv\Scripts\python.exe scripts\build_weekly_rankings.py `
  --season 2026 `
  --week 1 `
  --confirm-build BUILD_V1_WEEKLY_RANKINGS
```

The workflow verifies the feature, projection, and depth-snapshot hashes against
their tracked manifests before ranking. It refuses to overwrite existing
outputs.

## Planned outputs

Output                                                         Git treatment
-------------------------------------------------------------  --------------------------
`data/processed/recommendations/2026_week_01_rankings.parquet`  Ignored generated artifact
`results/tables/weekly_rankings_2026_week_01.csv`               Tracked analytical output
`results/tables/weekly_rankings_2026_week_01_manifest.csv`      Tracked run evidence
`results/reports/weekly_rankings_2026_week_01_artifact.json`    Tracked report source

The portable report HTML is packaged from the validated artifact JSON. It is not
hand-authored or allowed to replace the CSV as the analytical source of truth.

## Acceptance criteria

The run passes only when:

- Every prediction reconciles one-to-one with its feature row.
- Prediction, feature, and depth snapshot hashes match tracked lineage.
- Every player matches exactly one current depth row at the frozen cutoff.
- Roster/model-versus-depth position disagreements are excluded from role
  eligibility and flagged rather than silently coerced.
- All 32 teams and 16 Week 1 games remain represented.
- All 808 player-game keys remain available and unique.
- Fixed position demand and 12 FLEX slots produce exactly 84 lineup rows.
- Raw predictions remain unchanged.
- Display-floor changes are counted and flagged.
- Missing 2026 injury context is visible rather than treated as healthy.
