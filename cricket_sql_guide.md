# CricketStats SQL Guide

Use this guide when converting user questions into SQLite queries for
`cricketstats.sqlite`.

## Core Cricket Concepts

- A Test match is one match.
- A Test match can have up to 4 team innings.
- A player can bat in more than one innings in the same Test match.
- Innings is not the same as match.
- If the user asks about a player's first Test match, first find the earliest
  `match_id` for that player where `format_group = 'Test'`, then use every
  batting innings row for that player in that `match_id`.
- If the user asks for match-level totals such as runs, fours, sixes, balls, or
  catches in a match, aggregate all rows for that player and `match_id`.
- Do not answer first-match questions by returning only the earliest innings row.
- If the question says "in each innings", "both innings", "two innings", or
  "100 in each innings", it is asking about multiple batting innings in the same
  Test match. Use `GROUP BY player_name, match_id` and a `HAVING` clause.
- If the question says "Indian player", "Australian player", "England player",
  or another nationality/country adjective, it is asking for players representing
  that team. Do not treat the nationality as a player name. The team column
  depends on the selected table: `player_batting_innings_stats` uses
  `player_team`, while `player_match_stats` and
  `player_match_innings_stats` use `team`. Career tables have neither column;
  restrict a career row to a national team with an `EXISTS` subquery against
  `player_match_stats`, matching `player_name` and filtering its `team`.
- For first/earliest occurrence questions, do not select `MIN(match_date)` next
  to non-aggregated columns from the same CTE. SQLite can return a mismatched
  row. Filter to the qualifying rows, then use `ORDER BY match_date ASC,
  match_id ASC, innings_number ASC LIMIT 1`.

## Table Selection

- Use `player_batting_innings_stats` for batting innings questions such as runs,
  balls, fours, sixes, not outs, dismissal, opposition, venue, year, and first
  match.
- Use `player_match_stats` for one row per player per match, especially
  match-level batting, bowling, and fielding totals.
- Use `player_match_innings_stats` for innings-level batting, bowling, and
  fielding details.
- Use `player_career_stats` for total career wickets by format. This table has
  `wickets_taken`, `best_bowling`, `bowling_average`, and `five_wickets`.
- Use `player_match_stats` for wickets taken by a player in a specific match.
  This table has `wickets_taken`.
  It stores the player's team in the column `team`, not `player_team`.
  Never use `player_team` with `player_match_stats`, including in `SELECT`,
  `CASE`, `WHERE`, or join expressions.
- Use `player_match_innings_stats` for wickets taken by a player in a specific
  innings. This table has `wickets_taken`.
  It stores the player's team in the column `team`, not `player_team`.
- Do not use `player_batting_innings_stats` for wickets. It is batting-only and
  does not have `wickets_taken`.
- Use `player_career_stats` for career summaries by format, such as Test career
  runs, matches, average, hundreds, wickets, catches.
- For a career fielding total such as catches or stumpings, select the
  corresponding column directly from the `competition_name = 'All'` career
  row. Do not use `COUNT(*)` or `SUM(catches)`/`SUM(stumpings)`; those aggregate
  career rows rather than representing the stored career total.
- Use `player_career_group_stats` for grouped summaries by opposition, year, or
  competition.
- Use `match_stats` for match metadata such as teams, match date, venue, winner,
  result, and match type.
- For "which team won the most matches", group by `match_stats.winner` and
  exclude `winner IS NULL` and blank winners. Null winners represent matches
  without a recorded winner and are not a team.
- Use `match_innings_stats` for team innings totals.
  This table does not have `match_type`; join `match_stats` and use
  `m.match_type = 'Test'` when filtering Tests.
- When a highest team-innings question names a team, filter
  `match_innings_stats.team` to that exact team before ordering by
  `match_innings_stats.runs`. For example, "India's highest Test innings total"
  requires `mi.team = 'India'`; do not return the overall Test record.

Question: What is the highest ever total runs in a single innings by any team in
Test cricket?

This asks for the highest team innings total, not an individual batting innings.
Use `match_innings_stats.runs` and join `match_stats` for match type and match
metadata. Do not put `match_type` directly on `match_innings_stats`.

Pattern:

```sql
SELECT
  mi.match_id,
  mi.innings_number,
  mi.team,
  mi.runs AS total_runs,
  m.match_date,
  m.team1,
  m.team2,
  m.venue
FROM match_innings_stats mi
JOIN match_stats m ON m.match_id = mi.match_id
WHERE m.match_type = 'Test'
ORDER BY mi.runs DESC, mi.match_id ASC, mi.innings_number ASC
LIMIT 1;
```

## Location Questions

- "Did PLAYER play a Test in COUNTRY?" asks about match location, not the
  player's nationality/team and not the opponent.
