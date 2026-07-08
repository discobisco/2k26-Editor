learning

https://databallr.com/learning

Tier 1: Core Concepts
The foundational ideas that unlock everything else

Tier 1 — Core Concepts
Per-100 Possession Thinking
The foundation of meaningful basketball statistics

Think of per-100 possession stats like converting currencies to a common denomination. Raw counting stats are distorted by two things: team pace (faster teams create more possessions per game) and minutes played (a starter logging 35 minutes simply has more opportunities than a bench player logging 22). Per-100 possession rates strip away both of these distortions.

The key is that per-100 stats normalize by the player's own possessions played, not the team's total. If a player was on the floor for 75 possessions and recorded 2 steals, their rate is 2.0 / 75 × 100 = 2.67 steals per 100 possessions.

This matters because per-game stats hide both pace and playing time. Consider two players who each average 1.5 steals per game. Player A plays 34 minutes on a 102-pace team — roughly 72 possessions. Player B plays 26 minutes on a 96-pace team — roughly 52 possessions. Player A's rate is 1.5 / 72 * 100 = 2.08 per 100. Player B's rate is 1.5 / 52 * 100 = 2.88 per 100. Same per-game number, but Player B is a far more disruptive defender per opportunity.

This logic extends across the entire box score. Turnover rate (TOV%) measures the percentage of a player's possessions that end in turnovers, not raw turnover counts. Offensive rebound percentage (ORB%) measures the share of available offensive rebounds a player grabs, not the raw total. Usage rate measures the share of team possessions a player "uses" (via a shot, turnover, or free throw trip) while on the court. All of these are possession-based rates, and all of them are more useful than the raw counts.

The practical takeaway is simple: whenever you see a per-game counting stat, ask yourself whether pace and minutes are inflating or deflating the number. Per-100 possession stats are not perfect — they do not account for quality of competition or lineup context — but they remove the two largest sources of noise in raw box score data.

Per-100 rate
Stat per 100 = (Stat / Player Poss) × 100
Player A: 1.5 STL, 34 min, 102-pace team → ~72 poss
(1.5 / 72) × 100 = 2.08 per 100
Player B: 1.5 STL, 26 min, 96-pace team → ~52 poss
(1.5 / 52) × 100 = 2.88 per 100
Key Takeaways
Raw counting stats are inflated by both team pace and minutes played — a starter on a fast team racks up more stats by default.
Per-100 possession rates normalize by the player's own possessions played, removing both pace and playing time distortion.
Most advanced rate stats (TOV%, ORB%, Usage) are already possession-adjusted by design.
Always check whether a stat is pace- or minutes-dependent before comparing players across different roles and teams.
Explore per-100 stats in the Stats table
Tier 1 — Core Concepts
Relative Stats (rTS%)
Why context matters more than raw numbers

League-average True Shooting percentage has risen steadily over the past two decades, from roughly 52% in the early 2000s to around 58% in recent seasons. This shift is driven by the three-point revolution, rule changes favoring offense, and improved shot selection. The consequence: a raw TS% number means something entirely different depending on when it was recorded.

Relative True Shooting (rTS%) solves this by subtracting the league-average TS% for that season from the player's TS%. The result tells you how far above or below average the player was in their specific context. A player shooting 56% TS in the 2004-05 season, when league average was ~52%, had an rTS% of +4.0 — an elite scorer. That same 56% TS in the 2024-25 season, when league average is ~58%, yields an rTS% of -2.0 — below average.

This distinction matters enormously for historical comparisons. Allen Iverson posted a 54.3% TS in 2005-06 — slightly above the ~53.5% league average that season, giving him an rTS% of +0.8. By modern standards, 54.3% would yield an rTS% of roughly -3.7, making him look like an inefficient scorer. But in his era, he was a tick above average. Meanwhile, a current player at 58% TS might appear more efficient than Iverson ever was, but they are simply average for their era. rTS% captures this context and makes cross-era comparisons meaningful.

The DataBallr stats table and PvP comparison views both show rTS%, and it is one of the most informative single numbers for evaluating scoring efficiency. When you see a player's rTS%, you are seeing their efficiency relative to the competition they actually faced, not an absolute number divorced from context.

rTS% formula
rTS% = Player TS% - League Average TS%
2005 example: 56% TS, league avg 52%
rTS% = 56.0 - 52.0 = +4.0 (elite)
2025 example: 56% TS, league avg 58%
rTS% = 56.0 - 58.0 = -2.0 (below average)
Key Takeaways
League-average TS% has risen significantly over time, making raw TS% comparisons across eras unreliable.
rTS% = Player TS% minus league average TS% for that season.
Positive rTS% means above-average efficiency; negative means below-average — regardless of era.
rTS% is one of the best single-number efficiency indicators available.
See rTS% in the Stats table
Compare players' rTS% head-to-head
Tier 1 — Core Concepts
The NBA's Statistical Evolution
How shooting, turnovers, and rebounding have shifted over 25 years

