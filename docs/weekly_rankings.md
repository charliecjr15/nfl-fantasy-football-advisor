# Weekly Projection Rankings

## Status

The protected Version 1 weekly ranking workflow and its first live 2026 Week 1
run are complete. The accepted data run was created at
`2026-08-22 08:10:06 UTC` from ranking commit `a8bba90`.

All feature, prediction, and depth-snapshot hashes reconciled. The output kept
all 808 candidates, retained all 32 teams and 16 games, identified 283
role-eligible players, and filled exactly 84 provisional lineup slots. All 84
selected rows met the configured `HIGH` historical-evidence threshold.

The data ranking status is `PASS_WITH_INJURY_CAVEAT`. This is a structural and
reasonableness acceptance, not a forecast-accuracy result.

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

## Outputs

Output                                                         Git treatment
-------------------------------------------------------------  --------------------------
`data/processed/recommendations/2026_week_01_rankings.parquet`  Ignored generated artifact
`results/tables/weekly_rankings_2026_week_01.csv`               Tracked analytical output
`results/tables/weekly_rankings_2026_week_01_manifest.csv`      Tracked run evidence
`results/reports/weekly_rankings_2026_week_01_artifact.json`    Tracked report source

The canonical report artifact passed package/schema validation, but no portable
HTML report was accepted. Browser QA repeatedly detected a small page-level
horizontal overflow at the 1,440-pixel desktop viewport, including after the
native evidence table was removed and the chart was reduced to a four-bar,
single-series comparison. The artifact-specific content rendered in the failure
preview, so the remaining issue is isolated to the portable-reader verification
path. Temporary failure screenshots were removed, and no failed HTML was kept.

The tracked CSV remains the analytical source of truth. The report artifact is
retained as the reproducible reader source until its HTML can pass browser QA.

## Observed run controls

```text
ranking_rows=808
role_eligible_rows=283
depth_position_mismatch_rows=5
projected_lineup_rows=84
projected_lineup_slots=QB:12,RB:24,WR:24,TE:12,FLEX:12
projected_lineup_confidence=HIGH:84
raw_negative_projection_rows=3
display_floored_projection_rows=3
injury_report_rows=0
duplicate_keys=0
unavailable_keys=0
target_column_loaded=False
ranking_status=PASS_WITH_INJURY_CAVEAT
```

The five roster/model-versus-depth position conflicts remain in the full audit
output, are not role eligible, and carry `DEPTH_POSITION_MISMATCH`.

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