- Use `player_match_stats` joined to `match_stats`.
- Filter the player with `p.player_name`.
- Filter Tests with `m.match_type = 'Test'`.
- Filter country/location with `m.city` or `m.venue`. Do not use
  `p.player_team`; `player_match_stats` does not have that column. Do not use
  `p.team` as a location filter; `p.team` is the player's team.
- The database has no country column. For India, use Indian host cities and old
  city names in `m.city` or `m.venue`: Bombay, Mumbai, Calcutta, Kolkata,
  Madras, Chennai, Delhi, Kanpur, Bangalore, Bengaluru, Hyderabad, Ahmedabad,
  Nagpur, Mohali, Chandigarh, Pune, Ranchi, Rajkot, Indore, Lucknow,
  Dharamsala, Cuttack, Guwahati, Jaipur, Jamshedpur, Visakhapatnam.

Question: Did Bradman play any Test in India?

Pattern:

```sql
SELECT
  COUNT(*) AS tests_in_india
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'DG Bradman'
  AND m.match_type = 'Test'
  AND (
    m.city IN (
      'Bombay', 'Mumbai', 'Calcutta', 'Kolkata', 'Madras', 'Chennai',
      'Delhi', 'Kanpur', 'Bangalore', 'Bengaluru', 'Hyderabad',
      'Ahmedabad', 'Nagpur', 'Mohali', 'Chandigarh', 'Pune', 'Ranchi',
      'Rajkot', 'Indore', 'Lucknow', 'Dharamsala', 'Cuttack', 'Guwahati',
      'Jaipur', 'Jamshedpur', 'Visakhapatnam'
    )
    OR lower(m.venue) LIKE lower('%India%')
  );
```

For yes/no count questions, do not use `GROUP BY`; `COUNT(*)` without grouping
returns `0` when there are no matching matches. If this returns a count of 0,
the player did not play a Test in India according to the database.

## Common Query Patterns

Question: Test match listing for PLAYER

Use `player_match_stats` joined to `match_stats`, because this asks for one row
per match. If a known alias maps to an exact database `player_name`, use exact
equality instead of `LIKE`.

Pattern:

```sql
SELECT
  m.match_date,
  p.match_id,
  CASE WHEN m.team1 = p.team THEN m.team2 ELSE m.team1 END AS opposition,
  m.venue,
  p.runs_scored,
  p.balls_faced,
  p.fours,
  p.sixes,
  p.wickets_taken,
  p.overs_bowled,
  p.runs_conceded,
  p.catches
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND m.match_type = 'Test'
ORDER BY m.match_date ASC, p.match_id ASC
LIMIT 50;
```

Question: How many runs did PLAYER score in his first Test match?

Pattern:

```sql
WITH first_match AS (
  SELECT match_id
  FROM player_batting_innings_stats
  WHERE player_name = 'PLAYER_NAME'
    AND format_group = 'Test'
  ORDER BY match_date ASC, match_id ASC
  LIMIT 1
)
SELECT
  p.player_name,
  p.match_id,
  MIN(p.match_date) AS match_date,
  MAX(p.opposition) AS opposition,
  SUM(p.runs_scored) AS total_runs
FROM player_batting_innings_stats p
JOIN first_match f ON f.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
GROUP BY p.player_name, p.match_id;
```

Question: How many fours did PLAYER score in his first Test match?

Use the same first-match CTE and `SUM(p.fours)`.

Question: Show PLAYER innings in his first Test match.

Use the same first-match CTE and return rows ordered by `innings_number`.

Question: Show/list PLAYER innings where he scored 100 or more.

Use the resolved database `player_name` from context. Do not use the user's raw
full name if the database uses initials.

```sql
SELECT
  player_name,
  match_id,
  innings_number,
  runs_scored,
  is_not_out,
  match_date,
  opposition,
  venue
FROM player_batting_innings_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND runs_scored >= 100
ORDER BY match_date ASC, innings_number ASC
LIMIT 50;
```

Question: Who was the first Indian player to score a hundred in a Test match?

This asks for the earliest individual batting innings of 100+ by a player
representing India in Tests. It does not ask for hundreds in both innings.

Pattern:

```sql
SELECT
  player_name,
  match_id,
  match_date,
  opposition,
  innings_number,
  runs_scored,
  is_not_out,
  venue
FROM player_batting_innings_stats
WHERE format_group = 'Test'
  AND player_team = 'India'
  AND runs_scored >= 100
ORDER BY match_date ASC, match_id ASC, innings_number ASC
LIMIT 1;
```

Question: Which Indian player has scored the most double-centuries in Tests?

A double-century is one batting innings of 200 or more. Use
`player_batting_innings_stats`, filter the national team with
`player_team = 'India'`, group by player, and count innings with
`runs_scored >= 200`. Do not use `player_career_stats.hundreds`; that column
counts every score of 100 or more, including scores below 200. “Indian player”
is a team-wide filter, not a player name to resolve.

