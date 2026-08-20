# MySQL Staging Layer and Validation

## Technical summary

The MySQL staging pipeline successfully loaded and reconciled 1,446,743 historical NFL rows across six staging tables.

All 48 season-dataset partitions matched the validated extraction manifest. Every documented analytical grain remained unique, schedule and roster
coverage reached 100% in every season, snap-count coverage remained between 99.77% and 100%, and all 45,693 configured full-PPR calculations reconciled
without a mismatch.

The staging layer is trustworthy enough to support clean analytical tables. It is not yet a model-ready feature table.

## All six staging tables reconcile exactly

The loader completed all 48 partitions in 146.9 seconds on the development machine. Runtime is machine-specific and should not be treated as a performance
benchmark.

Staging table              Expected rows    Loaded rows    Difference    Status
━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━  ━━━━━━━━━━━━  ━━━━━━━━
stg_schedules                      2,127          2,127             0    Pass
─────────────────────────  ───────────────  ─────────────  ────────────  ────────
stg_weekly_rosters               362,959        362,959             0    Pass
─────────────────────────  ───────────────  ─────────────  ────────────  ────────
stg_injuries                      43,561         43,561             0    Pass
─────────────────────────  ───────────────  ─────────────  ────────────  ────────
stg_depth_charts                 796,273        796,273             0    Pass
─────────────────────────  ───────────────  ─────────────  ────────────  ────────
stg_snap_counts                  196,130        196,130             0    Pass
─────────────────────────  ───────────────  ─────────────  ────────────  ────────
stg_weekly_player_stats           45,693         45,693             0    Pass

All dataset-season rows also matched the chronological split configured in ../config/data_settings.toml:

- Training: 2018–2023
- Validation: 2024
- Test: 2025

Tables are used instead of charts because this document records exact ingestion and audit controls rather than a trend analysis.

## Six staging tables preserve their validated source grains

Each table has a generated staging_row_id primary key and a loaded_at ingestion timestamp. Source-grain uniqueness is audited separately so unavailable
source identifiers can remain visible instead of being silently discarded.

Table                      Intended source grain
━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
stg_weekly_player_stats    One core fantasy player per regular-season week
─────────────────────────  ─────────────────────────────────────────────────────────────────────
stg_schedules              One regular-season game
─────────────────────────  ─────────────────────────────────────────────────────────────────────
stg_weekly_rosters         One player-team-week roster record
─────────────────────────  ─────────────────────────────────────────────────────────────────────
stg_injuries               One player-team-week injury record
─────────────────────────  ─────────────────────────────────────────────────────────────────────
stg_depth_charts           Legacy player-position-week or timestamped player-position snapshot
─────────────────────────  ─────────────────────────────────────────────────────────────────────
stg_snap_counts            One player-game snap record

The core fantasy population includes QB, RB, WR, and TE only. The final player-stat distribution is:

Position    Player-week rows    Distinct players
━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━
QB                     5,092                 171
──────────  ──────────────────  ──────────────────
RB                    12,003                 392
──────────  ──────────────────  ──────────────────
TE                     9,513                 316
──────────  ──────────────────  ──────────────────
WR                    19,085                 604

All player-stat rows have an available player ID, game ID, team, opponent, valid position, regular-season designation, and valid NFL week.

## Candidate grains remain unique

No duplicate groups were found at any validated analytical grain.

Dataset                     Total rows    Unavailable primary identifier rows    Duplicate key groups
━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━━━━━━━
Weekly player statistics        45,693                                      0                       0
──────────────────────────  ────────────  ─────────────────────────────────────  ──────────────────────
Schedules                        2,127                                      0                       0
──────────────────────────  ────────────  ─────────────────────────────────────  ──────────────────────
Weekly rosters                 362,959                                    131                       0
──────────────────────────  ────────────  ─────────────────────────────────────  ──────────────────────
Injuries                        43,561                                      0                       0
──────────────────────────  ────────────  ─────────────────────────────────────  ──────────────────────
Snap counts                    196,130                                      0                       0

The 131 unavailable weekly-roster GSIS identifiers represent approximately 0.04% of roster rows. They remain in staging for auditability but cannot
participate in player-level joins.

Depth charts require format-specific keys:

- Legacy weekly records use season, week, team, GSIS ID, position group, position abbreviation, and depth rank.
- Timestamped records use timestamp, team, GSIS ID, position abbreviation, and position slot.

Both depth-chart formats have zero duplicate key groups.

The 2025 timestamped depth source contains 5,577 rows without an available GSIS ID, approximately 1.01% of that feed. These records must be excluded from
player-level feature joins unless a reliable identifier is added later.

## Join coverage exceeds every quality threshold

Schedule and roster joins match every core player-week row. Only 39 of the 45,693 player-week rows lack a snap-count match, approximately 0.09% overall.

Season    Player-week rows    Schedule match    Roster match    Snap match    Status
━━━━━━━━  ━━━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━━━  ━━━━━━━━━━━━━━  ━━━━━━━━━━━━  ━━━━━━━━
    2018               5,363           100.00%         100.00%       100.00%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2019               5,411           100.00%         100.00%        99.89%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2020               5,543           100.00%         100.00%       100.00%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2021               5,866           100.00%         100.00%        99.90%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2022               5,808           100.00%         100.00%        99.98%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2023               5,801           100.00%         100.00%        99.90%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2024               5,864           100.00%         100.00%        99.90%    Pass