The table below tracks three of the most important league-wide statistics from 2001 to 2026: True Shooting percentage (TS%), turnovers per 100 possessions (TOV/100), and offensive rebound percentage (ORB%). Together, these three numbers map directly to the Three Factors framework and reveal how fundamentally the game has changed.

Shooting efficiency has risen dramatically. League-average TS% climbed from 51.4% in 2001 to a peak of 58.1% in 2023 — a 6.7-percentage-point gain. This rise was driven by the three-point revolution (teams shooting more threes at improving rates), the extinction of the long midrange jumper, and rule changes that opened up offensive spacing. The 2012 season (52.4%) stands out as an outlier — that was the lockout-shortened season where compressed schedules and limited practice time depressed shooting across the league.

Turnover rates have steadily declined. Teams committed 16.3 turnovers per 100 possessions in 2001 but just 13.7 per 100 by 2024 — a reduction of roughly 16%. Modern offenses emphasize ball security, spacing reduces the chaotic drives that produce turnovers, and offensive schemes have become more structured. The recent uptick to ~14.6 in 2026 may reflect rule enforcement changes or shifting styles of play.

Offensive rebounding tells the most complex story. ORB% dropped from 31.1% in 2001 to a low of 25.7% in 2021 — a 17% decline — as teams prioritized transition defense over crashing the glass. The logic was straightforward: in a three-point-heavy league, getting back in transition was more valuable than chasing long rebounds. But since 2021, ORB% has rebounded sharply to 30.2% in 2026, nearly returning to early-2000s levels. This reversal suggests teams are finding new value in offensive rebounding or adjusting their transition-vs-crash calculus.

These three trends illustrate why era-adjusted stats like rTS% are essential. A player's raw TS% means something entirely different in a 51% league (2001) versus a 58% league (2023). The same applies to TOV% and ORB% — what counts as "good" ball security or rebounding effort has shifted as the league-wide baselines moved.

League averages by season (2001–2026)
2001
2004
2007
2010
2013
2016
2019
2022
2025
50%
52%
54%
56%
58%
60%
14
18
22
26
30
TS%TOV/100ORB%
Left axis: TS%
Right axis: TOV/100, ORB%
League averages by season (2001–2026)
Season	TS%	TOV/100	ORB%
2001	51.4%	16.3	31.1%
2002	51.7%	15.7	31.5%
2003	51.5%	16.2	31.1%
2004	51.3%	16.4	31.4%
2005	52.6%	15.7	31.5%
2006	53.2%	15.7	30.3%
2007	53.8%	16.2	30.1%
2008	53.7%	15.1	29.7%
2009	54.2%	15.1	29.7%
2010	54.1%	15.2	29.6%
2011	53.9%	15.3	29.7%
2012	52.4%	15.8	30.0%
2013	53.2%	15.7	29.7%
2014	53.8%	15.4	28.9%
2015	53.2%	15.2	28.6%
2016	53.9%	14.9	27.2%
2017	55.1%	14.4	26.8%
2018	55.5%	14.6	25.9%
2019	55.9%	14.0	26.4%
2020	56.4%	14.4	25.9%
2021	57.1%	13.9	25.7%
2022	56.6%	13.9	26.7%
2023	58.1%	14.1	27.4%
2024	58.0%	13.7	27.6%
2025	57.6%	14.4	28.5%
2026	57.6%	14.6	30.2%
Key Takeaways
League TS% rose from 51.4% (2001) to 58.1% (2023) — a 6.7-point gain driven by the three-point revolution and shot selection.
Turnovers per 100 possessions dropped from 16.3 to 13.7 over the same span — modern offenses take better care of the ball.
ORB% fell from 31.1% to a low of 25.7% (2021) as teams prioritized transition defense, but has since rebounded to 30.2%.
These shifting baselines are exactly why era-adjusted stats (like rTS%) exist — raw numbers mean different things in different eras.
Prerequisites:
relative-stats
See how rTS% adjusts for era
Three Factors framework
Tier 1 — Core Concepts
Three Factors (from Four)
The framework that explains almost all of basketball

Dean Oliver's Four Factors of basketball success — effective field goal percentage (eFG%), turnover rate (TOV%), offensive rebound percentage (ORB%), and free throw rate (FTA/FGA) — account for roughly 90-95% of the variance in offensive and defensive efficiency. Everything else in basketball is downstream of these four things. If your team shoots well, takes care of the ball, grabs offensive boards, and gets to the line, you win most of the time.

DataBallr collapses the four factors into three by combining eFG% and free throw rate into a single "shooting efficiency" factor represented by True Shooting percentage. TS% already captures both field goal efficiency and free throw value in a single number, so separating them would be redundant. The result is a cleaner three-factor framework: Shooting (TS%), Turnovers (TOV%), and Rebounding (ORB%/DRB%).

This three-factor model maps directly to the Six-Factor RAPM decomposition used on the ShotQuality page. Six-Factor RAPM breaks a player's total impact into six components: offensive and defensive contributions to each of the three factors. oTS measures a player's impact on team shooting efficiency. oTOV measures their impact on team turnover rate. oREB measures their impact on team offensive rebounding. The defensive counterparts (dTS, dTOV, dREB) measure how much the player helps or hurts the team on the other end.

