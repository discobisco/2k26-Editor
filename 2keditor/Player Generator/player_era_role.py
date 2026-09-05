"""Pre-shot-clock (1947-1954) playstyle model.

The evidence-driven rules produce a rating/tendency card that is *individually*
plausible but stylistically modern: a 1947 pivot ends up with a face-up jumper and
step-back post moves, a 1947 guard ends up with crossovers and pull-ups, everyone
gets isolation and transition-pull-up tendencies. None of that existed before the
24-second clock.

This module applies one researched post-pass over the finished field values,
gated strictly to ``player_era_context`` era key ``pre_shot_clock`` (season <= 1954).
It reshapes the *role-driven* behaviour — which is the lever that actually matters,
because the raw ``role.*`` signals are z-scored within era and so era-uniform
changes to them wash out — by pushing each archetype toward how it was actually
played:

* pivots / interior bigs -> post-up, hook, backdown, put-back, bank shot up;
  face-up jumper, hop / spin / step-back post footwork, drives down.
* guards / perimeter -> two-hand set shot (spot-up mid), give-and-go passing,
  no-dribble catch-and-go up; on-ball creation, pull-ups, iso, alley-oop passing
  down. Elite handle ratings capped.
* everyone -> dunking, isolation, floaters, contested/off-screen jumpers,
  transition pull-ups down.

Controlled by env ``PLAYERGEN_ERA_ROLE_PLAYSTYLE`` (default on; ``0`` / ``false`` /
``off`` disables). Every touched field records ``era_role_playstyle=...`` in its
evidence keys and a ``_pre_shot_clock_role_playstyle`` suffix on its source rule.

The mid-range attribute is handled separately, inside
``player_rules_offense.derive_attribute_midrange``, because it needs the
free-throw-touch math rather than a flat multiplier.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from player_era_context import player_era_context

_PRE_SHOT_CLOCK_ERA_KEY = "pre_shot_clock"

# kind:
#   "scale"    -> value *= amount
#   "cap"      -> value <= amount, order preserved beneath the ceiling (see _capped)
#   "raise_to" -> value = max(value, amount)   (only when the gate is engaged)
# gate: None applies to everyone; otherwise the adjustment strength scales with the
# named archetype weight (0..1) so a hybrid forward gets a partial dose.
_GATES = ("guard", "wing", "frontcourt", "pivot", "perimeter")


#: Share of a cap the compressed band spans. A hard min() put every player in the
#: league on the cap for the most heavily suppressed actions -- ALLEYOOP, POSTFACEUP
#: and POSTSPIN each came out a single value across all 333 players in 1947 -- which
#: states the era correctly and then throws away which players did it more often.
#: Values already under the ceiling are untouched; the rest are compressed into the
#: top of the band in their original order.


#: The attribute floor. A field sitting here resolved to it on the player's own
#: evidence -- most often no made field goal all season. The era pass describes how an
#: archetype played, not whether this player could, so it must not lift a field off
#: the floor: raising post work because pivots posted up put players who never scored
#: back up at 55.
_ATTRIBUTE_FLOOR = 25.0


def _is_demonstrated_floor(field_key: str, current: Any) -> bool:
    # Attributes only. Tendencies legitimately live below 25 -- most of the era caps in
    # this model are single digits -- so treating a low tendency as a floored attribute
    # skipped its era cap and froze the field.
    if not field_key.startswith("Attributes/"):
        return False
    value = getattr(current, "value", None)
    return isinstance(value, (int, float)) and float(value) <= _ATTRIBUTE_FLOOR



@dataclass(frozen=True)
class _Adj:
    field: str
    kind: str
    amount: float
    gate: str | None
    why: str
    tag: str = ""  # retained so each adjustment stays self-describing in provenance


# The era playstyle pass reshapes tendencies only. Its three attribute adjustments --
# a guard-gated SPEEDWITHBALL cap and pivot-gated POSTHOOK/POSTCONTROL floors -- were
# archetype gates, which is position deciding a rating, so they are gone. What a player
# chose to do in 1947 is an era question; how well he could do it is a body and box-score
# question, and only the first belongs here.
_MODEL: tuple[_Adj, ...] = (
    # -- on-ball creation & handle: did not exist -------------------------------
    _Adj("Tendencies/TRIPLETHREATPUMPFAKE", "scale", 0.7, None, "less shot-fake gamesmanship", "handle"),
    _Adj("Tendencies/NOSETUPDRIBBLE", "scale", 1.3, "perimeter", "catch and go, no extended setup", ""),
    _Adj("Tendencies/NODRIVINGDRIBBLEMOVE", "scale", 1.35, None, "straight-line drives, no combo moves", ""),
    # No BALLCONTROL cap. The era suppressed the crossover *moves* -- the tendencies
    # above already carry that -- but it did not stop the best ball handler in the
    # league from being the best ball handler in the league. Capping the attribute at
    # 70 held Bob Davies, whose whole calling card was the handle, to the ceiling.
    # -- isolation basketball: did not exist ----------------------------------
    _Adj("Tendencies/PLAYDISCIPLINE", "scale", 1.15, None, "set-play weave/give-and-go offense", "ball_dominant"),
    # -- driving: slower, more deliberate, no rim-attack athletes ------------
    _Adj("Tendencies/DRIVE", "scale", 0.72, None, "deliberate half-court sets", "drive"),
    _Adj("Tendencies/DRIVE", "scale", 0.4, "pivot", "centers and pivots finished post actions rather than initiating perimeter drives", "drive"),
    _Adj("Tendencies/ATTACKSTRONGONDRIVE", "scale", 0.7, None, "few power finishers at the rim", "drive"),
    _Adj("Tendencies/OFFSCREENDRIVE", "scale", 0.7, None, "limited off-ball screen actions", "drive"),
    # -- shot selection: the two-hand set shot & the shot near the rim -------
    _Adj("Tendencies/MIDSPOTUPSHOT", "scale", 1.25, "perimeter", "two-hand set shot from the perimeter", "set_shot"),
    _Adj("Tendencies/MIDSHOT", "scale", 1.15, "perimeter", "set shot is the perimeter jumper", "set_shot"),
    _Adj("Tendencies/MIDOFFSCREENSHOT", "scale", 0.6, None, "little off-ball movement shooting", "off_screen"),
    _Adj("Tendencies/CONTESTEDJUMPERMID", "scale", 0.5, None, "you did not force contested jumpers", "volume_jumper"),
    _Adj("Tendencies/CONTESTEDJUMPERMIDRANGE", "scale", 0.5, None, "you did not force contested jumpers", "volume_jumper"),
    _Adj("Tendencies/BASKETUNDERSHOT", "scale", 1.2, None, "most offense finished at the rim", "rim_finish"),
    _Adj("Tendencies/CLOSESHOT", "scale", 1.2, None, "most offense finished at the rim", "rim_finish"),
    _Adj("Tendencies/CLOSEMIDDLESHOT", "scale", 1.15, None, "most offense finished at the rim", "rim_finish"),
    _Adj("Tendencies/USEGLASS", "scale", 1.4, None, "the bank shot was standard", ""),
    # -- post game: the pivot was the hub; footwork was the hook ------------
    _Adj("Tendencies/POSTUP", "scale", 1.35, "frontcourt", "the pivot ran the offense", "post_hub"),
    _Adj("Tendencies/POSTUPANDUNDER", "scale", 1.2, "frontcourt", "up-and-under off the pivot", "post_hub"),
    _Adj("Tendencies/FROMPOSTSHOT", "scale", 1.3, "frontcourt", "scoring came from the post", "post_hub"),
    _Adj("Tendencies/POSTBACKDOWN", "scale", 1.25, "frontcourt", "backing down from the pivot", "post_hub"),
    _Adj("Tendencies/POSTAGGRESSIVEBACKDOWN", "scale", 1.15, "pivot", "power pivots backed men down", "post_hub"),
    _Adj("Tendencies/POSTHOOKLEFT", "scale", 1.35, "pivot", "the hook was the money post shot", "post_hub"),
    _Adj("Tendencies/POSTHOOKRIGHT", "scale", 1.35, "pivot", "the hook was the money post shot", "post_hub"),
    _Adj("Tendencies/POSTDROPSTEP", "scale", 0.7, None, "drop step existed but was less emphasised", "post_footwork"),
    # -- passing: give-and-go, not flair ----------------------------------
    _Adj("Tendencies/DISHTOOPENMAN", "scale", 1.15, None, "give-and-go, hit the cutter", "ball_dominant"),
    # -- finishing above the rim: ability is fine, the *choice* to do it in a game is not -
    # NOTE: the dunk *attributes* (DRIVINGDUNK / STANDINGDUNK) are deliberately left alone.
    # Pre-shot-clock players dunked in warmups routinely -- the ability was there; they just
    # did not do it in games because of injury risk and convention. That is a *tendency*
    # suppression, already handled by player_era_context.dunk_attempt_multiplier, not an
    # ability ceiling.
    # -- transition ------------------------------------------------------
    _Adj("Tendencies/TRANSITIONSPOTUP", "scale", 0.6, None, "limited transition spacing", "fast_break"),
    # -- rebounding / hustle -------------------------------------------
    _Adj("Tendencies/PUTBACK", "scale", 1.2, "frontcourt", "everyone crashed the glass", ""),
    _Adj("Tendencies/CRASH", "scale", 1.15, None, "everyone crashed the glass", ""),
)


def era_role_playstyle_enabled() -> bool:
    return os.environ.get("PLAYERGEN_ERA_ROLE_PLAYSTYLE", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _position_vector(positions: Any, season_info_pos: Any) -> dict[str, float]:
    tokens: tuple[str, ...] = ()
    if positions is not None:
        tokens = tuple(getattr(positions, "all_positions", ()) or ())
        if not tokens and getattr(positions, "primary", ""):
            tokens = (positions.primary,)
    if not tokens:
        text = str(season_info_pos or "").upper()
        compact = "".join(ch for ch in text if ch.isalpha())
        two = {"G": ("PG", "SG"), "GF": ("SG", "SF"), "FG": ("SF", "SG"),
               "F": ("SF", "PF"), "FC": ("PF", "C"), "CF": ("C", "PF")}
        tokens = two.get(compact, ())
        if not tokens and compact in {"PG", "SG", "SF", "PF", "C"}:
            tokens = (compact,)
    vector = {p: 0.0 for p in ("PG", "SG", "SF", "PF", "C")}
    if not tokens:
        return vector
    weights = (0.65, 0.35) if len(tokens) > 1 else (1.0,)
    for token, weight in zip(tokens, weights):
        if token in vector:
            vector[token] += weight
    total = sum(vector.values())
    return {p: v / total for p, v in vector.items()} if total > 0.0 else vector


def role_mix(positions: Any, season_info_pos: Any = None) -> dict[str, float]:
    """Continuous archetype weights (~0..1) for the pre-shot-clock gates."""

    v = _position_vector(positions, season_info_pos)
    guard = v["PG"] + 0.7 * v["SG"] + 0.2 * v["SF"]
    wing = 0.3 * v["SG"] + v["SF"] + 0.45 * v["PF"]
    big = 0.55 * v["PF"] + v["C"]
    return {
        "guard": _clamp01(guard),
        "wing": _clamp01(wing),
        "frontcourt": _clamp01(big + 0.4 * wing),
        "pivot": _clamp01(big),
        "perimeter": _clamp01(guard + 0.45 * wing),
        # continuous inputs the mid-range rewrite also uses
        "post_raw": big + 0.25 * wing,
        "interior_raw": big + 0.2 * wing,
    }


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


def adjust_values(evidence: Any, positions: Any, values: dict[str, Any]) -> dict[str, Any]:
    """Return a new field->RuleValue map with the pre-shot-clock playstyle applied.

    ``values`` maps field key -> object with ``.value`` (int), ``.source_rule`` (str)
    and ``.evidence_keys`` (tuple). The concrete class is rebuilt via ``type(rv)``.
    """

    if not era_role_playstyle_enabled():
        return values
    era = player_era_context(evidence)
    if era.era_key != _PRE_SHOT_CLOCK_ERA_KEY:
        return values

    season_info = getattr(evidence, "season_info", {}) or {}
    mix = role_mix(positions, season_info.get("pos"))

    out = dict(values)

    def _write(field_key: str, new_value: float, current: Any, provenance: tuple[str, ...]) -> None:
        stored = _clamp_field(field_key, new_value)
        if stored == int(current.value):
            return
        out[field_key] = type(current)(
            value=stored,
            source_rule=f"{current.source_rule}_pre_shot_clock_role_playstyle",
            evidence_keys=tuple(current.evidence_keys) + (f"pre_playstyle_value={int(current.value)}",) + provenance,
        )

    # Blanket era playstyle. The per-player exemption list went with the star
    # profiles, so the era model now applies to every player in the era.
    for adj in _MODEL:
        current = out.get(adj.field)
        if current is None or not isinstance(getattr(current, "value", None), (int, float)):
            continue
        gate = 1.0 if adj.gate is None else mix.get(adj.gate, 0.0)
        if gate <= 0.0:
            continue
        original = float(current.value)
        if _is_demonstrated_floor(adj.field, current):
            continue
        if adj.kind == "scale":
            new_value = original * (1.0 + (adj.amount - 1.0) * gate)
        elif adj.kind == "raise_to":
            new_value = original + (adj.amount - original) * gate if original < adj.amount else original
        else:
            continue
        _write(
            adj.field,
            new_value,
            current,
            (
                f"era_role_playstyle={era.era_key}",
                f"era_role_gate={adj.gate or 'all'}:{gate:.2f}",
                f"era_role_op={adj.kind}:{adj.amount:g}",
                f"era_role_reason={adj.why}",
            ),
        )

    return out


def _clamp_field(field_key: str, value: float) -> int:
    rounded = int(round(value))
    if field_key.startswith("Attributes/"):
        return max(25, min(99, rounded))
    if field_key.startswith("Tendencies/"):
        # Deliberately the raw range: player_rules re-applies the ATD Absolute Cap
        # after this post-pass runs, so the cap has exactly one owner.
        return max(0, min(100, rounded))
    return rounded


__all__ = ["adjust_values", "role_mix", "era_role_playstyle_enabled"]
