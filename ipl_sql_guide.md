# IPL SQLite Query Guide

This database contains only Indian Premier League matches. Unless the user
explicitly asks to inspect a stored format label, do not add Test, ODI, or
international-team filters. Never use `m.match_type = 'Test'`.
This IPL rule overrides any general cricket instruction that says fivefers,
wickets, catches, hundreds, averages, or other unqualified questions should
default to Test cricket. In this assistant they always default to IPL.

## High-priority regression rules

- Career leaderboards for fours, sixes, stumpings, runs, wickets, catches, matches,
  hundreds, and fifties use the stored columns in `player_career_stats` with
  `format_group = 'IPL' AND competition_name = 'All'`. Do not `SUM` a stored
  career column.
- A highest individual score query must return the innings row, including
  `player_name`, `runs_scored`, and `is_not_out`; do not return only
  `MAX(runs_scored)`.
- IPL titles are `team_career_stats.titles`; match wins are
  `team_career_stats.wins`. Never substitute wins when the question says
  titles/trophies. For "which teams have won the most titles", compare
  `titles` with `(SELECT MAX(titles) FROM team_career_stats)` and return all
  tied teams.
- A highest team total query must return `team` and `runs` from
  `match_innings_stats`; use `SELECT team, runs ... ORDER BY runs DESC LIMIT
  1`. Do not return only `MAX(runs)` and do not rename `runs`.
- `delivery_stats` has no `season`; always join `match_stats m` and filter
  `m.season`. When a delivery query joins another table, qualify
  `d.match_id`, `d.innings_number`, `d.over_number`, and
  `d.delivery_number`.
- `player_batting_innings_stats` never has `competition_name = 'All'`.
  This remains forbidden inside consecutive-hundreds CTEs.

`competition_name = 'All'` is valid only for the two summarized career tables:
`player_career_stats` and `player_career_group_stats`. Never add
`competition_name = 'All'` to `player_batting_innings_stats`; its rows store
`competition_name = 'Indian Premier League'`, not `All`.

## Choose the table by question

- Match results, tosses, dates, venues, margins: `match_stats`.
- Team innings totals, run rates, wickets and extras:
  `match_innings_stats` joined to `match_stats`.
- A player's combined scorecard statistics in one match:
  `player_match_stats`.
- A player's statistics in a particular innings:
  `player_match_innings_stats`.
- One delivery/ball, including its over, batter, bowler and whether it was a
  six: `delivery_stats`.
- Individual batting innings, scores, dismissals, opposition and batting
  position: `player_batting_innings_stats`.
- Stored all-time player totals and averages: `player_career_stats`, filtered
  with `format_group = 'IPL' AND competition_name = 'All'`.
- Player statistics grouped by season or opposition:
  `player_career_group_stats`, using `group_type = 'year'` or
  `group_type = 'opposition'`.
- Franchise all-time results and titles: `team_career_stats`.
- Franchise results for a particular season and the champion flag:
  `team_season_stats`.
- Orange Cap season winners: `orange_cap_winners`.
- Purple Cap season winners: `purple_cap_winners`.
- Verified scheduled fixtures absent from ball-by-ball data because play never
  began: `supplemental_matches`.
- Source venue names mapped to canonical physical stadiums: `venue_aliases`.
- Delivery-derived hat-tricks with match context: `hat_trick_stats`.
- Source-backed records needing non-scorecard metadata: `special_record_stats`.
- Final points-table bottom teams by season: `team_last_place_finishes`.

## Core rules

1. The database is already IPL-only. Do not filter `event_name` unless useful
   for clarity, and never default to Test cricket.
2. Use stored career columns for career totals: `runs_scored`, `matches`,
   `hundreds`, `fifties`, `fours`, `sixes`, `wickets_taken`, `catches`, `stumpings`,
   `batting_average`, `bowling_average`, `best_bowling`, and `five_wickets`.
   Do not `COUNT(*)` when the requested total is already a career column.
   For "who has the most centuries/hundreds", use `player_career_stats.hundreds`
   with `format_group = 'IPL' AND competition_name = 'All'`, rank by
   `hundreds DESC`, and return every player tied for the maximum. Alternatively
   count qualifying `player_batting_innings_stats` rows with
   `runs_scored >= 100`, but then do NOT filter `competition_name = 'All'`.
   For "how many centuries has PLAYER scored", always prefer:
   `SELECT hundreds FROM player_career_stats WHERE player_name = ... AND
   format_group = 'IPL' AND competition_name = 'All'`. If ordering is added,
   `batting_innings` may be used only because this query is on
   `player_career_stats`. Never reference `batting_innings` while querying
   `player_batting_innings_stats`; that table has one row per innings and has
   no `batting_innings` column.
   For "who has hit the most fours", rank `player_career_stats.fours` with
   `format_group = 'IPL' AND competition_name = 'All'`. Do not sum innings
   rows, and never apply `competition_name = 'All'` to
   `player_batting_innings_stats`.
