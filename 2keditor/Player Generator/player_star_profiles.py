"""Named-player calling cards and documented limitations, 1947-1954 (pre-shot-clock).

The blanket ``player_era_role`` playstyle pass pushes every archetype toward the era
default. A handful of players are documented as genuine exceptions to that default --
Bob Davies really did dribble behind his back, Joe Fulks really did take turnaround
jumpers off the catch, Jim Pollard really did dunk. This registry records those,
plus the *explicitly stated* negatives (Fulks' foot speed and defense, Sadowski's
ball dominance), so the era pass does not both erase a player's signature skill and
leave the era default in its place.

Sourced from ``mappings/STAR_PLAYERS.md`` -- itself an evidence file, not a rating
instruction. The interpretation into fields lives here, with the STAR_PLAYERS.md
citation numbers carried through to each player's ``evidence`` tuple.

Rules kept from STAR_PLAYERS.md:
  * "Not a documented calling card / unresolved" is NOT a weakness. A ``limit`` is
    recorded only where a source explicitly states the negative.
  * ``exempt`` names ``_MODEL`` tags whose era suppression does not apply to this
    player. ``boost`` / ``limit`` are ``(field, op, amount)`` with op in
    {raise_to, cap, scale}; they are applied after the era pass and are not
    position-gated (the player identity is the gate).

Controlled by the same env switch as the era pass (``PLAYERGEN_ERA_ROLE_PLAYSTYLE``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StarProfile:
    player_id: str  # upper-case Basketball-Reference id
    name: str  # display only
    exempt: frozenset[str] = frozenset()
    boost: tuple[tuple[str, str, float], ...] = ()
    limit: tuple[tuple[str, str, float], ...] = ()
    evidence: tuple[str, ...] = ()
    first_season: int = 1947
    last_season: int = 1954


_PROFILES: tuple[StarProfile, ...] = (
        # -- 1940s league dossiers ------------------------------------------------
        StarProfile(
            player_id="DAVIEBO01",
            name="Bob Davies",
            exempt=frozenset({"handle", "flair_pass", "ball_dominant"}),
            boost=(
                ("Attributes/BALLCONTROL", "raise_to", 86),
                ("Attributes/SPEEDWITHBALL", "raise_to", 82),
                ("Attributes/PASSVISION", "raise_to", 74),
                ("Attributes/PASSIQ", "raise_to", 74),
                ("Attributes/PASSACCURACY", "raise_to", 72),
                ("Tendencies/DRIVINGBEHINDTHEBACK", "raise_to", 42),
                ("Tendencies/DRIVINGDRIBBLEHESITATION", "raise_to", 35),
                ("Tendencies/FLASHYPASS", "raise_to", 42),
                ("Tendencies/DISHTOOPENMAN", "raise_to", 60),
            ),
            evidence=(
                "STAR_PLAYERS.md#bob-davies",
                "hoophall.com/hall-of-famers/bob-davies[22]",
                "givemesport 1940s top-5[2]",
                "behind-the-back/through-legs/over-head 'not to show off but to produce results'",
                "led the league in assists 1949; 'innovative playmaker and steady floor general'",
                "no sourced negative on shooting/defense/rebounding -> no limit recorded",
            ),
            last_season=1955,
        ),
        StarProfile(
            player_id="FULKSJO01",
            name="Joe Fulks",
            exempt=frozenset({"off_dribble_jumper", "volume_jumper", "post_hub"}),
            boost=(
                ("Attributes/MIDRANGE", "raise_to", 74),
                ("Attributes/POSTFADE", "raise_to", 62),
                ("Tendencies/MIDSHOT", "raise_to", 62),
                ("Tendencies/MIDSPOTUPSHOT", "raise_to", 60),
                ("Tendencies/MIDOFFSCREENSHOT", "raise_to", 45),
                ("Tendencies/SPINJUMPER", "raise_to", 40),
                ("Tendencies/STEPBACKJUMPERMID", "raise_to", 28),
                ("Tendencies/SHOT", "raise_to", 70),
            ),
            limit=(
                # "relatively slow-footed" -> below-average lateral tools
                ("Attributes/SPEED", "cap", 60),
                ("Attributes/AGILITY", "cap", 60),
                # "defense was uninspired" -> a coherent below-average defensive card
                # (not bottom-of-league). INTERIORDEFENSE is capped too so the broken
                # team-DWS rule doesn't leave him an elite interior / poor perimeter defender.
                ("Attributes/PERIMETERDEFENSE", "cap", 48),
                ("Attributes/INTERIORDEFENSE", "cap", 50),
                ("Attributes/DEFENSECONSISTENCY", "cap", 48),
                ("Attributes/HELPDEFENSE", "cap", 50),
                ("Attributes/STEAL", "cap", 48),
                ("Attributes/BLOCK", "cap", 46),
                # "not a strong rebounder"
                ("Attributes/OFFENSIVEREBOUND", "cap", 52),
                ("Attributes/DEFENSEREBOUND", "cap", 58),
            ),
            evidence=(
                "STAR_PLAYERS.md#joe-fulks",
                "nba.com/news/history-nba-legend-joe-fulks[5]",
                "airborne one-handed shot after L/R spin, midair hand transfer, turnaround, running shots",
                "'high-volume shooting from multiple locations rather than only low-post finishing'",
                "EXPLICIT negatives: 'relatively slow-footed', 'defense was uninspired', 'not a strong rebounder' -> below-average, not bottom-tier",
            ),
        ),
        StarProfile(
            player_id="MIKANGE01",
            name="George Mikan",
            boost=(
                ("Attributes/POSTHOOK", "raise_to", 90),
                # the Mikan Drill *is* post footwork -- trained, obsessive, alternating
                # hands, the benchmark of the era. POSTCONTROL is his 99.
                ("Attributes/POSTCONTROL", "raise_to", 99),
                ("Attributes/CLOSESHOT", "raise_to", 80),
                # trained footwork / side-to-side movement / running work -- the source
                # explicitly says this was built, NOT "an automatic product of height",
                # yet the body rules floor him at ~27 for being 6-10 / 245. Still a giant:
                # SPEED (end-to-end foot speed) stays mid-30s; AGILITY (post footwork /
                # change of direction, his actual trained edge) sits clearly above it.
                ("Attributes/AGILITY", "raise_to", 55),
                ("Attributes/SPEED", "raise_to", 35),
                ("Tendencies/POSTHOOKLEFT", "raise_to", 55),
                ("Tendencies/POSTHOOKRIGHT", "raise_to", 55),
                ("Tendencies/USEGLASS", "raise_to", 55),
                ("Tendencies/POSTUP", "raise_to", 92),
            ),
            limit=(
                # a back-to-the-basket pivot, not a driver -- his finishing was hooks
                # and close shots off the block, not driving layups.
                ("Attributes/DRIVINGLAYUP", "cap", 65),
            ),
            evidence=(
                "STAR_PLAYERS.md#george-mikan",
                "nba.com/news/history-nba-legend-george-mikan[3]",
                "hoophall[20]",
                "'soft, deadly hook shot'; Mikan Drill alternating L/R finishes off the glass",
                "'relentless footwork, agility, side-to-side movement, and running work... rather than being treated as an automatic product of height'",
                "'one of the first big men to run the floor and finish with force'",
                "defense already set by player_special_rules (INTERIORDEFENSE 99 / PERIMETERDEFENSE 36, 1947 NBL)",
            ),
            last_season=1956,
        ),
        StarProfile(
            player_id="POLLAJI01",
            name="Jim Pollard",
            exempt=frozenset({"showtime_finish"}),
            boost=(
                ("Attributes/VERTICAL", "raise_to", 92),
                # The "dunk from the foul line / top of the backboard" leaping shows up
                # in DRIVING dunk (run-up, hang time). A STANDING dunk he still has to
                # get up and over a Mikan or an Otten from a standstill at 6-4, so it
                # caps well below his driving number. Set directly: the base standing-
                # dunk rule reads the pre-star VERTICAL.
                ("Attributes/DRIVINGDUNK", "raise_to", 88),
                ("Attributes/STANDINGDUNK", "raise_to", 70),
                ("Attributes/MIDRANGE", "raise_to", 76),
                ("Tendencies/DRIVINGDUNK", "raise_to", 30),
                ("Tendencies/MIDSPOTUPSHOT", "raise_to", 55),
                ("Tendencies/MIDOFFSCREENSHOT", "raise_to", 40),
            ),
            evidence=(
                "STAR_PLAYERS.md#jim-pollard",
                "hoophall.com/hall-of-famers/jim-pollard[23]",
                "givemesport[2]",
                "'deadly corner jump shot... nearly perfect'; 'touch top of backboard and dunk from the foul line'",
                "'one of the early players who made dunking visible in the professional game' -> he DID dunk in games",
                "team-first ('winning mattered more than scoring') is a priority, not a rating weakness -> no limit",
            ),
            last_season=1955,
        ),
        StarProfile(
            player_id="DALLMHO01",
            name="Howie Dallmar",
            boost=(
                ("Attributes/PASSACCURACY", "raise_to", 66),
                ("Attributes/PASSIQ", "raise_to", 66),
                ("Tendencies/DISHTOOPENMAN", "raise_to", 55),
            ),
            evidence=(
                "STAR_PLAYERS.md#howie-dallmar",
                "one of only four >100-assist players in 1946-47[25]",
                "title-clinching outside shot 1947 Finals G5 is an anecdote, not a shot-repertoire claim",
            ),
            last_season=1949,
        ),
        StarProfile(
            player_id="SADOWED01",
            name="Ed Sadowski",
            boost=(
                ("Tendencies/SHOT", "raise_to", 66),
                ("Tendencies/TOUCHES", "raise_to", 70),
                ("Attributes/OFFENSIVECONSISTENCY", "raise_to", 66),
            ),
            limit=(
                ("Tendencies/DISHTOOPENMAN", "cap", 30),
                ("Tendencies/PLAYDISCIPLINE", "cap", 30),
                ("Attributes/PASSVISION", "cap", 45),
            ),
            evidence=(
                "STAR_PLAYERS.md#ed-sadowski",
                "CelticsLife[21]: 3rd in league scoring 1947-48",
                "EXPLICIT negative: ball dominance -- 'stopped a game... demanded the ball'",
            ),
            last_season=1950,
        ),
        StarProfile(
            player_id="SEMINJI01",
            name="Jim Seminoff",
            boost=(
                ("Attributes/PASSACCURACY", "raise_to", 70),
                ("Attributes/PASSIQ", "raise_to", 70),
                ("Attributes/PASSVISION", "raise_to", 68),
                ("Tendencies/DISHTOOPENMAN", "raise_to", 55),
            ),
            limit=(("Tendencies/SHOT", "cap", 48),),
            evidence=(
                "STAR_PLAYERS.md#jim-seminoff",
                "CelticsLife[21]: 3rd/6th/8th in league assists 1948-1950; documented identity is playmaking",
                "'explicitly... not a flashy scorer' -> modest shot tendency, not a skill weakness",
            ),
            last_season=1950,
        ),
        StarProfile(
            player_id="LAVELTO01",
            name="Tony Lavelli",
            boost=(("Attributes/MIDRANGE", "raise_to", 62),),
            limit=(
                ("Attributes/STRENGTH", "cap", 48),
                ("Attributes/HUSTLE", "cap", 46),
            ),
            evidence=(
                "STAR_PLAYERS.md#tony-lavelli",
                "CelticsLife[21]: 'a shooter from Yale' (weak source); halftime accordion act",
                "EXPLICIT: 'toughness was not his calling card'",
            ),
            first_season=1950,
            last_season=1951,
        ),
        # -- 1950-1954 (still pre-shot-clock) -----------------------------------
        StarProfile(
            player_id="MIKKEVE01",
            name="Vern Mikkelsen",
            boost=(
                ("Attributes/STRENGTH", "raise_to", 78),
                ("Attributes/INTERIORDEFENSE", "raise_to", 72),
                ("Attributes/DEFENSEREBOUND", "raise_to", 80),
                ("Attributes/OFFENSIVEREBOUND", "raise_to", 72),
                ("Tendencies/POSTUP", "raise_to", 70),
                ("Tendencies/FOUL", "raise_to", 60),
            ),
            evidence=(
                "STAR_PLAYERS.md#vern-mikkelsen",
                "hoophall[11]: 'one of the first true power forwards'; paint scoring, intense rebounding, physical defense",
                "durable (699/704 games); Bleacher[1] foul accumulation (weaker source -> modest FOUL bump only)",
            ),
            first_season=1950,
            last_season=1956,
        ),
        StarProfile(
            player_id="GALLAHA01",
            name="Harry Gallatin",
            boost=(
                ("Attributes/STRENGTH", "raise_to", 80),
                ("Attributes/HUSTLE", "raise_to", 85),
                ("Attributes/INTANGIBLES", "raise_to", 70),
                ("Attributes/DEFENSEREBOUND", "raise_to", 85),
                ("Attributes/OFFENSIVEREBOUND", "raise_to", 78),
            ),
            evidence=(
                "STAR_PLAYERS.md#harry-gallatin",
                "hoophall[12]: 'playing hard', 'tremendous physical strength', led league rebounding 1954, 682 straight games",
            ),
            first_season=1949,
            last_season=1956,
        ),
        StarProfile(
            player_id="SCHAYDO01",
            name="Dolph Schayes",
            boost=(
                ("Attributes/MIDRANGE", "raise_to", 78),
                ("Tendencies/MIDSPOTUPSHOT", "raise_to", 55),
                ("Attributes/DEFENSEREBOUND", "raise_to", 85),
                ("Attributes/OFFENSIVEREBOUND", "raise_to", 76),
                ("Attributes/PASSACCURACY", "raise_to", 66),
            ),
            evidence=(
                "STAR_PLAYERS.md#dolph-schayes",
                "nba.com/news/history-nba-legend-dolph-schayes[6]",
                "'remained a two-handed SET shooter' -> era set-shot treatment is correct, no shooting exemption",
                "led league in rebounding when first compiled; among assist leaders; trained FT (14-inch hoop)[17]",
            ),
            first_season=1949,
            last_season=1956,
        ),
        StarProfile(
            player_id="MACAUED01",
            name="Ed Macauley",
            boost=(
                ("Attributes/DRIVINGLAYUP", "raise_to", 72),
                ("Attributes/POSTHOOK", "raise_to", 72),
                ("Attributes/SPEED", "raise_to", 70),
                ("Attributes/AGILITY", "raise_to", 72),
                ("Tendencies/FROMPOSTSHOT", "raise_to", 55),
            ),
            evidence=(
                "STAR_PLAYERS.md#ed-macauley",
                "hoophall[14]: 'glided down NBA lanes for easy layups and precise hook shots'; mobility frustrated bigs",
                "finesse identity; 'bruising' is not-a-calling-card (unresolved) -> no strength limit per STAR_PLAYERS rules",
            ),
            first_season=1950,
            last_season=1956,
        ),
        StarProfile(
            player_id="SHARMBI01",
            name="Bill Sharman",
            boost=(
                ("Attributes/MIDRANGE", "raise_to", 82),
                ("Tendencies/MIDSPOTUPSHOT", "raise_to", 58),
                ("Attributes/PERIMETERDEFENSE", "raise_to", 70),
                ("Attributes/DEFENSECONSISTENCY", "raise_to", 66),
                ("Tendencies/ONBALLSTEAL", "raise_to", 55),
            ),
            limit=(
                ("Attributes/BALLCONTROL", "cap", 62),
                ("Attributes/PASSVISION", "cap", 55),
            ),
            evidence=(
                "STAR_PLAYERS.md#bill-sharman",
                "nba.com[28]: 'arguably the greatest shooter of his era'; 'fierce, aggressive defensive style'; toughness",
                "'The source does not identify him as Boston's main dribble creator; Cousy is' -> handle/vision capped",
            ),
            first_season=1951,
            last_season=1956,
        ),
        StarProfile(
            player_id="ARIZIPA01",
            name="Paul Arizin",
            exempt=frozenset({"off_dribble_jumper", "volume_jumper", "drive", "handle"}),
            boost=(
                ("Attributes/MIDRANGE", "raise_to", 80),
                ("Attributes/VERTICAL", "raise_to", 78),
                ("Attributes/PERIMETERDEFENSE", "raise_to", 65),
                ("Attributes/OFFENSIVEREBOUND", "raise_to", 60),
                ("Attributes/DEFENSEREBOUND", "raise_to", 66),
                ("Tendencies/DRIVE", "raise_to", 45),
                ("Tendencies/DRIVINGLAYUP", "raise_to", 55),
            ),
            evidence=(
                "STAR_PLAYERS.md#paul-arizin",
                "nba.com[29] / hoophall[15]: 'jump shot that only a few players had mastered'; low line-drive release",
                "'great leaper, slick ballhandler, tough defender'; 'inside scoring and spectacular, acrobatic drives'",
                "EXPLICIT: 'NOT a surviving set-shot specialist... defining weapon was the then-new jump shot'",
            ),
            first_season=1951,
            last_season=1956,
        ),
        StarProfile(
            player_id="JOHNSNE01",
            name="Neil Johnston",
            boost=(
                ("Attributes/POSTHOOK", "raise_to", 88),
                ("Attributes/POSTCONTROL", "raise_to", 78),
                ("Attributes/CLOSESHOT", "raise_to", 74),
                ("Tendencies/FROMPOSTSHOT", "raise_to", 60),
                ("Tendencies/POSTHOOKLEFT", "raise_to", 45),
                ("Attributes/OFFENSIVEREBOUND", "raise_to", 72),
                ("Attributes/DEFENSEREBOUND", "raise_to", 74),
            ),
            evidence=(
                "STAR_PLAYERS.md#neil-johnston",
                "hoophall[16]: 'devastating sweeping hook shot from the pivot'; led league scoring/rebounding/FG% at times",
            ),
            first_season=1952,
            last_season=1956,
        ),
        StarProfile(
            player_id="COUSYBO01",
            name="Bob Cousy",
            exempt=frozenset({"handle", "flair_pass", "ball_dominant", "fast_break"}),
            boost=(
                ("Attributes/BALLCONTROL", "raise_to", 90),
                ("Attributes/SPEEDWITHBALL", "raise_to", 85),
                ("Attributes/PASSVISION", "raise_to", 90),
                ("Attributes/PASSIQ", "raise_to", 85),
                ("Attributes/PASSACCURACY", "raise_to", 80),
                ("Tendencies/FLASHYPASS", "raise_to", 70),
                ("Tendencies/DRIVINGBEHINDTHEBACK", "raise_to", 45),
                ("Tendencies/DRIBBLESPIN", "raise_to", 35),
                ("Tendencies/DISHTOOPENMAN", "raise_to", 70),
                ("Tendencies/TRANSITIONSPOTUP", "raise_to", 45),
            ),
            evidence=(
                "STAR_PLAYERS.md#bob-cousy",
                "nba.com[8]: fast-break engine; 'no-look, spinning, behind-the-back, and long rocket passes'",
                "childhood right-arm injury -> ambidextrous handle/shot; flair repeatedly tied to finding scorers",
                "defense unresolved -> no limit",
            ),
            first_season=1951,
            last_season=1956,
        ),
        StarProfile(
            player_id="YARDLGE01",
            name="George Yardley",
            exempt=frozenset({"off_dribble_jumper"}),
            boost=(
                ("Attributes/MIDRANGE", "raise_to", 75),
                ("Attributes/VERTICAL", "raise_to", 80),
                ("Attributes/DRIVINGDUNK", "raise_to", 58),
                ("Tendencies/SHOT", "raise_to", 62),
            ),
            evidence=(
                "STAR_PLAYERS.md#george-yardley",
                "hoophall[38]: 'spring-legged jump shooter and defense-commanding scorer'; 'flamboyant scoring machine'",
            ),
            first_season=1954,
            last_season=1956,
        ),
)

STAR_PROFILES: dict[str, StarProfile] = {profile.player_id: profile for profile in _PROFILES}


def star_profile_for(player_id: str, season: int) -> StarProfile | None:
    profile = STAR_PROFILES.get(str(player_id or "").strip().upper())
    if profile is None:
        return None
    if season < profile.first_season or season > profile.last_season:
        return None
    return profile


__all__ = ["StarProfile", "STAR_PROFILES", "star_profile_for"]
