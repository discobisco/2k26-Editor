# PlayerGen Simulation Rating Contract

This document records user-established NBA 2K simulation behavior that governs PlayerGen mapping. These are output-behavior requirements, not permission to substitute missing source statistics or join players by display name.

## 1. Shooting execution and frequency

- Shooting Attributes and shooting Tendencies must be paired against the proven Pool/simulation shooting-percentage ranges.
- If a generated package is expected to shoot a given percentage, its shooting Attribute and relevant Tendencies must remain within the rating ranges already demonstrated to produce that percentage.
- Shooting Attributes represent conversion skill. Tendencies represent attempt frequency and location. Shot volume must not be used to inflate conversion skill.
- Do not stretch league percentiles, medians, or league-average distance directly over 25–99 when that package falls outside the demonstrated NBA 2K percentage response.

### Mid-range execution response map

For seasons without direct mid-range make percentages, estimate the player's practical field make target as `FT% / 2`, then invert the NBA 2K MIDRANGE response map. FT% authors shooting execution here; it does not author MIDSHOT frequency.

Observed anchors for the same MIDRANGE Attribute are:

| MIDRANGE | Spot-up | Off-screen | Pull-up | Contested | Equal-context mean |
|---:|---:|---:|---:|---:|---:|
| 25 | 0.15% | 0.15% | 0.15% | 0.15% | 0.15% |
| 80 | 45% | 40% | 40% | 35% | 40% |
| 99 | 55% | 50% | 50% | 45% | 50% |

Use piecewise-linear interpolation between the aggregate anchors `(25, 0.0015)`, `(80, 0.40)`, and `(99, 0.50)`. Clamp below/above the measured range to 25/99. Examples: FT% 50/60/70/80/90/100 map to MIDRANGE 59/66/73/80/90/99.

## 2. Rebounding

- Offensive Rebound and Defensive Rebound each compute a same-season, same-league rank score from their independently owned rebound evidence.
- Both Attribute values use the direct mapping `round(25 + 74 * rank_score)` and remain inside the legal 25–99 domain.
- Do not map rebound rank through a Pool quantile/output curve; Pool packages may support evidence review but do not replace the direct 25–74 rank mapping.
- Offensive Rebound and Defensive Rebound are independent skills. Strength in one must not automatically create strength in the other.
- Explicit exception: whenever exact `player_id=malonmo01` (Moses Malone) is present, his Offensive Rebound rating must be 15 points above the next-highest Offensive Rebound rating in that generated season/league population. His Defensive Rebound remains independently authored.

### Consistency Attributes

- `Attributes/OFFENSIVECONSISTENCY` maps its weighted same-season, same-league component-rank score directly with `round(25 + 74 * rank_score)`.
- `Attributes/DEFENSECONSISTENCY` ranks its field-specific defensive-consistency context prediction within the same season and league, then applies the same direct 25–74 mapping.
- Neither Consistency Attribute uses a Pool output-distribution curve after its rank score is established.

## 3. Passing and assists

The three passing Attributes are:

- `Attributes/PASSACCURACY`
- `Attributes/PASSIQ`
- `Attributes/PASSVISION`

Requirements:

- A player expected to average 10 APG must have at least 95 in all three passing Attributes.
- Passing skill alone does not guarantee 10 APG. Teammates must convert the available scoring opportunities.
- An elite passer on a team that cannot score may average only approximately 5–6 APG.
- Assist opportunity is finite. If an entire league has 99 in all three passing Attributes, the expected peak can fall to approximately 6 APG, with most players around 3–4 APG, because available assists are distributed across the league.
- Therefore, assist ratings require both individual passing skill and team/league scoring-opportunity context. They must not be mapped from a player-only APG percentile as though opportunities were unlimited.

### Touches tendency

- `Tendencies/TOUCHES` measures the player's share of exact-team offensive involvement, not raw league-wide FGA or AST volume.
- Its main formula combines player FGA share of exact-team FGA (45%), player AST share of exact-team AST (30%), and USG% (25%). USG% remains direct because it is already a team-possession share while the player is on court.
- Each component is ranked only within the exact same season and league. Missing components are omitted and available weights are renormalized; missing is never zero.
- In historical NBL seasons where FGA, AST, and USG% are all unrecorded, use the surviving exact-team scoring-opportunity shares: player FGM share (65%) and player FTA share (35%). Keep this fallback explicitly provenanced because FGM cannot represent missed attempts.