```sql
SELECT
  player_name,
  COUNT(*) AS test_double_centuries
FROM player_batting_innings_stats
WHERE format_group = 'Test'
  AND player_team = 'India'
  AND runs_scored >= 200
GROUP BY player_name
ORDER BY test_double_centuries DESC, player_name ASC
LIMIT 1;
```

Question: Which player has scored the most triple-centuries in Test cricket?

A triple-century is one batting innings of 300 or more. This is a ranking over
all players, so do not infer or add any `player_name` filter. Count qualifying
rows in `player_batting_innings_stats` and return every player tied for the
highest count. Do not use `LIMIT 1`, because multiple players can share the
record.

```sql
WITH triple_centuries AS (
  SELECT
    player_name,
    COUNT(*) AS triple_hundreds
  FROM player_batting_innings_stats
  WHERE format_group = 'Test'
    AND runs_scored >= 300
  GROUP BY player_name
)
SELECT
  player_name,
  triple_hundreds
FROM triple_centuries
WHERE triple_hundreds = (
  SELECT MAX(triple_hundreds)
  FROM triple_centuries
)
ORDER BY player_name ASC;
```

Question: Who was the first player to score 100 or more runs in each innings of a
Test match?

Important:

- "Each innings of a Test" means the same player scored 100+ in two batting
  innings within the same `match_id`.
- Do not use only `SELECT DISTINCT player_name WHERE runs_scored >= 100`; that
  only finds players who scored one century in one innings.
- Use `player_batting_innings_stats`, group by `player_name` and `match_id`, and
  use `HAVING COUNT(*) >= 2` after filtering `runs_scored >= 100`.
- Sort by `match_date` to find the first occurrence.

Pattern:

```sql
WITH centuries AS (
  SELECT
    player_name,
    match_id,
    match_date,
    opposition,
    innings_number,
    runs_scored,
    is_not_out,
    venue
  FROM player_batting_innings_stats
  WHERE format_group = 'Test'
    AND runs_scored >= 100
),
both_innings AS (
  SELECT
    player_name,
    match_id,
    MIN(match_date) AS match_date,
    MAX(opposition) AS opposition,
    COUNT(*) AS centuries_in_match,
    GROUP_CONCAT(
      runs_scored || CASE WHEN is_not_out = 1 THEN '*' ELSE '' END,
      ', '
    ) AS scores,
    MAX(venue) AS venue
  FROM centuries
  GROUP BY player_name, match_id
  HAVING COUNT(*) >= 2
)
SELECT
  player_name,
  match_id,
  match_date,
  opposition,
  scores,
  venue
FROM both_innings
ORDER BY match_date ASC, match_id ASC
LIMIT 1;
```

Question: What are the runs scored by PLAYER when he scored centuries in each
innings of a Test match?

This asks for the player's individual innings scores in matches where that same
player made 100+ in two batting innings of the same Test. Return the qualifying
innings rows. Do not group by `innings_number`; that prevents the query from
seeing both innings in the same match. Do not use `SUM(runs_scored)` unless the
user explicitly asks for a total.

Pattern:

```sql
WITH century_innings AS (
  SELECT
    player_name,
    match_id,
    match_date,
    opposition,
    innings_number,
    runs_scored,
    is_not_out,
    venue
  FROM player_batting_innings_stats
  WHERE player_name = 'PLAYER_NAME'
    AND format_group = 'Test'
    AND runs_scored >= 100
),
both_innings_matches AS (
  SELECT
    player_name,
    match_id
  FROM century_innings
  GROUP BY player_name, match_id
  HAVING COUNT(*) >= 2
)
SELECT
  c.match_id,
  c.match_date,
  c.opposition,
  c.innings_number,
  c.runs_scored,
  c.is_not_out,
  c.venue
FROM century_innings c
JOIN both_innings_matches b
  ON b.player_name = c.player_name
 AND b.match_id = c.match_id
ORDER BY c.match_date ASC, c.innings_number ASC;
```

Question: How many times did PLAYER score centuries in each innings of a Test
match?

This asks for the number of Tests where the player scored 100+ in two batting
innings. First find qualifying matches by grouping century innings by
`player_name, match_id`, then count those match rows in an outer query. Do not
return `COUNT(*)` grouped by `match_id`; that returns the number of century
innings in each qualifying match, usually `2`, instead of the number of matches.

Pattern:

```sql
WITH century_matches AS (
  SELECT
    player_name,
    match_id
  FROM player_batting_innings_stats
  WHERE player_name = 'PLAYER_NAME'
    AND format_group = 'Test'
    AND runs_scored >= 100
  GROUP BY player_name, match_id
  HAVING COUNT(*) >= 2
)
SELECT
  COUNT(*) AS times_centuries_in_each_innings
FROM century_matches;
```