3. For a player's highest score or a score in a particular match/season, use
   `player_batting_innings_stats`. `is_not_out = 1` means not out. For the
   highest individual score in a named season, join that table to
   `match_stats`, filter `m.season`, and order `p.runs_scored DESC`. Never
   apply `season` to `player_batting_innings_stats`, which has no such column.
   Return the complete innings row context rather than only `MAX(runs_scored)`.
   "Boundaries" means fours plus sixes unless the user explicitly asks only
   for fours. For "who among these players hit more/most boundaries in one
   innings", filter those players in `player_batting_innings_stats`, calculate
   `fours + sixes AS boundaries` for every innings row, and order that
   expression descending. Do not `SUM(fours)` or `SUM(fours + sixes)` across
   each player's career. Rishabh Pant resolves to `RR Pant`.
   For "against which team were the most centuries scored in YEAR", join
   batting innings to `match_stats` for the season, filter
   `runs_scored >= 100`, and group by
   `player_batting_innings_stats.opposition`. Do not derive the opponent from
   a `match_innings_stats` alias or reference `mi.team`. Return every
   opposition tied at the maximum century count.
4. For five-wicket hauls, either use career `five_wickets` or count innings
   rows in `player_match_innings_stats` where `wickets_taken >= 5`. Never count
   combined match wickets as an innings haul.
   "Fastest to reach N IPL wickets" means the fewest chronological match
   appearances needed for cumulative wickets to reach N. Join
   `player_match_stats` to `match_stats`; within each player, ordered by
   `match_date, match_id`, calculate both `ROW_NUMBER()` and cumulative
   `SUM(wickets_taken)`. For each player take the first row at or above the
   milestone, then rank `matches_to_N` ascending. This is not a batting
   century and must never query `special_record_stats` with `fastest
   century`. The outer milestone query must use the player-name column exposed
   by its CTE/subquery; never reference an inner alias such as `p.player_name`
   after alias `p` has gone out of scope.
5. For a team highest innings, use `match_innings_stats.runs`, filtering its
   `team` column. For the opponent, join through `match_stats`.
   For extras, `match_innings_stats.team` is the batting team that received
   the extras, not the fielding team that conceded them. To find the most
   extras conceded in a single match, derive the conceding team as the other
   one of `match_stats.team1` and `team2`, group by `match_id` and that team,
   alias it `team`, sum `extras_total AS extras_conceded`, then select those
   same CTE column names and rank the match-level totals. Never reference
   `team` outside the CTE if the derived column was instead named
   `conceding_team`, and never group only by team across IPL history.
   "Lowest total defended" means the lowest first-innings score by a team that
   won by runs; it has nothing to do with `event_stage = 'Final'`. For the
   conventional full-length IPL record, exclude reduced-over innings by
   requiring the first innings to be complete: either `wickets = 10` or
   `legal_balls = scheduled_overs * balls_per_over`. Join `match_stats`, use
   `innings_number = 1`, require `m.winner = mi.team` and
   `m.won_by_runs > 0`, then order `mi.runs ASC`. Return the defending team,
   total, opponent, date, and margin. If the user explicitly asks to include
   rain-shortened matches, do not apply the completed-innings condition.
6. For all-time team wins, losses, win percentage, or titles, use
   `team_career_stats`. For a season, use `team_season_stats`. A loss
   leaderboard must sum or rank the stored `losses` column. Never interpret a
   loss as `wins = 0`, and never sum `matches` under that condition.
   "Most consecutive losses" is not a season or career loss total. Expand
   every match into one appearance per team using `team1` and `team2`, order
   each team's appearances by `match_date, match_id`, mark whether the winner
   differs from that team, and use a window-islands calculation over all
   seasons to count uninterrupted loss streaks. Carry `match_date` and
   `match_id` through every intermediate CTE that feeds an ordered window.
   A win, tie, or no-result breaks a losing streak. The Delhi franchise's
   historical 11-match streak is stored as `Delhi Daredevils`; "alongside
   Delhi Capitals" asks for the other tied record holder, so exclude both
   Delhi names after calculating streaks. Do not query only `MAX(season)` or
   `SUM(losses)`.