────────  ──────────────────  ────────────────  ──────────────  ────────────  ────────
    2025               6,037           100.00%         100.00%        99.77%    Pass

The configured minimum snap-count coverage is 98%. Missing snap data will remain NULL in the clean layer and receive a missingness indicator rather than
being converted to zero.

## Full-PPR scoring reconciles exactly

The staged player statistics contain both the source full-PPR value and the project’s independently calculated value.

Across every season:

- Rows outside the 0.01-point tolerance: 0
- Maximum absolute difference: 0.00 points
- Reconciliation status: Pass

This confirms that the configured scoring rules match the historical source for QB, RB, WR, and TE records.

## Identity exceptions remain controlled and visible

The roster audit found:

- 13 player-week groups associated with more than one team
- 0 conflicting GSIS-to-PFR mappings within a player-team-week
- 68 weekly rows carrying a PFR conflict flag

The 68 flagged rows are repeated weekly roster observations, not 68 distinct unresolved players. The loader preserves the flags so downstream
transformations can choose the official player mapping while retaining the source discrepancy.

Multi-team player weeks must remain at player-team-week grain until a documented team-selection rule is applied.

## Injury sparsity is expected but time availability differs in 2025

Missing final injury-report status ranges from 50.95% to 54.69% by season. The stability of that rate indicates normal source-reporting behavior rather
than a failed partition.

Missing practice status ranges from 0.30% to 0.80%.

A missing final report status must not automatically be interpreted as healthy. Feature engineering should preserve separate indicators for:

- whether an injury row exists;
- whether a final game status exists;
- whether a practice status exists;
- the observed status value.

The date_modified field is populated for all staged injury rows from 2018 through 2024. The 2025 source does not provide that field, so its rows cannot
support precise intraday as-of filtering.

For leakage-safe historical modeling, same-week injury information should be used only when its availability before the prediction cutoff can be
established. Previous-week injury information remains safer for the first one-week-ahead baseline.

## The injury text-width failure is resolved

The first staging attempt stopped on a 154-character report_primary_injury value because the original MySQL column allowed only 150 characters.

The failed 2024 injury partition rolled back without a partial commit. A complete source-width audit found no other overflowing text columns.

The final field is:

report_primary_injury VARCHAR(255)

The current maximum is 154 characters, leaving 101 characters of headroom. The regression control in ../sql/03_validate_staging.sql verifies this limit
after every reload.

## The loader requires explicit replacement permission

../scripts/load_mysql_staging.py performs the following controls before loading:

1. Reads the 48-row extraction manifest.
2. Confirms every Parquet file exists.
3. Reconciles each Parquet row count to the manifest.
4. Confirms Parquet columns match the MySQL staging schemas.
5. Refuses to clear populated tables unless --replace is supplied.
6. Loads each partition as a database transaction.
7. Rolls back the current partition if an insert fails.
8. Reconciles MySQL table and season totals after loading.

The default command is appropriate only when every staging table is empty:

python scripts\load_mysql_staging.py

To intentionally rebuild all six reproducible staging tables:

python scripts\load_mysql_staging.py --replace

The --replace option truncates only the six documented stg_ tables before reloading them.

## Reproducing the MySQL staging layer

Run the SQL and Python steps in this order:

1. Execute ../sql/01_create_database.sql.
2. Execute ../sql/02_create_staging_tables.sql.
3. Configure the ignored local .env file using .env.example.
4. Activate the project virtual environment.
5. Run the staging loader.
6. Execute ../sql/03_validate_staging.sql.

Local credentials are never committed. The project’s .gitignore excludes .env.

## Limitations and modeling safeguards

The staging layer preserves validated source data but does not yet resolve every record into a final modeling grain.

The clean layer must address these limitations:

- Rows without usable player identifiers cannot participate in player-level joins.
- Missing snap matches must stay distinguishable from true zero snaps.
- Legacy and timestamped depth charts require different as-of rules.
- Timestamped depth rows after a target game must never be used for that game.
- Missing injury status must not be interpreted as a healthy designation.
- The 2025 injury source lacks modification timestamps.
- Multi-team player weeks require team-aware logic.
- loaded_at records local ingestion time, not when the source information first became publicly available.

These controls establish structural and reconciliation quality. They do not establish that a future projection model will be accurate, unbiased, or
causally interpretable.

## Clean analytical tables are the next milestone

The next stage should:

1. Create clean schedule, player-week, roster, injury, depth, and snap tables.
2. Enforce analytical keys after documented exclusions.
3. Preserve explicit availability and missingness flags.
4. Create team-week schedule context.
5. Create reliable GSIS-to-PFR player crosswalks.
6. Build format-aware depth-chart joins.
7. Prepare one leakage-safe row per player and prediction week.

## Further questions

The clean-layer design must determine:

- Which roster record should represent a player during a multi-team week?
- How should 2025 injury rows be used without update timestamps?
- What is the safest as-of rule for the timestamped depth-chart feed?
- Should snap-count gaps be imputed, positionally estimated, or left missing?
- Which identifiers should be retained for later fantasy-platform integrations?