Question: Who was the first Indian player to score 100 or more runs in each
innings of a Test match?

Use the same pattern, but add `player_team = 'India'` in the `centuries` CTE.
For other countries, use the corresponding `player_team` value.

Pattern:

```sql
WITH centuries AS (
  SELECT
    player_name,
    match_id,
    match_date,
    opposition,
    innings_number,
    runs_scored,
    is_not_out,
    venue
  FROM player_batting_innings_stats
  WHERE format_group = 'Test'
    AND player_team = 'India'
    AND runs_scored >= 100
),
both_innings AS (
  SELECT
    player_name,
    match_id,
    MIN(match_date) AS match_date,
    MAX(opposition) AS opposition,
    COUNT(*) AS centuries_in_match,
    GROUP_CONCAT(
      runs_scored || CASE WHEN is_not_out = 1 THEN '*' ELSE '' END,
      ', '
    ) AS scores,
    MAX(venue) AS venue
  FROM centuries
  GROUP BY player_name, match_id
  HAVING COUNT(*) >= 2
)
SELECT
  player_name,
  match_id,
  match_date,
  opposition,
  scores,
  venue
FROM both_innings
ORDER BY match_date ASC, match_id ASC
LIMIT 1;
```

Question: Show PLAYER Test career summary.

Use `player_career_stats` with:

```sql
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
```

Question: What is PLAYER's Test batting average?

Use `player_career_stats.batting_average`. Cricket batting average is not
`AVG(runs_scored / balls_faced)`. Do not use balls faced to calculate batting
average. For Test career averages, use the precomputed career row:

```sql
SELECT
  player_name,
  matches,
  batting_innings,
  not_outs,
  runs_scored,
  highest_score,
  batting_average,
  hundreds,
  fifties
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
ORDER BY runs_scored DESC, batting_innings DESC
LIMIT 1;
```

Question: How many Test hundreds did PLAYER score?

Use `player_career_stats.hundreds`. Do not count rows in
`player_career_group_stats`; those rows are grouped summaries, not individual
hundreds. Do not use `COUNT(*)` on `player_career_stats`; that counts career
rows, not hundreds. Select the `hundreds` column. When duplicate rows can match,
order by batting data before limiting.

```sql
SELECT
  player_name,
  hundreds
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
ORDER BY runs_scored DESC, batting_innings DESC
LIMIT 1;
```

Question: How many Test hundreds did PLAYER score against TEAM?

This asks for individual innings of 100+ against a specific opposition. Use
`player_batting_innings_stats`, because career totals in `player_career_stats`
are not broken down by opposition. Filter the opposition directly. Do not use
`player_team != 'TEAM'`; that only excludes players representing that team and
does not mean "against TEAM".

Pattern:

```sql
SELECT
  COUNT(*) AS hundreds_against_team
FROM player_batting_innings_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND opposition = 'TEAM'
  AND runs_scored >= 100;
```

Question: Which batsman has scored the most consecutive Test hundreds?

This asks for the longest streak of century innings in a player's chronological
Test batting innings. Build the sequence from all Test batting innings first;
do not filter to `runs_scored >= 100` before computing row numbers. If you
filter first, every hundred is adjacent to the next hundred and the query counts
total career hundreds instead of a consecutive streak.

Pattern:

```sql
WITH innings AS (
  SELECT
    player_name,
    match_id,
    match_date,
    innings_number,
    runs_scored,
    CASE WHEN runs_scored >= 100 THEN 1 ELSE 0 END AS is_hundred
  FROM player_batting_innings_stats
  WHERE format_group = 'Test'
),
marked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (
      PARTITION BY player_name
      ORDER BY match_date, match_id, innings_number
    ) -
    ROW_NUMBER() OVER (
      PARTITION BY player_name, is_hundred
      ORDER BY match_date, match_id, innings_number
    ) AS streak_group
  FROM innings
),
streaks AS (
  SELECT
    player_name,
    COUNT(*) AS consecutive_hundreds,
    MIN(match_date) AS start_date,
    MAX(match_date) AS end_date
  FROM marked
  WHERE is_hundred = 1
  GROUP BY player_name, streak_group
)
SELECT
  player_name,
  consecutive_hundreds,
  start_date,
  end_date
FROM streaks
ORDER BY consecutive_hundreds DESC, start_date ASC, player_name ASC
LIMIT 1;
```

Question: Which visiting batsman has scored the most Test centuries in COUNTRY?

This combines a location filter with a visiting-player filter. "In Australia"
means the match was played in Australia, not necessarily against Australia.
"Visiting batsman" means the player's team was not Australia. Use
`player_batting_innings_stats` for individual centuries, join `match_stats` for
location, and filter `p.player_team <> 'Australia'`.