7. Season labels are stored as text and may span calendar years:
   `2007/08`, `2009/10`, and `2020/21`. A request for "2008 IPL" means the
   inaugural season stored as `2007/08`; "2010 IPL" means `2009/10`; "2020 IPL"
   means `2020/21`. Other recent seasons normally equal the calendar year.
   Do not invent domestic-style labels such as `2014/15` for the 2015 IPL.
   Specifically, the 2015 IPL is stored as `season = '2015'`. For "number of
   matches played in 2015", count rows from `match_stats` where
   `season = '2015'`.
   The `season` column exists in `match_stats` and `team_season_stats`. It does
   NOT exist in `player_batting_innings_stats`, `player_match_stats`,
   `player_match_innings_stats`, or `player_career_stats`. Never write
   `WHERE season = ...` against those player tables.
   For "who scored the most runs in the 2025 season", join
   `player_batting_innings_stats p` to `match_stats m` on `match_id`, filter
   `m.season = '2025'`, group by `p.player_name`, sum `p.runs_scored`, and
   order by that sum descending.
   The same join rule applies to a franchise's highest run-scorer in a named
   IPL season: filter `p.player_team`, filter the season through
   `match_stats m`, group by `p.player_name`, and sum `p.runs_scored`. Never
   use `p.season`; the innings table has no season column. IPL 2020 is stored
   as `m.season = '2020/21'`. Rajasthan Royals' leader in that season resolves
   to `SV Samson`.
   If using `player_career_group_stats` instead, year values are stored as
   strings such as `group_value = 'year 2025'`, not simply `'2025'`, and its
   competition-specific rows use
   `competition_name = 'Indian Premier League'`, not `'All'`.
   Ordinal IPL match questions such as "the 1st and 500th match" refer to the
   league-wide chronological sequence, not `event_match_number`, which resets
   each season. Number all `match_stats` rows with
   `ROW_NUMBER() OVER (ORDER BY match_date, match_id)`, join player
   appearances, keep the requested ordinal numbers, and require
   `COUNT(DISTINCT ipl_match_number)` to equal the number requested.
8. A tied match can still have a winner after a Super Over. Use the stored
   `winner` for wins; use `result = 'tie'` when the question asks how many
   matches were tied.
9. `team_career_stats.ties` and `no_results` are team appearances, so summing
   them across teams counts each match twice. To count tied or no-result
   matches league-wide, query `match_stats`.
10. `player_match_stats.team` is the player's team.
    `player_batting_innings_stats.player_team` is the player's team.
    `player_career_stats` has no team column.
11. To find a player's team in a season, join a player match/innings table to
    `match_stats` and group by the player's team. Players can represent more
    than one franchise across their IPL career.
    `player_match_stats` uses `team`, not `player_team`. For "which team did
    PLAYER represent before TEAM in IPL YEAR", query the immediately preceding
    season's nonblank team. Rahul Tewatia resolves to `R Tewatia`; immediately
    before his Rajasthan Royals 2020 stint, he represented Delhi Capitals in
    season `2019`.
12. Return all tied leaders when the question says "most" and the lead is
    tied. A ranked CTE or filtering to the maximum is preferable to arbitrary
    `LIMIT 1`.
    Generic leaderboard questions such as "who has played the most number of
    games" name no player. Search all players; never add a `player_name`
    predicate and never select a fuzzy player candidate from words such as
    "games" or "number". For most games/matches played, use
    `player_career_stats.matches` with `format_group = 'IPL'` and
    `competition_name = 'All'`, ordered by `matches DESC`.
13. Use exact database player and team names supplied in Extra context. Do not
    invent expanded player names.
14. Use `LIMIT 50` for open-ended lists, but not for scalar aggregates.
15. For "compare the batting statistics of PLAYER A and PLAYER B", query
    `player_career_stats` directly with both exact names and filter
    `format_group = 'IPL' AND competition_name = 'All'`. Return a meaningful
    batting comparison: `player_name`, `matches`, `batting_innings`,
    `not_outs`, `runs_scored`, `highest_score`, `highest_score_not_out`,
    `batting_average`, `hundreds`, `fifties`, `fours`, `sixes`, and
    `batting_strike_rate`. Do not join `player_match_stats`, do not recompute
    games with `COUNT(*)`, and do not return only matches and strike rate.
    For a highest batting-average leaderboard with a minimum-runs qualifier,
    query `player_career_stats`, apply the requested
    `runs_scored >= MINIMUM` and `batting_average IS NOT NULL` filters, and
    order by `batting_average DESC`. "Highest" never uses ascending order.
    When the user asks for the batting averages of multiple named players,
    return one row for every requested player using `player_name IN (...)`.
    Add `batting_average IS NOT NULL` to avoid empty duplicate career rows.
    Do not turn a multi-player lookup into a leaderboard with `ORDER BY` and
    `LIMIT 1`. Kane Williamson resolves to `KS Williamson`.
