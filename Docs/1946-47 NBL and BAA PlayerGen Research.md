# 1946-47 NBL and BAA Research for PlayerGen

Research supplement for generating real players from the 1946-47 National Basketball League and Basketball Association of America seasons.

This document supplies evidence and constraints. It does not define ratings, fictional era templates, seeds, player-name features, or runtime behavior.

## 1. Scope

This study covers exactly:

- **1946-47 NBL**
- **1946-47 BAA**, the BAA's inaugural season

It does not cover earlier MBC/NBL seasons, the ABL, independent teams, military teams, or later NBL/BAA/NBA seasons except where a source's broader biography is explicitly identified and prevented from overriding 1946-47 evidence.

## 2. Evidence method

### 2.1 Evidence classes

- **Direct:** an observed statistic, physical measurement, 1946-47 season description, or explicit institutional biography.
- **Calculated:** transparent arithmetic from observed source fields.
- **Informed inference:** a narrow PlayerGen implication from direct or calculated evidence.
- **Unresolved:** unavailable, contradictory, or insufficiently specific to 1946-47.

Player names identify the real player to whom evidence belongs. Names are not model inputs or role features.

### 2.2 Quantitative sample

The project-local `NBA_DATA_Master.sqlite` supplied 1946-47 player and team totals. A player-team stint qualified for the ordinary-role tables when:

1. It was a real team row rather than a `TOT` aggregate.
2. The player made at least one field goal.
3. Games played were at least 40% of that team's recorded games.

Duplicate `player_info` entries were collapsed by player ID before attaching broad position, height, and weight.

The resulting samples are:

- **109 qualifying NBL player-team stints**
- **120 qualifying BAA player-team stints**

These are player-team stints, not necessarily unique people; a traded player may have more than one team row if each stint qualifies.

### 2.3 Availability boundary

The 1946-47 NBL rows used here contain games, FGM, FTM, FTA, points, broad position, height, and weight. They do not contain FGA, assists, rebounds, minutes, steals, blocks, or turnovers.

The 1946-47 BAA rows contain FGA and assists in addition to scoring fields, but not rebounds or minutes.

Therefore:

- NBL FGM share is observed make production, not shot-attempt share.
- NBL shot volume and creation cannot be reconstructed from BAA medians.
- Missing rebounds, minutes, steals, blocks, and turnovers remain unresolved.
- Missing values are not zero.
- Modern efficiency, usage, pace, and possession statistics must not be fabricated.

## 3. Ordinary 1946-47 role baselines

The tables report medians among qualifying player-team stints. Position is a broad historical label, not a modern five-position assignment.

### 3.1 NBL

| Position | Stints | Median height | Median weight | Median team PTS |
|---|---:|---:|---:|---:|
| G | 17 | 5'11" | 180 lb | 8.5% |
| G-F | 27 | 6'0" | 180 lb | 9.1% |
| F-G | 21 | 6'2" | 190 lb | 10.9% |
| F | 4 | 6'1.5" | 190.5 lb | 9.3% |
| F-C | 18 | 6'4" | 200 lb | 7.3% |
| C-F | 17 | 6'6" | 220 lb | 13.4% |
| C | 5 | 6'9" | 230 lb | 9.3% |

The pure-`F` and pure-`C` samples are small. Their medians are descriptive, not stable universal priors.

Leading qualifying scoring shares:

| Player | Team | Position | Team PTS |
|---|---|---|---:|
| Don Otten | Tri-Cities | C | 26.3% |
| Freddie Lewis | Sheboygan | F-G | 24.4% |
| Arnie Risen | Indianapolis | C-F | 23.3% |
| Al Cervi | Rochester | G-F | 22.8% |
| Hal Tidrick | Toledo | F-G | 22.8% |
| Chips Sobek | Toledo | G-F | 21.7% |
| Bob Carpenter | Oshkosh | F-C | 20.1% |
| Jerry Rizzo | Syracuse | G | 19.5% |

These are individual scoring loads. They must not become default position tendencies.

### 3.2 BAA