Pattern:

```sql
SELECT
  p.player_name,
  p.player_team,
  COUNT(*) AS centuries_scored
FROM player_batting_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.format_group = 'Test'
  AND p.runs_scored >= 100
  AND p.player_team <> 'Australia'
  AND (
    m.city IN (
      'Sydney', 'Melbourne', 'Adelaide', 'Perth', 'Brisbane',
      'Hobart', 'Canberra', 'Darwin', 'Cairns', 'Gold Coast'
    )
    OR lower(m.venue) LIKE lower('%Sydney%')
    OR lower(m.venue) LIKE lower('%Melbourne%')
    OR lower(m.venue) LIKE lower('%Adelaide%')
    OR lower(m.venue) LIKE lower('%Perth%')
    OR lower(m.venue) LIKE lower('%Brisbane%')
    OR lower(m.venue) LIKE lower('%Hobart%')
  )
GROUP BY p.player_name, p.player_team
ORDER BY centuries_scored DESC, p.player_name ASC
LIMIT 1;
```

Question: How many overseas/abroad Test hundreds did PLAYER score?

This asks for the player's individual Test century innings outside the player's
home country. Use `player_batting_innings_stats` for the centuries and join
`match_stats` for match location. Overseas/abroad is player-specific: exclude
the player's own home country, not always India. For an Indian player such as
Gavaskar, overseas means the match was not played in India. For an Australian
player such as Bradman, abroad means the match was not played in Australia. Use
`NOT (...)` around the matching home-country location predicate.

Pattern:

```sql
SELECT
  COUNT(*) AS overseas_test_hundreds
FROM player_batting_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND p.format_group = 'Test'
  AND p.runs_scored >= 100
  AND NOT (
    m.city IN (
      'Bombay', 'Mumbai', 'Calcutta', 'Kolkata', 'Madras', 'Chennai',
      'Delhi', 'Kanpur', 'Bangalore', 'Bengaluru', 'Hyderabad',
      'Ahmedabad', 'Nagpur', 'Mohali', 'Chandigarh', 'Pune', 'Ranchi',
      'Rajkot', 'Indore', 'Lucknow', 'Dharamsala', 'Cuttack', 'Guwahati',
      'Jaipur', 'Jamshedpur', 'Visakhapatnam'
    )
    OR lower(m.venue) LIKE lower('%India%')
  );
```

For Bradman abroad, use the Australia location predicate, not the India
predicate:

```sql
SELECT
  COUNT(*) AS test_hundreds_abroad
FROM player_batting_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'DG Bradman'
  AND p.format_group = 'Test'
  AND p.runs_scored >= 100
  AND NOT (
    m.city IN (
      'Sydney', 'Melbourne', 'Adelaide', 'Perth', 'Brisbane',
      'Hobart', 'Canberra', 'Darwin', 'Cairns', 'Gold Coast'
    )
    OR lower(m.venue) LIKE lower('%Australia%')
  );
```

Question: How many catches did PLAYER take?

Use `player_career_stats.catches` for career catch totals by format. Do not use
`SUM(catches)` from `player_match_stats` for career totals unless the career
table is missing the needed row. If the format is not specified, prefer Test
career catches.

Pattern:

```sql
SELECT
  player_name,
  catches AS total_catches
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
ORDER BY catches DESC, matches DESC
LIMIT 1;
```

Question: Which Indian player has taken the most catches?

Use `player_career_stats.catches` for the stored career total and establish
India membership through `player_match_stats.team`. `player_career_stats` has
no `player_team` or `team` column, and `player_match_stats` uses `team`, never
`player_team`.

```sql
SELECT
  c.player_name,
  c.catches,
  c.matches
FROM player_career_stats c
WHERE c.format_group = 'Test'
  AND c.competition_name = 'All'
  AND c.catches > 0
  AND EXISTS (
    SELECT 1
    FROM player_match_stats pm
    WHERE pm.player_name = c.player_name
      AND pm.team = 'India'
  )
ORDER BY c.catches DESC, c.matches DESC, c.player_name ASC
LIMIT 1;
```

If the database has split batting/fielding rows for a player, resolve this as a
fielding question and prefer the row with the higher `catches`. For example,
Gavaskar's Test catches are under `player_name = 'Gavaskar'`, while
`SM Gavaskar` is the batting row with zero catches.

Question: How many wickets did PLAYER take?