The practical value of the three-factor framework is prioritization. When evaluating a lineup or a player, start with the three factors. If a lineup has a great net rating but terrible ORB%, you know the rebounding glass is a vulnerability even if the overall numbers look good. If a player has a strong overall RAPM but it is driven entirely by oTOV (they do not turn it over), you have a more specific picture of what they actually contribute.

Key Takeaways
Dean Oliver's Four Factors (eFG%, TOV%, ORB%, FT Rate) explain ~90-95% of offensive/defensive variance.
DataBallr uses three factors — Shooting (TS%), Turnovers, Rebounding — since TS% already captures both shooting and free throw value.
Six-Factor RAPM decomposes player impact into offense and defense for each factor: oTS/dTS, oTOV/dTOV, oREB/dREB.
Start with the three factors when diagnosing why a lineup is working or failing.
See Six-Factor RAPM decomposition
Tier 1 — Core Concepts
Shot Value & the Midrange Story
Why long twos died and short midrange survived

The core math of shot selection is points per shot (PPS). A two-point field goal made at 50% yields 2 × 0.50 = 1.00 PPS. A three-point field goal made at 33.3% also yields 3 × 0.333 = 1.00 PPS. So a 50% two-pointer and a 33.3% three-pointer produce identical expected value on the make-or-miss level. Since the league-average three-point percentage is roughly 36%, the average three is worth about 1.08 PPS. That means a two-point shot needs to be made at 54% to match the average three — a high bar.

But make-or-miss PPS is not the full picture. When a shot misses, the offense has a chance to grab the offensive rebound and score again. Offensive rebound rates vary dramatically by shot zone: rim misses are recovered at ~39%, short midrange at ~32%, above-the-break threes at ~27%, corner threes at ~28%, and long midrange at just ~24% — the lowest of any zone. This means the true expected value of a rim attempt is higher than raw PPS suggests (misses frequently lead to second chances), while long midrange misses are the least likely to generate additional scoring opportunities.

Long two-point shots — those from 16 to 23 feet, the classic midrange jumper — are where this combined math is most devastating. Most players shoot approximately 40% from that range, yielding just 0.80 PPS. That is 26% less efficient than an average three-pointer on a make-or-miss basis, and long midrange misses produce the fewest offensive rebounds of any zone. When the analytics revolution reached NBA front offices in the early 2010s, this was one of the clearest signals: the long two is a bad shot for most players.

But "most" is not "all." The short midrange (10-16 feet) survived because skilled shot creators shoot 48-52% or higher from there, especially off the dribble — and when they miss, short midrange misses are offensive rebounded at a meaningfully higher rate (~32%) than long twos (~24%). Certain elite midrange shooters — DeMar DeRozan, Kevin Durant, Chris Paul — sustain long midrange percentages well above 50%, clearing the efficiency threshold outright. The analytical case killed the lazy midrange, not the midrange itself. A Durant pull-up 18-footer at 52% is 1.04 PPS, competitive with an average three.

There is also a creation dimension that raw PPS misses. A player who can credibly score from the midrange forces the defense to extend, which opens driving lanes and creates kick-out threes for teammates. Shot quality and shot value are not the same thing — a shot that generates gravity has indirect value beyond its own conversion rate. The complete analytical picture accounts for direct efficiency, offensive rebounding probability on misses, and the ecosystem effects of a player's shot diet.

In the playoffs, where defensive intensity rises and three-point percentages typically drop, the short midrange becomes even more valuable. Half-court offense in tight games often runs through the midrange, because these shots are harder for defenses to take away than threes and less reliant on getting all the way to the rim against set defenses. The midrange is a pressure release valve when the easy shots dry up.

Points per shot: 2-pointers
50% × 2 = 1.00 PPS
Points per shot: 3-pointers
33.3% × 3 = 1.00 PPS (break-even) | 36% × 3 = 1.08 PPS (league avg)
Long two threshold
To match league-avg 3PT: need 54% on 2s (1.08 ÷ 2 = 54%)
OReb% by zone
Rim: 39% | Short Mid: 32% | Long Mid: 24% | Above-Break 3: 27% | Corner 3: 28%
Myth
Stats say the midrange is bad.

Reality
Stats say the average midrange is inefficient — around 0.80 PPS for long twos, with the lowest offensive rebound rate of any zone. But elite midrange shooters (50%+) beat that threshold, and shot creation value (pulling defenders, collapsing help) adds value beyond raw PPS. The data killed the lazy midrange, not the midrange itself.

Key Takeaways
Long 2s died because ~40% FG = 0.80 PPS, well below league-avg 3PT efficiency, with the lowest offensive rebound rate of any zone (~24%).
Short midrange survived because elite players beat the efficiency threshold, and misses are rebounded at a higher rate (~32%) than long twos.
Shot creation value exists beyond raw PPS — midrange gravity opens driving lanes and creates threes.
True shot value = PPS + (miss probability × OReb% × second-chance value). Rim shots and short midrange benefit most from this adjustment.
See shot location breakdown in ShotQuality


https://www.darko.app/longevity

darko data