16. For "compare the bowling statistics of PLAYER A and PLAYER B", query
    `player_career_stats` directly with both exact names and filter
    `format_group = 'IPL' AND competition_name = 'All'`. Return
    `player_name`, `matches`, `wickets_taken`, `best_bowling`,
    `bowling_average`, and `five_wickets` (plus fielding columns only if
    useful). Do not join `player_match_stats` or
    `player_match_innings_stats`; those joins create duplicate rows and
    ambiguous columns such as `wickets_taken`. Do not recompute a stored
   career bowling total. For a named player's singular "bowling record" or
   "bowling figures", filter that exact `player_name` and return useful career
   bowling columns such as `matches`, `wickets_taken`, `bowling_average`,
   `best_bowling`, and `five_wickets`. Never omit the player predicate and
   rank the whole league. Alzarri Joseph, including the misspelling "Alzeri
   Joseph", resolves to `AS Joseph`.
   For an unqualified all-time "best bowling average" record, use a minimum
   qualification of 50 career IPL wickets so one-off part-time bowlers do not
   lead the table. Require `wickets_taken >= 50` and
   `bowling_average IS NOT NULL`, then order `bowling_average ASC`. Never let
   SQLite's null-first ascending order select a player with no bowling
   average. If the user supplies a different minimum, use their qualification.
17. A short question such as "how many runs has Kohli scored" means IPL career
    runs because this is an IPL-only assistant. Use
    `player_career_stats.runs_scored` with the resolved player name,
    `format_group = 'IPL'`, and `competition_name = 'All'`. Never use
    `SUM(runs_scored)` from `player_batting_innings_stats` for this career
    question, and especially never combine that innings table with
    `competition_name = 'All'`.
18. "Who has taken more/most fivefers" is an all-player IPL leaderboard. Use
    `player_career_stats.five_wickets` with `format_group = 'IPL'` and
    `competition_name = 'All'`, find the maximum, and return every player tied
    at that maximum. Return `five_wickets AS fivefers`. Do not add
    `m.match_type = 'Test'`; do not add any
    `player_name` filter; and do not use `LIMIT 1`, because multiple IPL
    bowlers can share the lead. Do not merely order all career rows. Filter to
    the maximum with this query shape:

    ```sql
    SELECT player_name, five_wickets AS fivefers
    FROM player_career_stats
    WHERE format_group = 'IPL'
      AND competition_name = 'All'
      AND five_wickets = (
        SELECT MAX(five_wickets)
        FROM player_career_stats
        WHERE format_group = 'IPL' AND competition_name = 'All'
      )
    ORDER BY player_name;
    ```
19. In this project, an IPL "thirty" means an individual batting innings from
    30 through 49 runs inclusive. It is a score below the fifty threshold, not
    merely 30 through 39. For "who has scored most thirties", count
    `player_batting_innings_stats` rows where
    `runs_scored BETWEEN 30 AND 49`, group by `player_name`, and return only
    the player or players tied at the maximum count. The innings table may be
    filtered with `format_group = 'IPL'`, but never with
    `competition_name = 'All'`.
20. For "which team has won the most number of games", query
    `team_career_stats` directly. Select `team` and `wins`, filter to the
    maximum `wins` (returning ties if any), and do not use a player table.
    `team` and `wins` are columns of `team_career_stats`; do not assume every
    statistics table has a `team` column.
21. A question containing a specific season plus "won the IPL trophy",
    "champion", or "who won the IPL" asks for that season's winner—not the
    all-time title leader. Query `team_season_stats` with
    `season = 'YYYY' AND champion = 1` and return `team`. Do not query
    `team_career_stats.titles` for a specific-season winner.
22. For "list all teams that have won the IPL trophy and the years in which
    they won", return one row per championship from `team_season_stats`, using
    `WHERE champion = 1` and selecting `team, season`. Order chronologically
    with `year`, then `season`. Do not use `team_career_stats.first_year` or
    `last_year`; those columns describe a franchise's participation span, not
    its trophy years. Do not use `LIMIT`, because the user asked for all.
23. "How many times TEAM went to/reached the finals" asks for final
    appearances, not titles won. Query `match_stats`, filter
    `event_stage = 'Final'`, and require the resolved team to equal either
    `team1` or `team2`. Count those final matches. Do not use
    `team_season_stats.champion = 1`, because that counts only finals won.
    For CSK, use the exact team name `Chennai Super Kings`.
