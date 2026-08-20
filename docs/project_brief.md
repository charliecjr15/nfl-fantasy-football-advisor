# NFL Fantasy Football Advisor: Project Brief

## Project status

Source validation complete; historical extraction design in progress.

## Project objective

Build a reproducible NFL analytics system that uses historical and current player data to support season-long fantasy football decisions.

The system will produce preseason draft rankings and weekly recommendations for a default 12-team, full-PPR redraft league. Recommendations will be based
on transparent statistical evidence rather than unsupported opinions.

A later project phase will reuse the player projections for daily fantasy sports analysis.

## Intended user

The initial user is a fantasy football manager participating in a standard 12-team season-long league.

The system should help the manager answer:

- Which players should I target during the preseason draft?
- Which players should I start this week?
- Which player should fill my FLEX position?
- Which available players are promising waiver-wire targets?
- Which players have favorable or unfavorable upcoming matchups?
- Why does the system prefer one player over another?

## Default league configuration

- League type: redraft
- Number of teams: 12
- Draft type: snake
- Scoring: full PPR
- Starting quarterbacks: 1
- Starting running backs: 2
- Starting wide receivers: 2
- Starting tight ends: 1
- Starting FLEX players: 1
- Starting kickers: 1
- Starting defenses: 1
- Bench positions: 6
- Injured-reserve positions: 1

The FLEX position may contain an RB, WR, or TE.

## Default player scoring rules

- Passing yards: 0.04 points per yard
- Passing touchdowns: 4 points
- Interceptions: -2 points
- Rushing yards: 0.10 points per yard
- Rushing touchdowns: 6 points
- Receptions: 1 point
- Receiving yards: 0.10 points per yard
- Receiving touchdowns: 6 points
- Individual special-teams touchdowns: 6 points
- Two-point conversions: 2 points
- Lost fumbles: -2 points

Kicker and defense scoring will be added after the core QB, RB, WR, and TE workflow is validated.

## Version 1 scope

Version 1 will focus on season-long fantasy football and will include:

1. Historical player-game and player-week statistics
2. Reproducible full-PPR fantasy-point calculations
3. Player, roster, team, schedule, and injury data
4. Rolling player-performance and opportunity measures
5. Upcoming opponent and matchup context
6. Weekly projected fantasy points
7. Position-specific weekly rankings
8. Start, sit, FLEX, and waiver-wire recommendation tiers
9. Plain-language explanations for each recommendation
10. Preseason draft rankings using historical performance, projected opportunity, and available ranking benchmarks
11. Backtesting against completed NFL weeks
12. Exported result tables, charts, and a portfolio-ready summary

## Initial analytical grain

The main historical table will use one row per:

`season + week + player`

Each row will describe one player's performance in one NFL week.

Upcoming projection tables will use one row per:

`season + week + player + projection_version`

The projection version or creation timestamp will preserve what the system knew when a recommendation was generated.

## Planned data sources

The primary data source will be [nflverse](https://github.com/nflverse/nflverse-data), accessed through the maintained [nflreadpy](https://github.com/
nflverse/nflreadpy) Python package.

Planned source categories include:

- Weekly player statistics
- Game schedules and results
- Player and team identifiers
- Weekly rosters
- Injury reports
- Depth charts
- Snap counts
- Play-by-play data
- Fantasy-football player ID mappings
- Available draft and weekly ranking benchmarks

Raw source data will be retained separately from processed analytical data. Source dates, seasons, row counts, and data availability will be documented.

## Planned player features

Potential predictive features include:

- Previous-week fantasy points
- Rolling three-week fantasy points
- Rolling five-week fantasy points
- Season-to-date fantasy points
- Passing attempts
- Carries
- Targets
- Receptions
- Total opportunities
- Snap count and snap share
- Target share
- Red-zone opportunities
- Touchdowns
- Yards per opportunity
- Team scoring environment
- Opponent
- Home or away status
- Days of rest
- Injury designation
- Recent practice participation
- Depth-chart position
- Opponent fantasy points allowed by position
- Recent opponent defensive performance
- Bye-week status

Every weekly feature must use only information that would have been available before the predicted game. Future-week information must never leak into
historical model training or evaluation.

