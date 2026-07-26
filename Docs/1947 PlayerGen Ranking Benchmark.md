# 1947 PlayerGen Ranking Benchmark

This benchmark validates generated 1946-47 BAA and NBL players through the real PlayerGen proposal path.

## BAA comparison population

Use only generated 1947 BAA player records with:

- more than 10 games played (`G > 10`);
- recorded `OWS`, `DWS`, and `WS` in the exact 1947 BAA `Advanced` row;
- the generated proposal attached to the same exact `player_id` and canonical team record.

Do not substitute NBL data, another season, another league, a name match, or another statistic.

## Generated totals

The benchmark uses the authored Player Attributes layout:

- **Offense total:** sum every generated numeric candidate in `Attributes / Offense`.
- **Defense total:** sum every generated numeric candidate in `Attributes / Defense`.
- **Total Attributes:** sum every generated numeric candidate in the complete `Attributes` section.

Every generated field is counted once. Tendencies, Vitals, Badges, source statistics, and display-only values are excluded.

## BAA ranking checks

Rank descending, using average ranks for tied totals or tied statistics:

1. Offense total must reproduce the `OWS` ranking for the eligible BAA population.
2. Defense total must reproduce the `DWS` ranking for the eligible BAA population.
3. Total Attributes must reproduce the `WS` ranking for the eligible BAA population.

The benchmark reports every player's two ranks, rank delta, exact-rank matches, and Spearman rank correlation. Correlation is diagnostic; it does not turn a ranking mismatch into a pass.

## NBL Bob Feerick floor

The NBL has no 1947 `OWS`, `DWS`, or `WS` rows, so those BAA ranking checks must not be fabricated for NBL players.

Instead, each named NBL player's generated Total Attributes must be at least Bob Feerick's generated 1947 BAA Total Attributes. The benchmark keys these players by exact source `player_id`:

| Player | League | Exact `player_id` |
|---|---|---|
| Bob Feerick | BAA reference | `feeribo01` |
| George Mikan | NBL | `mikange01` |
| Bobby McDermott | NBL | `mcderro01` |
| Bob Davies | NBL | `daviebo01` |
| Freddie Lewis | NBL | `lewisfr01` |
| Al Cervi | NBL | `cervial01` |
| Hal Tidrick | NBL | `tidriha01` |
| Arnie Risen | NBL | `risenar01` |
| Red Holzman | NBL | `holzmre01` |
| Bob Carpenter | NBL | `carpebo01` |
| Bob Calihan | NBL | `calihro01` |

Additional historically established NBL players may be added explicitly by exact `player_id`; names remain display text rather than identity.

## Diagnostic-only ranking

The benchmark comparisons are diagnostic outputs. Production proposals are not post-processed to force `FG%`, `OWS`, `DWS`, `WS`, shooting, Offense, Defense, or total-Attribute rank agreement. Every field retains its ordinary field owner and provenance, including `Attributes/HANDS` and `Attributes/HUSTLE`.

The JSON shooting comparison includes all nine shooting Attribute values plus the broad under-basket, close, mid, driving-layup, driving-dunk, standing-dunk, post-up, and shoot-from-post Tendencies. These values are observed by the benchmark and are not rewritten by it.

## Runner

Run from the repository root:

```text
python3 "nba2k_editor/Player Generator/playergen_1947_ranking_benchmark.py" --output .hermes/playergen_1947_ranking_benchmark.json
```

The runner exercises the production generation path and writes the complete inspectable benchmark result. It does not alter source data or rewrite proposals.