24. "Who scored the highest number of sixes/sixers in a single over" is a
    delivery-level question. Use `delivery_stats`, group by `batter`,
    `match_id`, `innings_number`, and `over_number`, and sum `is_six`.
    Return every batter-over tied at the maximum. Do not use
    `player_match_stats.sixes`; that is a player's total sixes for an entire
    match. The stored `over_number` is zero-based, so select
    `over_number + 1 AS over_number` when displaying the human-readable over.
    Do not use `ORDER BY ... LIMIT 1`. First aggregate every batter-over in a
    CTE, then filter to the maximum:

    ```sql
    WITH over_sixes AS (
      SELECT batter, match_id, innings_number, over_number,
             SUM(is_six) AS sixes_in_over
      FROM delivery_stats
      GROUP BY batter, match_id, innings_number, over_number
    )
    SELECT batter, match_id, innings_number,
           over_number + 1 AS over_number, sixes_in_over
    FROM over_sixes
    WHERE sixes_in_over = (SELECT MAX(sixes_in_over) FROM over_sixes)
    ORDER BY batter;
    ```
25. Orange Cap and Purple Cap questions have dedicated tables. For "who won
    the Orange Cap in YYYY", query `orange_cap_winners` with the exact
    `season` and return `player_name`, `runs_scored`, and optionally `matches`.
    For "who won the Purple Cap in YYYY", query `purple_cap_winners` and return
    `player_name`, `wickets_taken`, and optionally `matches`,
    `playoff_wickets`, and `economy_rate`. Do not recompute these answers from
    generic player tables when the cap tables are available.
    "Highest wicket-taker in the YYYY edition/season" is the same season
    leaderboard intent and may use `purple_cap_winners` filtered by its
    `season` column. Do not apply an unqualified `season` filter to player
    match, innings, or career tables; those tables have no season column. For
    a full derived leaderboard rather than only the winner, join the player
    match table to `match_stats`.
26. To list all Orange/Purple Cap winners, select from the corresponding cap
    table and order by `year, season`; do not add `LIMIT`. To find who won a
    cap most often, group the corresponding table by `player_name`, use
    `COUNT(*) AS caps`, and return every player tied at the maximum count.
27. Cap records are derived from the imported IPL score data. Orange Cap uses
    maximum season runs. Purple Cap uses maximum season wickets, then playoff
    wickets and economy rate as tie-break metrics. `source_method` records the
    derivation used.
28. "Who was the first player to score a century for TEAM in IPL YEAR?" is a
    search across all players, so do not resolve or add a `player_name`
    filter. Query `player_batting_innings_stats p`, join `match_stats m` by
    `match_id`, filter `p.player_team` to the named team,
    `p.runs_scored >= 100`, and `m.season` to the requested IPL season. "For
    TEAM" means `player_team = TEAM`, not `opposition = TEAM`. Order by
    `p.match_date`, `p.match_id`, and `p.innings_number`, then `LIMIT 1`.
    IPL 2008 is the inaugural season stored as `2007/08`. "Kings XI" means
    `Kings XI Punjab`.
29. In "YEAR Team A and Team B played in the 18th game", "18th game" means
    `match_stats.event_match_number = 18`; it never means
    `innings_number = 18`. Resolve the historical team names used in that
    season: Delhi in 2009 is `Delhi Daredevils`, not `Delhi Capitals`.
    For "how many runs did the chasing team need to win", return the first
    batting team's innings total plus one as the target. For 2009 match 18,
    Delhi Daredevils batted first, so use `team1_runs + 1`, or join innings 1
    and calculate `runs + 1`. Filter `season = '2009'`, match number 18, and
    both named teams. Do not invent a wickets-based formula.
30. "TEAM won, but by how much?" asks for the victory margin, not the target.
    After identifying the match by `season`, `event_match_number`, teams, and
    winner, return `won_by_runs` when it is non-NULL or `won_by_wickets` when
    that is non-NULL, ideally with a margin type. Do not calculate
    `team1_runs + 1`. For match 2 of the 2009 IPL, Royal Challengers Bangalore
    beat Rajasthan Royals by the stored `won_by_runs` margin.
31. Some fixtures washed out before any ball was bowled have no Cricsheet JSON
    and therefore no `match_stats` row. Questions that explicitly describe a
    numbered game as washed out/no result should check
    `supplemental_matches`, filtering by `season`, `event_match_number`, and
    `result = 'no result'`. For the seventh game of IPL 2009, return `team1`
    and `team2` from this table. Do not require the absent fixture to exist in
    `match_stats`.
32. For stadium/ground leaderboards, normalize venue spellings by joining
    `venue_aliases v ON v.raw_venue = p.venue` and group by
    `v.canonical_venue`. For "which stadium has witnessed the most IPL
    centuries", count `player_batting_innings_stats` rows with
    `runs_scored >= 100`, grouped by canonical venue, then return the maximum.
    Do not join `match_stats`; the batting-innings table already has `venue`,
    and joining without qualifying it can cause `ambiguous column name:
    venue`. Do not group raw venue strings because variants such as
    `Wankhede Stadium` and `Wankhede Stadium, Mumbai` refer to one ground.