## 4. Interior defense, perimeter defense, blocks, and steals

- Main defensive quality combines player DWS (50%), exact-team win percentage (25%), and exact-team point differential (25%), each ranked within the same season and league.
- Missing components remain missing and the available authored weights are renormalized; missing values are never converted to zero.
- When player DWS is unavailable, exact-team win percentage and point differential jointly establish defensive quality.
- Position/matchup allocation still determines whether that defensive quality belongs primarily in Interior Defense or Perimeter Defense.
- The best Interior Defense and Perimeter Defense players in a season/league should reach the 90s.
- Players with negative defensive results should remain below 40 at most rather than being lifted by the rest of the population.
- Exact researched player-season-team overrides may supersede the statistical quality blend only when repository evidence directly supports defense for that identity. For 1947 NBL George Mikan (`mikange01`, `CAG`), Pro Basketball Encyclopedia describes him as an outstanding defender and outstanding in every facet, so his researched defensive-quality override is 99 before center position allocation.

Block thresholds:

- Approximately 2–3 BPG requires a Block Attribute of at least 90.
- Approximately 1–2 BPG requires a Block Attribute of at least 65.

Steal thresholds:

- Steal output follows approximately the same thresholds as blocks: approximately 2–3 SPG requires 90-plus steal-generation strength; approximately 1–2 SPG requires at least 65-plus.
- `Attributes/PASSPERCEPTION` also generates steals. When Steal and Pass Perception are both mapped from the same steal-output target, they must split that target's contribution 50/50 rather than each receiving the full steal-derived rating.

## 5. Vertical

- Vertical is based on how far the player rises off the floor, not absolute touch height.
- Compute or infer jump height relative to the player's standing reach when standing-reach/touch evidence exists.
- Example: if a 6'0 player and a 6'10 player both touch 11'5 from a standing jump, the 6'0 player must receive a drastically higher Vertical rating because the shorter player rose farther.
- Absolute reach must not be ranked as Vertical.

## 6. Strength

- When direct strength evidence is unavailable, Strength may be inferred from body density rather than raw weight alone.
- At equal weight, the shorter player is generally stronger because the same mass is carried in a smaller frame.
- Example: at 220 lb, a 6'2 player should rate stronger than a 6'9 player unless direct evidence overrides the body inference.

## 7. Speed, Agility, and Speed With Ball

Speed:

- Within the active season/league population, the shortest/lightest player anchors 99 and the tallest/heaviest player anchors 25.
- Smaller/lighter NBA players generally rank faster than larger/heavier players when direct speed evidence is unavailable.

Agility:

- Agility is based primarily on Perimeter Defense ability.
- Agility must never be more than 5 points above Speed: `AGILITY <= SPEED + 5`.

Speed With Ball:

- Speed must always be at least 5 points above Speed With Ball: `SPEEDWITHBALL <= SPEED - 5`.
- The gap may be larger. Speed With Ball must never be closer than five points to Speed.

## 8. Post and dunk Attributes

Post Control:

- Post Control combines scoring effectiveness, height, and weight.

Post Hook:

- Exact `player_id=mikange01` (George Mikan) receives `Attributes/POSTHOOK=99`.
- Exact `player_id=abdulka01` (Kareem Abdul-Jabbar) receives `Attributes/POSTHOOK=99`.

Standing Dunk:

- Standing Dunk is primarily height-driven when direct dunk evidence is unavailable.
- Players under 6'4 (`identity.ht_in_in < 76`) receive `Attributes/STANDINGDUNK=25` before any FG%, role, or historical-alignment logic.
- A player listed at exactly 6'4 is outside this floor gate and continues through the normal Standing Dunk formula.

Driving Dunk:

- For older seasons without recorded dunk statistics, Driving Dunk is authored entirely from Vertical and height.
- Do not use scoring volume, rebounding, or generic athletic production as a substitute for that vertical-plus-height relationship.

## 9. Identity and exception boundary

- Runtime identity remains exact source `player_id` plus the generated season/league record. Names are display-only.
- The Mikan, Kareem, and Moses Malone rules above are explicit user-authored exceptions. They do not authorize additional named-player templates.
- Missing source data remains missing unless this contract explicitly provides the substitute relationship.