If the user does not specify a format and the player is known mainly as a Test
player, prefer Test career wickets from `player_career_stats` where
`format_group = 'Test'` and `competition_name = 'All'`.
Use the `wickets_taken` column from `player_career_stats`; do not use
`SUM(wickets_taken)` from `player_match_stats` for career totals unless the
career table is missing the needed row.
Never use `COUNT(*)` for career wicket totals. `COUNT(*)` counts matching career
rows, so it will often return `1`; it does not return wickets.
For bowling career stats, prefer the row with `wickets_taken > 0` when more than
one career row matches the player's name/surname. Some players have an initialed
row with zero wickets and a surname-only row with their bowling career.
For a full-name wicket question, do not stop at the initial-plus-surname match if
a surname-only Test career row has more wickets. Example: "Richard Hadlee"
should resolve to the Hadlee Test bowling row with the highest `wickets_taken`,
not automatically to `RJ Hadlee`.

Pattern:

```sql
SELECT
  player_name,
  wickets_taken AS total_wickets
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
ORDER BY wickets_taken DESC, matches DESC
LIMIT 1;
```

Question: Has PLAYER taken any Test wicket?

This asks whether the player has a positive Test career wicket count. Use
`player_career_stats.wickets_taken`; do not use `COUNT(*)` on any table,
because that counts rows, not wickets.

Pattern:

```sql
SELECT
  player_name,
  wickets_taken AS test_wickets_taken,
  best_bowling,
  bowling_average
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
ORDER BY wickets_taken DESC, matches DESC
LIMIT 1;
```

If the database has split batting/bowling rows for a player, resolve this as a
bowling question and prefer the row with the higher `wickets_taken`. For example,
Gavaskar's Test wicket is under `player_name = 'Gavaskar'`, while
`SM Gavaskar` is the batting row with zero wickets.

Question: Get PLAYER's bowling record.

This asks for career bowling fields, not a mixed batting career summary. Use
`player_career_stats`, return bowling fields, filter to the Test career row
unless another format is specified, and require rows with wickets.

Pattern:

```sql
SELECT
  player_name,
  matches,
  wickets_taken,
  best_bowling,
  bowling_average,
  five_wickets
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
  AND wickets_taken > 0
ORDER BY wickets_taken DESC, matches DESC
LIMIT 1;
```

Never use `ORDER BY runs_scored DESC, batting_innings DESC` for bowling record,
bowling average, wickets, best bowling, or five-wicket questions.
When using `player_career_stats` for those bowling questions, always include
`AND wickets_taken > 0`.
Even when the resolved `player_name` is exact, keep
`ORDER BY wickets_taken DESC, matches DESC` before `LIMIT 1` so duplicate or
split career rows choose the bowling row.

Question: What is PLAYER's Test bowling average?

Use `player_career_stats.bowling_average`. Do not calculate bowling average from
match rows unless the career table lacks a row. For Dennis Lillee, use
`player_name = 'Lillee'`; the `DK Lillee` career row has zero wickets.

Pattern:

```sql
SELECT
  player_name,
  matches,
  wickets_taken,
  best_bowling,
  bowling_average,
  five_wickets
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
  AND wickets_taken > 0
LIMIT 1;
```

Pattern:

```sql
SELECT
  player_name,
  format_group,
  span,
  matches,
  wickets_taken,
  best_bowling,
  bowling_average,
  five_wickets
FROM player_career_stats
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND competition_name = 'All'
LIMIT 1;
```

If the user asks for wickets in a specific match, use `player_match_stats`.
Important: `player_match_stats` does not have `format_group`. To filter Tests
when using `player_match_stats`, join `match_stats` and use
`m.match_type = 'Test'`.

Question: How many fivefers did PLAYER take?

The terms "fivefer", "fivefers", "fifer", "fifers", "fiver", "fivers",
"five-for", "five-wicket haul", and "5 wickets per innings" all mean an
innings-level five-wicket haul. Use `player_match_innings_stats` joined to
`match_stats`.
Never use `player_match_stats`: its `wickets_taken` is the combined match
total, which can count a match where the bowler took fewer than five wickets in
each innings and can collapse two five-wicket innings in one match into one.
Do not use `player_batting_innings_stats` for wickets or bowling questions.

```sql
SELECT
  p.player_name,
  COUNT(*) AS five_wicket_innings
FROM player_match_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND m.match_type = 'Test'
  AND p.wickets_taken >= 5
GROUP BY p.player_name;
```

Question: Who has taken all 10 wickets in a Test match innings?

This asks for bowling innings where one bowler took all 10 wickets. Use
`player_match_innings_stats.wickets_taken`; in this table row, `player_name` is
the bowler for bowling innings stats. Do not use `dismissal_bowler`, and do not
group by `dismissal_bowler`.

Pattern:

```sql
SELECT
  p.player_name,
  p.team,
  p.match_id,
  p.innings_number,
  p.wickets_taken,
  p.runs_conceded,
  p.overs_bowled,
  m.match_date,
  m.team1,
  m.team2,
  m.venue
FROM player_match_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE m.match_type = 'Test'
  AND p.wickets_taken >= 10
ORDER BY m.match_date ASC, p.player_name ASC;
```