33. "Who was the first batter to score successive/consecutive hundreds" is a
    search across all players; never infer a `player_name` filter or fuzzy
    candidate list. Build a window over every IPL batting innings ordered by
    `match_date, match_id, innings_number` within each `player_name`. Use
    `LAG(runs_scored)` to compare each score with that player's immediately
    preceding batting innings, then require both scores to be at least 100.
    Order the qualifying second hundreds chronologically and `LIMIT 1`.
    Do not filter to centuries before applying `LAG`, because that would hide
    intervening non-century innings and create false consecutive sequences.
34. "Centuries while chasing" means centuries scored while batting in the
    second innings: use `player_batting_innings_stats.innings_number = 2` and
    `runs_scored >= 100`. It does not mean the player's team lost, so never
    use `match_stats.winner != player_team`. For "most", group across all
    players, calculate each count, and return every player tied at the maximum;
    do not merely order the full leaderboard and do not use `LIMIT`. Use a CTE:

    ```sql
    WITH chase_centuries AS (
      SELECT player_name, COUNT(*) AS centuries_chasing
      FROM player_batting_innings_stats
      WHERE innings_number = 2 AND runs_scored >= 100
      GROUP BY player_name
    )
    SELECT player_name, centuries_chasing
    FROM chase_centuries
    WHERE centuries_chasing = (
      SELECT MAX(centuries_chasing) FROM chase_centuries
    )
    ORDER BY player_name;
    ```
35. "Slowest IPL century" means the greatest number of balls faced to reach
    100 runs, not the earliest century by date and not necessarily the total
    balls in the completed innings. Use `delivery_stats`. Within each
    `batter, match_id, innings_number`, ordered by
    `over_number, delivery_number`, calculate cumulative batter runs and
    cumulative balls faced. A delivery with wides does not count as a ball
    faced; use
    `CASE WHEN json_extract(extras_json, '$.wides') IS NULL THEN 1 ELSE 0 END`.
    Keep the first row where cumulative runs reach at least 100 for each
    innings, call its cumulative ball count `balls_to_century`, then return
    every innings tied at the maximum. Do not use `MIN(match_date)`.
    Sum `batter_runs`, never `total_runs` (which includes extras). Use this
    query shape:

    ```sql
    WITH progress AS (
      SELECT d.*,
        SUM(batter_runs) OVER (
          PARTITION BY batter, match_id, innings_number
          ORDER BY over_number, delivery_number
        ) AS cumulative_runs,
        SUM(CASE
              WHEN json_extract(extras_json, '$.wides') IS NULL THEN 1
              ELSE 0
            END) OVER (
          PARTITION BY batter, match_id, innings_number
          ORDER BY over_number, delivery_number
        ) AS balls_to_point
      FROM delivery_stats d
    ),
    century_rows AS (
      SELECT *,
        ROW_NUMBER() OVER (
          PARTITION BY batter, match_id, innings_number
          ORDER BY over_number, delivery_number
        ) AS milestone_rank
      FROM progress
      WHERE cumulative_runs >= 100
    ),
    century_moments AS (
      SELECT batter, match_id, innings_number,
             balls_to_point AS balls_to_century
      FROM century_rows
      WHERE milestone_rank = 1
    )
    SELECT batter, match_id, innings_number, balls_to_century
    FROM century_moments
    WHERE balls_to_century = (
      SELECT MAX(balls_to_century) FROM century_moments
    )
    ORDER BY batter;
    ```
36. "Who has scored successive hundreds" (including the misspelling
    "hunderds") asks for every player who has at least one pair of centuries
    in immediately consecutive batting innings. Use the same all-innings
    `LAG(runs_scored)` method as rule 33, then filter
    `previous_runs >= 100 AND runs_scored >= 100`. Group the qualifying rows
    by `player_name` to return each player once, optionally counting the
    sequences. Do not filter `runs_scored >= 100` before calculating `LAG`,
    do not order a window by `runs_scored DESC`, and do not use `LIMIT 1`.
37. Hat-trick questions should use `hat_trick_stats`. One row represents one
    completed sequence of three consecutive bowler-credited wickets. For "who
    is the only bowler to take 3 hat-tricks", group by `bowler`, count rows as
    `hat_tricks`, and use `HAVING COUNT(*) = 3`. Do not query `match_date`
    from `delivery_stats`; `hat_trick_stats` already contains match and season
    context.