| Position | Stints | Median height | Median weight | Team PTS | Team FGA | Team AST |
|---|---:|---:|---:|---:|---:|---:|
| G | 41 | 6'0" | 175 lb | 7.8% | 7.6% | 7.6% |
| G-F | 12 | 6'1.5" | 172.5 lb | 9.5% | 9.3% | 10.4% |
| F-G | 8 | 6'2.5" | 187.5 lb | 8.2% | 8.8% | 7.5% |
| F | 27 | 6'3" | 190 lb | 6.9% | 7.2% | 6.7% |
| F-C | 13 | 6'5" | 190 lb | 7.6% | 8.1% | 7.3% |
| C-F | 9 | 6'6" | 210 lb | 8.6% | 7.7% | 7.7% |
| C | 10 | 6'7" | 225 lb | 5.4% | 5.2% | 4.2% |

Prominent individual loads:

- **Joe Fulks:** 33.7% of Philadelphia's points, 28.9% of its FGA, and 40.0% of its made free throws.
- **Stan Miasek:** 23.6% of Detroit's points and 19.8% of its FGA.
- **Bob Feerick:** 20.9% of Washington's points.
- **Ernie Calverley:** 42.0% of Providence's assists.
- **Howie Dallmar:** 30.3% of Philadelphia's assists.
- **Kenny Sailors:** 27.1% of Cleveland's assists.
- **Johnny Logan:** 26.7% of St. Louis's assists.
- **Ossie Schectman:** 23.9% of New York's assists.

The BAA data show that scoring and creation could be highly concentrated. The ordinary center medians are low-volume, so high-volume bigs must be generated from their individual evidence rather than the center label alone.

## 4. 1946-47 league and team context

### 4.1 NBL

Rochester won the Eastern Division. Fort Wayne remained strong but lost Buddy Jeannette to the ABL, Ed Sadowski to the BAA, and Bobby McDermott to Chicago after a midseason dispute.

Oshkosh won the Western Division behind veteran bigs Leroy Edwards, Bob Carpenter, and Gene Englund. Indianapolis finished second behind Arnie Risen's scoring. Chicago surged after George Mikan returned from a contract holdout and McDermott arrived from Fort Wayne.

In the championship series, Rochester's offense used the speed of Bob Davies, Red Holzman, and Al Cervi. Its strong frontcourt—George Glamack, Arnie Johnson, and Dolly King—took turns doubling Mikan. Chicago won the series after Mikan and Bob Calihan became decisive.

Supported team-style conclusions:

- Rochester combined speed and guard creation with enough frontcourt strength to use multiple defenders against an elite center.
- Chicago's championship construction combined Mikan's exceptional interior impact with McDermott's veteran perimeter scoring and creation.
- Oshkosh remained a veteran, hard-nosed frontcourt team rather than a generic speed team.
- NBL team success did not require one identical pace or role structure.

### 4.2 BAA

Washington posted the league's best regular-season record. Red Auerbach assembled a strong frontcourt around Bones McKinney, Johnny Norlander, and John Mahnken, with Bob Feerick, Fred Scolari, Marty Passaglia, and Irv Torgoff supplying perimeter and swing responsibilities.

Philadelphia centered its offense on Joe Fulks, whose jump shot and scoring load were exceptional even within the season. Veteran ABL players supplied much of the surrounding roster.

Chicago and St. Louis tied atop the Western Division while using contrasting styles:

- Chicago used Chuck Halbert's rebounding, several speedy guards, and a fast break. Max Zaslofsky supplied long-range scoring when transition stalled.
- St. Louis lacked Chicago's height and used a more methodical, defense-oriented half-court attack to find shots for Johnny Logan and Belus Smawley.

Philadelphia defeated Chicago in the BAA Finals.

Supported PlayerGen conclusion: the inaugural BAA contained fast-break, methodical half-court, frontcourt-centered, and exceptional high-volume scoring constructions. “1946-47” is not one universal play style.

## 5. Named 1946-47 player evidence

### 5.1 George Mikan — exceptional two-way center

Direct evidence:

- 6'10" and unusually athletic for his size.
- Strong scorer, rebounder, and defender.
- Could run the floor and finish with force.
- Drew planned multi-player coverage from Rochester in the NBL Finals.