Question: How many wickets did PLAYER take by lbw/bowled/caught/etc.?

This asks about wickets credited to the bowler by dismissal type. In
`player_match_innings_stats`, `player_name` is the dismissed batter's row, and
`dismissal_bowler` is the bowler credited with the wicket. Do not use
`player_batting_innings_stats` for this.

```sql
SELECT
  COUNT(*) AS wickets_by_dismissal_type
FROM player_match_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.dismissal_bowler = 'PLAYER_NAME'
  AND lower(p.dismissal_kind) = 'lbw'
  AND m.match_type = 'Test';
```

Question: Which bowler has taken the wicket of PLAYER the most?

This asks who dismissed the named batter most often. The named player belongs in
`player_match_innings_stats.player_name` as the dismissed batter. The bowler is
stored in `dismissal_bowler`. Exclude rows where `dismissal_bowler` is null or
blank; otherwise not-outs, run-outs, absent hurt, and unknown/no-bowler rows can
be counted as a blank bowler.

Pattern:

```sql
SELECT
  p.dismissal_bowler,
  COUNT(*) AS wickets_taken
FROM player_match_innings_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'BATTER_NAME'
  AND m.match_type = 'Test'
  AND p.dismissal_bowler IS NOT NULL
  AND trim(p.dismissal_bowler) <> ''
GROUP BY p.dismissal_bowler
ORDER BY wickets_taken DESC, p.dismissal_bowler ASC
LIMIT 1;
```

For this question, resolve the user's player name as a batter. For example,
Gavaskar as the dismissed batter should use `SM Gavaskar`, not the surname-only
bowling/fielding row.
Dismissed-batter questions override bowling/fielding stat-aware name resolution:
the named player is the batter who got out. For "wicket of Gavaskar" or "who
dismissed Gavaskar", use `SM Gavaskar`.

Pattern:

```sql
SELECT
  p.player_name,
  p.wickets_taken,
  p.overs_bowled,
  p.runs_conceded,
  m.match_date,
  m.team1,
  m.team2,
  m.venue
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND m.match_type = 'Test'
ORDER BY m.match_date ASC
LIMIT 50;
```

Question: How many times did PLAYER take 10 wickets or more in a Test?

This asks for 10+ wickets in a single Test match, across both innings of that
match. Use `player_match_stats`, because it already stores one row per player per
match with total `wickets_taken`. Join `match_stats` to filter Tests.

Do not use `format_group` on `player_match_stats`; that column does not exist in
that table.

Pattern:

```sql
SELECT
  p.player_name,
  COUNT(*) AS ten_wicket_matches
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND m.match_type = 'Test'
  AND p.wickets_taken >= 10
GROUP BY p.player_name;
```

If the user asks to list those matches, use:

```sql
SELECT
  p.player_name,
  p.wickets_taken,
  p.runs_conceded,
  m.match_date,
  m.team1,
  m.team2,
  m.venue,
  m.result
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE p.player_name = 'PLAYER_NAME'
  AND m.match_type = 'Test'
  AND p.wickets_taken >= 10
ORDER BY m.match_date ASC;
```

Question: Which Indian player has taken the most 10-wicket hauls in Tests?

This asks for players representing India, so use `p.team = 'India'` on
`player_match_stats`. Do not use `p.player_team`; `player_match_stats` does not
have that column.

Pattern:

```sql
SELECT
  p.player_name,
  COUNT(*) AS ten_wicket_hauls,
  SUM(p.wickets_taken) AS wickets_in_those_matches
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE m.match_type = 'Test'
  AND p.team = 'India'
  AND p.wickets_taken >= 10
GROUP BY p.player_name
ORDER BY ten_wicket_hauls DESC,
         wickets_in_those_matches DESC,
         p.player_name ASC
LIMIT 1;
```

For other countries, replace `p.team = 'India'` with the relevant country name.

Question: Show PLAYER Test runs by year.

Use `player_career_group_stats` with:

```sql
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND group_type = 'year'
```

Question: Show PLAYER Test runs by opposition.

Use `player_career_group_stats` with:

```sql
WHERE player_name = 'PLAYER_NAME'
  AND format_group = 'Test'
  AND group_type = 'opposition'
```

Question: In which year did PLAYER make his Test debut?

Use `player_match_stats` joined to `match_stats`. Find the earliest Test
`match_date` for that player, then return `m.year`, `m.match_date`, teams, venue,
and the database player name. If the user gives a full/common name that may not
match the abbreviated database name, search with `LIKE`.

Pattern:

```sql
SELECT
  m.year,
  m.match_date,
  m.team1,
  m.team2,
  m.venue,
  p.player_name
FROM player_match_stats p
JOIN match_stats m ON m.match_id = p.match_id
WHERE m.match_type = 'Test'
  AND lower(p.player_name) LIKE lower('%PLAYER_SURNAME_OR_KEYWORD%')
ORDER BY m.match_date ASC, m.match_id ASC
LIMIT 1;
```

Examples:

- "which year did Boycott make his debut" should search for `%Boycott%`.
- "which year did Gundappa Vishwanath make his debut" should search for
  `%Viswanath%` or `%Vishwanath%`; the database player name is usually
  `GR Viswanath`.

## Player Name Rules

- Always resolve the user's player wording to a database `player_name` before
  writing the final query. Use that resolved name in the final query.
- If a player alias is known, use the exact database `player_name`.
- If the question context provides an exact database `player_name`, use equality:
  `player_name = 'L Amarnath'`. Do not replace that with `LIKE '%Amarnath%'`.
- Never invent, expand, or "correct" player names. Use exact database names from
  the resolver/context, such as `M Vijay`; do not guess expanded names such as
  `Murali V Vijay`.
- Do not query with the user's raw full common name when the database uses an
  abbreviation, initials, or surname-only row.
- When resolving a full player name, first check whether the exact full name
  exists as a database `player_name`. If it exists, use it. Example:
  "Shubman Gill" -> `Shubman Gill`, not `S Gill`.
- If the exact full name is not found, try the first character of the first name
  plus the last name. Examples: "Lala Amarnath" -> `L Amarnath`,
  "Sunil Gavaskar" -> `S Gavaskar` if there is no known alias, "Don Bradman" ->
  `D Bradman` if there is no known alias.
- If initial-plus-last-name is not found, search by the distinctive last name.
- For Test questions, prefer player names that have `player_career_stats` rows
  where `format_group = 'Test'` and `competition_name = 'All'`. Do not resolve a
  Test question to a domestic-only player if a Test player also matches the name.
- Resolve the player name according to the requested statistic. For bowling
  average, wickets, best bowling, or five-wicket hauls, prefer the matching Test
  career row with `wickets_taken > 0`. For batting average, runs, hundreds, or
  fifties, prefer the matching Test career row with batting innings/runs. For
  catches or fielding questions, prefer the matching Test career row with
  `catches > 0`.
- For full-name bowling/wicket questions, compare both the initial-plus-surname
  candidate and the surname-only candidate when both exist. Use the candidate
  with the higher Test career `wickets_taken`; for example, Richard Hadlee's
  wicket total is stored under `Hadlee`, while `RJ Hadlee` is not the right
  bowling career row for this question.
- For bowling record or career bowling questions, return bowling fields from
  `player_career_stats`, require `wickets_taken > 0` when possible, and order by
  `wickets_taken DESC, matches DESC`. Do not order by `runs_scored` or
  `batting_innings`.
- When querying batting career stats from `player_career_stats`, duplicate rows
  may exist for the same `player_name`. Use `ORDER BY runs_scored DESC,
  batting_innings DESC LIMIT 1`, not bare `LIMIT 1`.
- When context provides a resolved stat-aware Test `player_name`, use exact
  equality for that one name. Do not use an `IN` list of alternate candidates.
- For comparison questions, resolve each named player separately according to the
  requested statistic, then include all resolved names in the final query.
- If the player name is uncertain, use a case-insensitive LIKE predicate with a
  distinctive surname or database-style key token. Do not search for a full
  common name that may not exist in the database, such as `%Lala Amarnath%`.
  Prefer `%Amarnath%`, `%Gavaskar%`, `%Viswanath%`, etc.

```sql
lower(player_name) LIKE lower('%Gavaskar%')
```

- Prefer exact `player_name` matches over LIKE when available.
- For Lala Amarnath, use the exact database name `L Amarnath`.

## Known Player Aliases

- Sunil Gavaskar = SM Gavaskar
- Gavaskar = SM Gavaskar
- Don Bradman = DG Bradman
- Bradman = DG Bradman
- Sachin Tendulkar = SR Tendulkar
- Tendulkar = SR Tendulkar
- Brian Lara = BC Lara
- Lara = BC Lara
- Geoff Boycott = G Boycott
- Boycott = G Boycott
- Gundappa Viswanath = GR Viswanath
- Gundappa Vishwanath = GR Viswanath
- Viswanath = GR Viswanath
- Vishwanath = GR Viswanath
- Lala Amarnath = L Amarnath
- Amarnath = L Amarnath when the question clearly refers to Lala Amarnath
- Surinder Amarnath = S Amarnath
- Dennis Lillee bowling/career bowling = Lillee

## Safety

- Return only one SQLite SELECT query.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, PRAGMA,
  ATTACH, DETACH, or VACUUM.
- Use `LIMIT 50` unless the user explicitly asks for all rows.