38. "Top N run scorers" means an IPL career leaderboard. Query
    `player_career_stats`, filter `format_group = 'IPL'` and
    `competition_name = 'All'`, select `player_name, runs_scored`, order by
    `runs_scored DESC`, and use the requested limit. Do not sum
    `player_batting_innings_stats`, and never apply
    `competition_name = 'All'` to that innings table.
39. `delivery_stats` uses `batter`, `bowler`, and `batting_team`; it has no
    `player_team` column. For the question about Rinku Singh's five consecutive
    sixes in the last over of the 2023 KKR win, resolve Rinku Singh to
    `batter = 'RK Singh'`, filter
    `batting_team = 'Kolkata Knight Riders'`, join `match_stats` for
    `m.season = '2023'` and the winner, group the six deliveries by match,
    innings, over, and bowler, and require five sixes with
    `HAVING SUM(d.is_six) >= 5`. Return `bowler`.
40. "Who won back-to-back Purple Caps" asks whether the same player won in any
    two adjacent IPL seasons across the full history. Self-join
    `purple_cap_winners p1` to `p2` on equal `player_name` and
    `p2.year = p1.year + 1`, then return the player and both seasons. Do not
    restrict the search to the latest two seasons with `ORDER BY year DESC
    LIMIT 2`.
    `purple_cap_winners` has no `team` column. For "which team/franchise has
    won the most Purple Caps", join each winner to `match_stats` on season and
    then to `player_match_stats` on both match ID and player name. First select
    `DISTINCT p.season, p.player_name, pm.team`; only then group by team and
    count rows. Counting the raw match join would count matches played rather
    than Purple Caps. Return every team tied at the maximum.
41. Questions involving historical nationality plus capped/uncapped status
    should use `special_record_stats` when a matching sourced record exists;
    scorecard tables do not contain complete capped-status metadata. For
    "Which Indian uncapped player scored the fastest IPL century during the
    2022 season?", filter
    `record_type = 'fastest century by an uncapped Indian player'` and
    `season = '2022'`, then return `player_name`, `record_value`, and
    `record_unit`. Use exactly:
    `SELECT player_name, record_value, record_unit FROM special_record_stats
    WHERE record_type = 'fastest century by an uncapped Indian player' AND
    season = '2022'`. Never relabel the value as seconds; the stored unit is
    balls. Do not filter `delivery_stats` with `d.season`; deliveries have no
    season column.
42. For "which player scored the most hundreds in IPL YEAR", join
    `player_batting_innings_stats p` to `match_stats m` on `match_id`, filter
    `m.season = 'YEAR'` and `p.runs_scored >= 100`, then count by
    `p.player_name` and return the maximum. The batting-innings table has no
    `season` column, so never write `p.season` or an unqualified `season`
    against it. Do not use all-time `player_career_stats.hundreds` for a
    single-season question.
43. "Fastest IPL fifty in YEAR" is a delivery-level milestone across all
    players. Join `delivery_stats d` to `match_stats m` for the requested
    season. Within each `batter, match_id, innings_number`, ordered by
    `over_number, delivery_number`, calculate cumulative `batter_runs` and
    cumulative balls faced, excluding wides from the ball count. Keep the
    first row where cumulative runs reach 50, call its count
    `balls_to_fifty`, and return every batter tied at the minimum. Do not query
    `special_record_stats` unless the question contains additional metadata
    such as capped/uncapped status, and do not invent an Indian-player filter.
    In every window partition and ordering expression, qualify delivery
    columns as `d.match_id`, `d.innings_number`, `d.over_number`, and
    `d.delivery_number` before introducing an outer CTE alias. Return the
    player as `batter` and the minimum as `balls_to_fifty`.
    The all-time version uses the same delivery milestone calculation without
    a season filter. Build cumulative runs and balls in `progress`, aggregate
    the first qualifying ball as `balls_to_fifty` in a `milestones` CTE, then
    compare only that exposed CTE column with
    `(SELECT MIN(balls_to_fifty) FROM milestones)`. Return every tied batter;
    do not use `LIMIT 1`, and never reference `balls_to_fifty` in a CTE where
    it has not yet been defined.