## Planned recommendation outputs

The weekly recommendation table should eventually include:

- Season
- Week
- Player identifier
- Player name
- Team
- Opponent
- Position
- Injury status
- Projected fantasy points
- Projection floor
- Projection ceiling
- Position rank
- Overall FLEX rank where applicable
- Start, sit, FLEX, or waiver tier
- Confidence level
- Recommendation reasons
- Projection creation timestamp
- Source-data freshness timestamp

## Evaluation plan

The project will use time-based validation rather than randomly mixing past and future weeks.

Planned evaluation measures include:

- Mean absolute error for projected fantasy points
- Root mean squared error
- Spearman rank correlation between projected and actual player results
- Accuracy of start-worthy player tiers
- Performance by position
- Performance by week
- Performance for high-volume and low-volume players
- Comparison against a simple rolling-average baseline
- Comparison against available external ranking benchmarks when licensing permits

A more complicated model must outperform a simple, documented baseline before it replaces that baseline.

## Data-quality controls

The project will validate:

- Row counts by season and week
- Duplicate player-week keys
- Missing player and team identifiers
- Missing positions
- Unexpected position values
- Schedule-to-stat matching
- Roster-to-stat matching
- Injury-data coverage
- Players changing teams
- Bye weeks
- Postponed or canceled games
- Players with no recent NFL history
- Fantasy-point calculation reconciliation
- Projection rows created after a game began
- Accidental use of future-week data

Missing statistics will not automatically be treated as zero unless the field definition supports that interpretation.

## Technology plan

- Python 3.11
- `nflreadpy`
- Polars for source loading
- pandas where useful for analysis and presentation
- MySQL 8 for staged and analytical tables
- SQL for transformations, validation, and exploratory analysis
- scikit-learn for baseline projection models
- Matplotlib and Seaborn for charts
- Streamlit or another lightweight interface in a later phase
- Git and GitHub for version control and portfolio publication

## Planned workflow

1. Document the fantasy decision and scoring rules.
2. Create the project structure and Python environment.
3. Inspect available nflverse datasets and columns.
4. Extract a small historical sample.
5. Define and validate fantasy-point calculations.
6. Load staged data into MySQL.
7. Create clean player, team, schedule, roster, injury, and weekly-stat tables.
8. Build leakage-safe historical features.
9. Establish simple projection baselines.
10. Backtest the projections using chronological validation.
11. Create weekly position rankings.
12. Add start, sit, FLEX, and waiver recommendation rules.
13. Create preseason draft rankings.
14. Export result tables and charts.
15. Build a usable weekly interface.
16. Document findings, limitations, and reproduction instructions.
17. Publish the completed project to GitHub.

## Future DFS phase

After the season-long system is validated, a separate DFS module may add:

- Platform-specific salary data
- Salary-cap constraints
- Projected points per salary dollar
- Player stacking rules
- Opponent correlation
- Lineup optimization
- Contest-specific risk preferences
- Multiple optimized lineups

DFS will remain separate from version 1 so its salary and lineup rules do not distort the season-long recommendation logic.

## Important limitations

- Fantasy projections are uncertain and are not guarantees.
- Injuries, coaching decisions, weather, trades, and role changes can make historical trends less useful.
- Rookie players and players with limited recent history require special treatment.
- Public injury and depth-chart information may be incomplete or delayed.
- Opponent strength can change during a season.
- External rankings may reflect expert judgment that is not fully reproducible.
- Results depend on the selected league and scoring rules.
- The system will support decisions but will not automatically manage a fantasy roster.
- Future DFS analysis may relate to paid contests, but this project will not promise profits or eliminate financial risk.

## Planned deliverables

- Project brief
- Source-data profile
- Reproducible Python extraction scripts
- MySQL staging and analytical model
- Data-quality audit queries
- Fantasy-point calculation documentation
- Historical feature tables
- Baseline projection model
- Backtesting results
- Preseason draft rankings
- Weekly start/sit rankings
- FLEX recommendations
- Waiver-wire candidate tables
- Decision-relevant charts
- Weekly recommendation interface
- Executive summary
- GitHub README with complete reproduction instructions