PlayerGen use: exceptional size-strength-athleticism combination, interior scoring, rebounding, defense, and transition finishing. He must not define the ordinary center baseline.

### 5.2 Bobby McDermott — veteran deep set-shooting creator

Direct style evidence from his profile:

- 5'11" and approximately 185 pounds.
- Very strong but not especially fast.
- High-arcing two-handed set shot extending to roughly 30 feet.
- Used a fake and backward step before shooting.
- Could drive and create for teammates.

Exact-season context: Fort Wayne traded him to Chicago during 1946-47; he and Mikan joined the Gears' late surge and championship run.

PlayerGen use: deep set-shot evidence, scoring and playmaking, strong guard frame, and secondary driving. Do not convert this into modern three-point zones, a modern jump-shot package, or modern burst athleticism.

### 5.3 Arnie Risen — lanky scoring center

Direct evidence:

- Approximately 6'9" and 200 pounds.
- Described as a “string bean” center rather than a bulky Mikan type.
- Indianapolis's principal 1946-47 scorer.
- Institutional biography supports scoring, rugged rebounding, and versatility, but later-career achievements must not be copied backward automatically.

PlayerGen use: tall, lean scoring/rebounding center distinct from Mikan's physical construction.

### 5.4 Bob Davies — speed and innovative playmaking

Direct evidence:

- Rochester's offense used him as part of its speedy guard trio.
- Institutional biography documents functional behind-the-back, through-the-legs, and over-the-head handling.
- Identified as an innovative playmaker and floor general.

PlayerGen use: transition creation, unusually creative era-relative handle, and floor-general responsibility. Do not infer modern dribble-combo frequencies.

### 5.5 Al Cervi and Red Holzman — Rochester guard speed

The 1946-47 season account explicitly places Cervi and Holzman with Davies in Rochester's speedy offensive trio. Cervi also carried 22.8% of Rochester's recorded points in the qualifying sample.

PlayerGen use: speed and transition participation are directly supported. More specific handle, shot-location, or defensive fields need individual sources.

### 5.6 Joe Fulks — BAA scoring and jump-shot outlier

Direct and calculated evidence:

- Pro Basketball Encyclopedia describes an exceptional jump shot.
- 33.7% of Philadelphia's points.
- 28.9% of Philadelphia's FGA.
- 40.0% of Philadelphia's made free throws.

PlayerGen use: exceptional shot volume, jump shooting, and foul-line scoring load. His profile is an outlier, not the ordinary forward-center mold. Historical “jump shot” evidence does not identify modern three-point locations.

### 5.7 Ernie Calverley — concentrated creation

Calverley produced 42.0% of Providence's recorded assists, the strongest qualifying assist concentration in the BAA sample.

PlayerGen use: primary creation and passing responsibility are strongly supported by the recorded team share. Specific pass types and dribble packages remain unresolved.

### 5.8 Howie Dallmar, Kenny Sailors, Johnny Logan, and Ossie Schectman

Their recorded assist shares support substantial initiation responsibility:

- Dallmar: 30.3% of Philadelphia assists.
- Sailors: 27.1% of Cleveland assists.
- Logan: 26.7% of St. Louis assists.
- Schectman: 23.9% of New York assists.

These shares establish creation load, not identical play style. Team and biographical evidence must decide how each player created.

### 5.9 Chuck Halbert and Max Zaslofsky — complementary Chicago functions

The season account assigns different functions:

- Halbert's rebounding helped trigger Chicago's fast break.
- Zaslofsky supplied long-range scoring when the fast break stalled.

PlayerGen use: retain the functional separation. Rebounding evidence for Halbert is qualitative because the BAA did not record player rebounds; Zaslofsky's “long range” cannot be converted directly into modern three-point zones.

### 5.10 Ordinary-role caution

The season's stars should not erase ordinary rotation molds. The median tables show many guards, forwards, and centers with modest team scoring, FGA, or assist shares. Low-scoring defensive, rebounding, screening, cutting, and connective roles may have existed, but only source-supported functions should be assigned to a particular real player.

## 6. PlayerGen translation contract

For a real 1946-47 NBL or BAA player:

1. Match the player, league, team stint, and season first.
2. Preserve sourced height, weight, position, games, and available box-score fields.
3. Use ordinary distributions as plausibility context, not as formula outputs.
4. Use named evidence only for the player it describes.
5. Let the model own formulas and 2K field translation.
6. Keep attributes, tendencies, statistics, and shot percentages semantically separate.
7. Keep unavailable NBL FGA and assists unresolved.
8. Keep unavailable rebounds, minutes, steals, blocks, and turnovers unresolved in both leagues.
9. Do not substitute FGM for FGA or points share for shot tendency.
10. Do not translate “outside” or “long range” directly into modern three-point locations.
11. Do not apply Mikan, Fulks, McDermott, or another star's evidence to ordinary players.
12. Do not impose one universal 1946-47 pace, role, or physical template.

## 7. Claims intentionally not established

This study does not establish:

- NBL FGA or assist distributions.
- Player rebound distributions in either league.
- Individual minutes, steals, blocks, turnovers, usage, or modern advanced statistics.
- Modern five-position role equivalence.
- Modern shot zones from historical shooting terminology.
- Complete individual defensive profiles.
- Exact pass, dribble, post-touch, screen, cut, or matchup frequencies without film or play-by-play.
- Earlier-career traits not evidenced in 1946-47.

These are unresolved fields, not invitations to impute values.

## 8. Source ledger

URLs accessed July 21-22, 2026.

### Statistical and season sources

- **Basketball-Reference.** “1946-47 NBL Season Summary.”  
  https://www.basketball-reference.com/nbl/seasons/1947.html
- **Basketball-Reference.** “1946-47 BAA Season Summary” and player totals.  
  https://www.basketball-reference.com/leagues/BAA_1947.html  
  https://www.basketball-reference.com/leagues/BAA_1947_totals.html
- **Pro Basketball Encyclopedia.** “1946-1947.” Secondary season narrative covering the NBL, BAA, and contemporary professional context.  
  https://probasketballencyclopedia.com/seasons/1946-1947/

### Historical and institutional sources

- **Nelson, Murry R.** *The National Basketball League: A History, 1935-1949.* McFarland, 2009. Used for NBL historical context, not as a substitute for the 1946-47 statistical tables.  
  https://books.google.com/books?id=8HYQQYEtQ4gC
- Naismith Memorial Basketball Hall of Fame, “Bobby McDermott.”  
  https://www.hoophall.com/hall-of-famers/bobby-mcdermott
- Naismith Memorial Basketball Hall of Fame, “Bob Davies.”  
  https://www.hoophall.com/hall-of-famers/bob-davies
- Naismith Memorial Basketball Hall of Fame, “George Mikan.”  
  https://www.hoophall.com/hall-of-famers/george-mikan
- Naismith Memorial Basketball Hall of Fame, “Arnie Risen.”  
  https://www.hoophall.com/hall-of-famers/arnie-risen
- Pro Basketball Encyclopedia, “Bobby McDermott.” Detailed secondary player profile and career table.  
  https://probasketballencyclopedia.com/player/bobby-mcdermott/

### Project-local statistical source

- `nba2k_editor/Player Generator/NBA Player Data/NBA_DATA_Master.sqlite`
- `nba2k_editor/Player Generator/NBA Player Data/Advanced stats/NBA_DATA_MASTER_MAP.md`

## 9. Confidence summary

### Strongly supported

- Exact 1946-47 NBL and BAA scope.
- Statistical availability boundaries.
- Calculated ordinary physical and production distributions under the stated filters.
- Contrasting team constructions in Rochester, Chicago, Oshkosh, Washington, Philadelphia, and St. Louis.
- The named player traits explicitly connected to 1946-47 above.

### Supported but incomplete

- Qualitative rebounding and defensive functions where no player rebound or defensive totals exist.
- Exact mechanisms behind recorded assist shares.
- The frequency and location of set shots, jump shots, and long-range attempts.

### Unresolved

- Missing box-score fields and possession context.
- Complete shot-location, movement, and defensive profiles.
- Any attempt to generalize beyond the 1946-47 NBL and BAA seasons.