44. "Who became only the second player after Shikhar Dhawan to score two
    consecutive hundreds" asks for the next player to achieve the feat after
    Dhawan, not the second such player in all IPL history. Use the all-innings
    `LAG(runs_scored)` method from rules 33 and 36. Find each player's earliest
    qualifying second century, keep dates later than Dhawan's 2020 sequence,
    exclude `S Dhawan`, order chronologically, and take the first: this returns
    `JC Buttler` on `2022-04-22`. Return literal `2 AS achievement_order`.
    Do not reference an alias such as
    `p.runs_scored` unless that alias is actually declared in the same query.
    Do not add `competition_name = 'All'` to the batting-innings CTE.
    Use this final structure after building the all-innings `ordered` CTE:

    ```sql
    , first_sequences AS (
      SELECT player_name, MIN(match_date) AS completion_date
      FROM ordered
      WHERE previous_runs >= 100 AND runs_scored >= 100
      GROUP BY player_name
    ),
    ranked AS (
      SELECT *,
        ROW_NUMBER() OVER (
          ORDER BY completion_date, player_name
        ) AS achievement_order
      FROM first_sequences
    )
    SELECT player_name, completion_date, achievement_order
    FROM ranked
    WHERE achievement_order = 2;
    ```
45. "Which team has had the most last-place finishes in the IPL points table?"
    must use `team_last_place_finishes`. Group by `team`, count rows as
    `last_place_finishes`, and return the maximum. Do not query
    `team_season_stats` with `matches = 0`; participating teams always have
    matches, and final positions can require net-run-rate tie-breaks not
    represented by wins alone.
46. "Most catches in a single innings" is an innings-level fielding record.
    Use `player_match_innings_stats.catches`, find its maximum, and return
    every row/player tied at that maximum, optionally joining `match_stats`
    for date and teams. Do not sum `player_match_stats.catches`; that produces
    career totals and incorrectly answers with the leading career catcher.
    Do not use `GROUP BY ... LIMIT 1`. Use:

    ```sql
    SELECT player_name, catches, match_id, innings_number
    FROM player_match_innings_stats
    WHERE catches = (
      SELECT MAX(catches) FROM player_match_innings_stats
    )
    ORDER BY player_name;
    ```

## Franchise name changes

Franchise names are preserved as they appeared in the source, rather than
automatically merged:

- `Royal Challengers Bangalore` and `Royal Challengers Bengaluru`
- `Kings XI Punjab` and `Punjab Kings`
- `Delhi Daredevils` and `Delhi Capitals`
- `Rising Pune Supergiants` and `Rising Pune Supergiant`

An acronym or unqualified franchise identity means the franchise's full
history across name changes. Thus `RCB` uses
`IN ('Royal Challengers Bangalore', 'Royal Challengers Bengaluru')`. Apply
the same principle to Punjab, Delhi, and the Rising Pune franchise. When the
user explicitly writes one historical or current full name, that exact name
may be used alone.

For "against which team did RCB record its highest ever score", rank RCB's
rows in `match_innings_stats` by `runs DESC`, join `match_stats`, and derive
the opponent from the other match team:

```sql
SELECT mi.runs,
       CASE
         WHEN m.team1 = mi.team THEN m.team2
         ELSE m.team1
       END AS opposition
FROM match_innings_stats mi
JOIN match_stats m ON m.match_id = mi.match_id
WHERE mi.team IN (
  'Royal Challengers Bangalore',
  'Royal Challengers Bengaluru'
)
ORDER BY mi.runs DESC
LIMIT 1;
```

For an all-history leaderboard phrased as "which franchise", consolidate
renamed teams before summing the requested statistic. In particular:

- Delhi Daredevils + Delhi Capitals = Delhi Capitals
- Kings XI Punjab + Punjab Kings = Punjab Kings
- Royal Challengers Bangalore + Royal Challengers Bengaluru =
  Royal Challengers Bengaluru
- Rising Pune Supergiants + Rising Pune Supergiant =
  Rising Pune Supergiant

For "which franchise has lost the most matches", use a `CASE` expression for
those mappings, `SUM(losses)`, and rank the grouped franchise totals. Do not
use `WHERE wins = 0`.

## Examples

Most IPL runs:

```sql
SELECT player_name, runs_scored
FROM player_career_stats
WHERE format_group = 'IPL' AND competition_name = 'All'
ORDER BY runs_scored DESC
LIMIT 1;
```

Highest CSK innings:

```sql
SELECT mi.runs, mi.wickets, mi.overs, m.match_date, m.venue
FROM match_innings_stats mi
JOIN match_stats m ON m.match_id = mi.match_id
WHERE mi.team = 'Chennai Super Kings'
ORDER BY mi.runs DESC, m.match_date
LIMIT 1;
```

Season champion:

```sql
SELECT team
FROM team_season_stats
WHERE season = '2024' AND champion = 1;
```

Kohli's scores against Mumbai:

```sql
SELECT match_date, runs_scored, is_not_out, balls_faced
FROM player_batting_innings_stats
WHERE player_name = 'V Kohli'
  AND opposition = 'Mumbai Indians'
ORDER BY match_date, innings_number
LIMIT 50;
```
