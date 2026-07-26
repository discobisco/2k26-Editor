# PlayerGen MIDRANGE Spot-Up Calibration

Status: provisional controlled-response calibration. The user-observed anchors are authoritative; runtime uses monotone piecewise-linear interpolation within the explicit spot-up context until a full controlled sweep replaces it.

## Field semantics

- `Attributes/MIDRANGE` measures shot execution beginning at 10 feet.
- The `3–10 ft` bucket belongs to `Attributes/CLOSESHOT`; it is never MIDRANGE evidence.
- Direct-location MIDRANGE uses only the `10–16 ft` and `16 ft–3P` buckets.
- `FT% / 2` is a best-case wide-open stationary spot-up/set-shot target only.
- `MIDSPOTUPSHOT`, `MIDOFFSCREENSHOT`, `DRIVEPULLUPMIDRANGE`, and contested-mid fields are independent behavioral Tendencies. They are not make-percentage weights and are never normalized into attempt shares.
- FT% does not author any action Tendency.

## Admitted user-observed response anchors

| MIDRANGE | Wide-open spot-up | Off-screen | Pull-up | Contested | Status |
|---:|---:|---:|---:|---:|---|
| 25 | 0.0015 or less | 0.0015 or less | 0.0015 or less | 0.0015 or less | user-observed floor |
| 80 | 0.45 | 0.40 | 0.40 | 0.35 | user-observed anchor |
| 99 | 0.55 | 0.50 | 0.50 | 0.45 | user-observed anchor |

Ratings 26–79 and 81–98 remain unmeasured. The provisional interpolation is context-local and never averages, weights, or normalizes the four shot contexts.

## Required controlled sweep

For every tested rating, hold constant:

- game build and difficulty;
- shooter, badges, hot zones, fatigue, and non-MID Attributes;
- all shot Tendencies;
- defender, contest distance, location, and shot animation;
- attempt count and possession setup.

Record makes, attempts, make rate, rating, shot context, game build, and settings. Replace the provisional interpolation when the complete measured spot-up table is available.

## Runtime gate

The equal-context aggregate inversion is removed. Historical `FT% / 2` inversion uses only the open spot-up anchors. Modern direct-location evidence remains on its field-specific peer-calibrated path and is not routed through the historical open-shot response. Renaming or retaining the rejected aggregate helper is not an acceptable replacement.
