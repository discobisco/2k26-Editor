from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AuthoredOpeningRosterMember:
    player_id: str | None
    name: str
    status: str
    preferred_generated_team: str


@dataclass(frozen=True)
class AuthoredOpeningRosterTeam:
    team_name: str
    league: str
    confidence: str
    evidence: str
    members: tuple[AuthoredOpeningRosterMember, ...]


def _member(
    player_id: str | None,
    name: str,
    status: str,
    preferred_generated_team: str,
) -> AuthoredOpeningRosterMember:
    return AuthoredOpeningRosterMember(player_id, name, status, preferred_generated_team)


AUTHORED_OPENING_ROSTERS_1947: tuple[AuthoredOpeningRosterTeam, ...] = (
    AuthoredOpeningRosterTeam(
        team_name='Boston Celtics',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('brighal01', 'Al Brightman', 'locked', 'BOS'),
            _member('connoch01', 'Chuck Connors', 'locked', 'BOS'),
            _member('fenlewa01', 'Bill Fenley', 'locked', 'BOS'),
            _member('graywy01', 'Wyndol Gray', 'locked', 'BOS'),
            _member('hirscme01', 'Mel Hirsch', 'locked', 'BOS'),
            _member('kappeto01', 'Tony Kappen', 'locked', 'BOS'),
            _member('kottmha01', 'Harold Kottman', 'locked', 'BOS'),
            _member('simmoco01', 'Connie Simmons', 'locked', 'BOS'),
            _member('simmojo01', 'Johnny Simmons', 'locked', 'BOS'),
            _member('spectar01', 'Art Spector', 'locked', 'BOS'),
            _member('vaughvi01', 'Virgil Vaughn', 'locked', 'BOS'),
            _member('wallare01', 'Red Wallace', 'locked', 'BOS'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Chicago Stags',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('bakerno01', 'Norm Baker', 'locked', 'CHS'),
            _member('carlsdo01', 'Swede Carlson', 'locked', 'CHS'),
            _member('davisbi01', 'Bill Davis', 'locked', 'CHS'),
            _member('duffybo01', 'Bob Duffy', 'locked', 'CHS'),
            _member('gilmuch01', 'Chuck Gilmur', 'locked', 'CHS'),
            _member('halbech01', 'Chuck Halbert', 'locked', 'CHS'),
            _member('jarosto01', 'Tony Jaros', 'locked', 'CHS'),
            _member('kautzwi01', 'Wilbert Kautz', 'locked', 'CHS'),
            _member('parrado01', 'Doyle Parrack', 'locked', 'CHS'),
            _member('rottnmi01', 'Mickey Rottner', 'locked', 'CHS'),
            _member('seminji01', 'Jim Seminoff', 'locked', 'CHS'),
            _member('zasloma01', 'Max Zaslofsky', 'locked', 'CHS'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Cleveland Rebels',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction plus Grasso opener confirmation',
        members=(
            _member('baumhfr01', 'Frank Baumholtz', 'locked', 'CLR'),
            _member('endrene01', 'Ned Endress', 'locked', 'CLR'),
            _member('faughbo01', 'Bob Faught', 'locked', 'CLR'),
            _member('hermskl01', 'Kleggie Hermsen', 'locked', 'CLR'),
            _member('mogusle01', 'Leo Mogus', 'locked', 'CLR'),
            _member('riebeme01', 'Mel Riebe', 'locked', 'CLR'),
            _member('rotheir01', 'Irv Rothenberg', 'locked', 'CLR'),
            _member('sailoke01', 'Kenny Sailors', 'locked', 'CLR'),
            _member('scharbe01', 'Ben Scharnus', 'locked', 'CLR'),
            _member('schuldi01', 'Dick Schultz', 'locked', 'CLR'),
            _member('shabani01', 'Nick Shaback', 'locked', 'CLR'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Detroit Falcons',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('aubucch01', 'Chet Aubuchon', 'locked', 'DTF'),
            _member('brownha01', 'Harold Brown', 'locked', 'DTF'),
            _member('dillebo01', 'Bill Dille', 'locked', 'DTF'),
            _member('janisjo01', 'John Janisch', 'locked', 'DTF'),
            _member('kingto01', 'Tom King', 'locked', 'DTF'),
            _member('lewisgr01', 'Grady Lewis', 'locked', 'DTF'),
            _member('maughar01', 'Ace Maughan', 'locked', 'DTF'),
            _member('miasest01', 'Stan Miasek', 'locked', 'DTF'),
            _member('pearcge01', 'George Pearcy', 'locked', 'DTF'),
            _member('pearche01', 'Henry Pearcy', 'locked', 'DTF'),
            _member('schoomi01', 'Milt Schoon', 'locked', 'DTF'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='New York Knickerbockers',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('byrneto01', 'Tommy Byrnes', 'locked', 'NYK'),
            _member('cluggbo01', 'Bob Cluggish', 'locked', 'NYK'),
            _member('gottlle01', 'Leo "Ace" Gottlieb', 'locked', 'NYK'),
            _member('hertzso01', 'Sonny Hertzberg', 'locked', 'NYK'),
            _member('kaplora01', 'Ralph Kaplowitz', 'locked', 'NYK'),
            _member('militna01', 'Nat Militzok', 'locked', 'NYK'),
            _member('mullebo01', 'Bob Mullens', 'locked', 'NYK'),
            _member('murphdi01', 'Dick Murphy', 'locked', 'NYK'),
            _member('rosenha01', 'Hank Rosenstein', 'locked', 'NYK'),
            _member('schecos01', 'Ossie Schectman', 'locked', 'NYK'),
            _member('stutzst01', 'Stan Stutz', 'locked', 'NYK'),
            _member('weberja01', 'Jake Weber', 'locked', 'NYK'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Philadelphia Warriors',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction; opener notes retain rostered nonparticipant Jerry Rullo',
        members=(
            _member('dallmho01', 'Howie Dallmar', 'locked', 'PHW'),
            _member('fleisje01', 'Jerry Fleishman', 'locked', 'PHW'),
            _member('fulksjo01', 'Joe Fulks', 'locked', 'PHW'),
            _member('guokama01', 'Matt Guokas', 'locked', 'PHW'),
            _member('hillhar01', 'Art Hillhouse', 'locked', 'PHW'),
            _member('murphjo01', 'John Murphy', 'locked', 'PHW'),
            _member('musian01', 'Angelo Musi', 'locked', 'PHW'),
            _member('rosenpe01', 'Petey Rosenberg', 'locked', 'PHW'),
            _member('rulloje01', 'Jerry Rullo', 'locked', 'PHW'),
            _member('senesge01', 'George Senesky', 'locked', 'PHW'),
            _member('shefffr01', 'Fred Sheffield', 'locked', 'PHW'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Pittsburgh Ironmen',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction; opener notes retain rostered nonparticipant Joe Fabel',
        members=(
            _member('abramjo01', 'John Abramovic', 'locked', 'PIT'),
            _member('beckemo01', 'Moe Becker', 'locked', 'PIT'),
            _member('bytzumi01', 'Mike Bytzura', 'locked', 'PIT'),
            _member('fabeljo01', 'Joe Fabel', 'locked', 'PIT'),
            _member('frankna01', 'Nat Frankel', 'locked', 'PIT'),
            _member('maravpr01', 'Press Maravich', 'locked', 'PIT'),
            _member('melvied01', 'Ed Melvin', 'locked', 'PIT'),
            _member('mihalre01', 'Red Mihalik', 'locked', 'PIT'),
            _member('millewa01', 'Walter Miller', 'locked', 'PIT'),
            _member('millsjo01', 'John Mills', 'locked', 'PIT'),
            _member('noszkst01', 'Stan Noszka', 'locked', 'PIT'),
            _member('zelleha01', 'Hank Zeller', 'locked', 'PIT'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Providence Steam Rollers',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('beendha01', 'Hank Beenders', 'locked', 'PRO'),
            _member('callato01', 'Tom Callahan', 'locked', 'PRO'),
            _member('calveer01', 'Ernie Calverley', 'locked', 'PRO'),
            _member('curear01', 'Armand Cure', 'locked', 'PRO'),
            _member('dehnere01', 'Red Dehnert', 'locked', 'PRO'),
            _member('goodwpo01', 'Pop Goodwin', 'locked', 'PRO'),
            _member('kelleke01', 'Ken Keller', 'locked', 'PRO'),
            _member('martidi01', 'Dino Martin', 'locked', 'PRO'),
            _member('mearnge01', 'George Mearns', 'locked', 'PRO'),
            _member('shannea01', 'Earl Shannon', 'locked', 'PRO'),
            _member('sheabo01', 'Bob Shea', 'locked', 'PRO'),
            _member('spicelo01', 'Lou Spicer', 'locked', 'PRO'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='St. Louis Bombers',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction; all twelve appeared in the first BAA game',
        members=(
            _member('baltihe01', 'Herk Baltimore', 'locked', 'STB'),
            _member('barrjo01', 'Johnny Barr', 'locked', 'STB'),
            _member('davisau01', 'Aubrey Davis', 'locked', 'STB'),
            _member('dollbo01', 'Bob Doll', 'locked', 'STB'),
            _member('hankice01', 'Cecil Hankins', 'locked', 'STB'),
            _member('jacobfr01', 'Fred Jacobs', 'locked', 'STB'),
            _member('loganjo01', 'John Logan', 'locked', 'STB'),
            _member('martido01', 'Don Martin', 'locked', 'STB'),
            _member('munroge01', 'George Munroe', 'locked', 'STB'),
            _member('putnado01', 'Don Putman', 'locked', 'STB'),
            _member('rouxgi01', 'Gifford Roux', 'locked', 'STB'),
            _member('smithde01', 'Deb Smith', 'locked', 'STB'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Toronto Huskies',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley strict November 1 roster; Gino Sovran excluded as a later signing',
        members=(
            _member('biasaha01', 'Hank Biasatti', 'locked', 'TRH'),
            _member('fitzgbo01', 'Bob Fitzgerald', 'locked', 'TRH'),
            _member('fitzgdi01', 'Dick Fitzgerald', 'locked', 'TRH'),
            _member('fucarfr01', 'Frank Fucarino', 'locked', 'TRH'),
            _member('hoefech01', 'Charlie Hoefer', 'locked', 'TRH'),
            _member('hurlero01', 'Roy Hurley', 'locked', 'TRH'),
            _member('mccarmi01', 'Mike McCarron', 'locked', 'TRH'),
            _member('milleha01', 'Harry Miller', 'locked', 'TRH'),
            _member('nostrge01', 'George Nostrand', 'locked', 'TRH'),
            _member('sadowed01', 'Ed Sadowski', 'locked', 'TRH'),
            _member('wertira01', 'Ray Wertis', 'locked', 'TRH'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Washington Capitols',
        league='BAA',
        confidence='A',
        evidence='Robert Bradley opening-day reconstruction checked against first-game box scores',
        members=(
            _member('feeribo01', 'Bob Feerick', 'locked', 'WSC'),
            _member('gillege01', 'Gene Gillette', 'locked', 'WSC'),
            _member('goldfbe01', 'Ben Goldfadden', 'locked', 'WSC'),
            _member('lujacal01', 'Al Lujack', 'locked', 'WSC'),
            _member('mahnkjo01', 'John Mahnken', 'locked', 'WSC'),
            _member('mckinbo01', 'Bones McKinney', 'locked', 'WSC'),
            _member('norlajo01', 'John Norlander', 'locked', 'WSC'),
            _member('negraal01', 'Al Negratti', 'locked', 'WSC'),
            _member('ogradbu01', 'Buddy O’Grady', 'locked', 'WSC'),
            _member('passama01', 'Marty Passaglia', 'locked', 'WSC'),
            _member('scolafr01', 'Fred Scolari', 'locked', 'WSC'),
            _member('torgoir01', 'Irv Torgoff', 'locked', 'WSC'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Fort Wayne Zollner Pistons',
        league='NBL',
        confidence='A',
        evidence='Rodger Nelson early-October ten-man squad',
        members=(
            _member('reisech01', 'Chick Reiser', 'locked', 'FWZ'),
            _member('shippch01', 'Charley Shipp', 'locked', 'FWZ'),
            _member('bushge01', 'Jerry Bush', 'locked', 'FWZ'),
            _member('pelkija01', 'Jake Pelkington', 'locked', 'FWZ'),
            _member('toughbo01', 'Bob Tough', 'locked', 'FWZ'),
            _member('armstcu01', 'Curly Armstrong', 'locked', 'FWZ'),
            _member('kinnebo01', 'Bob Kinney', 'locked', 'FWZ'),
            _member('komenmi01', 'Milo Komenich', 'locked', 'FWZ'),
            _member('towerbl01', 'Carlisle "Blackie" Towery', 'locked', 'FWZ'),
            _member('mcderro01', 'Bobby McDermott', 'locked', 'FWZ'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Chicago American Gears',
        league='NBL',
        confidence='B',
        evidence='November 9 league-opener box score participants; unused bench unresolved',
        members=(
            _member('halebr01', 'Bruce Hale', 'confirmed_opener', 'CAG'),
            _member('brookpr01', 'Price Brookfield', 'confirmed_opener', 'CAG'),
            _member('calihro01', 'Bob Calihan', 'confirmed_opener', 'CAG'),
            _member('mikange01', 'George Mikan', 'confirmed_opener', 'CAG'),
            _member('ratkoge01', 'George Ratkovicz', 'confirmed_opener', 'CAG'),
            _member('szukast01', 'Stan Szukala', 'confirmed_opener', 'CAG'),
            _member('triptdi01', 'Dick Triptow', 'confirmed_opener', 'CAG'),
            _member('patrist01', 'Stan Patrick', 'confirmed_opener', 'CAG'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Oshkosh All-Stars',
        league='NBL',
        confidence='B',
        evidence='November 9 league-opener box score participants; unused bench unresolved',
        members=(
            _member('carpebo01', 'Bob Carpenter', 'confirmed_opener', 'OAS'),
            _member('sulliro01', 'Bob Sullivan', 'confirmed_opener', 'OAS'),
            _member('riskaed01', 'Eddie Riska', 'confirmed_opener', 'OAS'),
            _member('maddoja01', 'Jack Maddox', 'confirmed_opener', 'OAS'),
            _member('edwarle01', 'Leroy "Cowboy" Edwards', 'confirmed_opener', 'OAS'),
            _member('engluge01', 'Gene Englund', 'confirmed_opener', 'OAS'),
            _member('wagercl01', 'Clint Wager', 'confirmed_opener', 'OAS'),
            _member('vaughra02', 'Ralph Vaughn', 'confirmed_opener', 'OAS'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Buffalo Bisons',
        league='NBL',
        confidence='B+/C',
        evidence='Buffalo opening-program and Buffalo-only chronology reconstruction',
        members=(
            _member('ottendo01', 'Don Otten', 'probable', 'TCB'),
            _member('gateswi01', 'Pop Gates', 'probable', 'TCB'),
            _member('grunzni01', 'Nick Grunzweig', 'probable', 'TCB'),
            _member('hassebi01', 'Billy Hassett', 'probable', 'TCB'),
            _member('hickena01', 'Nat Hickey', 'probable', 'TCB'),
            _member('raderle01', 'Len Rader', 'probable', 'TCB'),
            _member('raderho01', 'Howie Rader', 'probable', 'TCB'),
            _member('simsbo01n', 'Bob Sims', 'probable', 'TCB'),
            _member('starzri01', 'Dick Starzyk', 'probable', 'TCB'),
            _member('waxmast01', 'Stan Waxman', 'probable', 'TCB'),
            _member(None, 'Bob Daughtery', 'probable_unused_reserve_no_generated_source', 'TCB'),
            _member(None, 'Mark Marlaire', 'probable_unused_reserve_no_generated_source', 'TCB'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Rochester Royals',
        league='NBL',
        confidence='B+',
        evidence='1946-47 team photograph and opening-season chronology',
        members=(
            _member('daviebo01', 'Bob Davies', 'strong_early_squad', 'RCR'),
            _member('cervial01', 'Al Cervi', 'strong_early_squad', 'RCR'),
            _member('holzmre01', 'Red Holzman', 'strong_early_squad', 'RCR'),
            _member('glamage01', 'George Glamack', 'strong_early_squad', 'RCR'),
            _member('johnsar01', 'Arnie Johnson', 'strong_early_squad', 'RCR'),
            _member('levanan01', 'Fuzzy Levane', 'strong_early_squad', 'RCR'),
            _member('kingwi01', 'Dolly King', 'strong_early_squad', 'RCR'),
            _member('garfija01', 'Dutch Garfinkel', 'strong_early_squad', 'RCR'),
            _member('quinlji01', 'Jim Quinlan', 'strong_early_squad', 'RCR'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Indianapolis Kautskys',
        league='NBL',
        confidence='B+',
        evidence='Season-use chronology; eleven-player reconstruction retained provisionally',
        members=(
            _member('klierle01', 'Leo Klier', 'provisional', 'INK'),
            _member('doernwi01', 'Gus Doerner', 'provisional', 'INK'),
            _member('risenar01', 'Arnie Risen', 'provisional', 'INK'),
            _member('andreer01', 'Ernie Andres', 'provisional', 'INK'),
            _member('schaehe01', 'Herm Schaefer', 'provisional', 'INK'),
            _member('clossbi01', 'Bill Closs', 'provisional', 'INK'),
            _member('dietzro01', 'Bob Dietz', 'provisional', 'INK'),
            _member('norriel01', 'Woody Norris', 'provisional', 'INK'),
            _member('gallolo01', 'Lowell Galloway', 'provisional', 'INK'),
            _member('smithdo01', 'Don Smith', 'provisional', 'INK'),
            _member('thompho03', 'Homer Thompson', 'provisional', 'INK'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Toledo Jeeps',
        league='NBL',
        confidence='C+',
        evidence='Opening-core reconstruction; unresolved bench omitted',
        members=(
            _member('tidriha01', 'Hal Tidrick', 'strong_opening_core', 'TLJ'),
            _member('sobekch01', 'George Sobek', 'strong_opening_core', 'TLJ'),
            _member('gerbero01', 'Bob Gerber', 'strong_opening_core', 'TLJ'),
            _member('hamilda01', 'Dale Hamilton', 'strong_opening_core', 'TLJ'),
            _member('rivliju01', 'Julie Rivlin', 'strong_opening_core', 'TLJ'),
            _member('schicjo01', 'Johnny Schick', 'strong_opening_core', 'TLJ'),
            _member('seymopa01', 'Paul Seymour', 'strong_opening_core', 'TLJ'),
            _member('patanjo01', 'Joe Patanelli', 'strong_opening_core', 'TLJ'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Syracuse Nationals',
        league='NBL',
        confidence='C',
        evidence='Opening-core reconstruction with later arrivals excluded',
        members=(
            _member('meehajo01', 'Chick Meehan', 'probable', 'SYN'),
            _member('chanejo01', 'John Chaney', 'probable', 'SYN'),
            _member('nelmage01', 'George Nelmark', 'probable', 'SYN'),
            _member('rizzoje01', 'Jerry Rizzo', 'probable', 'SYN'),
            _member('geejo01', 'Johnny Gee', 'probable', 'SYN'),
            _member('nugenro01', 'Bob Nugent', 'probable', 'SYN'),
            _member('mccahwi01', 'Bill McCahan', 'probable', 'SYN'),
            _member('rothmle01', 'Les Rothman', 'probable', 'SYN'),
            _member('moisejo01', 'John Moiseichik', 'probable', 'SYN'),
            _member('synnoro01', 'Bob Synnott', 'probable', 'SYN'),
            _member('possnlo01', 'Lou Possner', 'probable', 'SYN'),
            _member('butlech01', 'Charlie Butler', 'probable', 'SYN'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Youngstown Bears',
        league='NBL',
        confidence='C',
        evidence='Opening-core reconstruction; unresolved fringe omitted',
        members=(
            _member('ticcomi01', 'Milt Ticco', 'strong_opening_core', 'YNB'),
            _member('mehenbe01', 'Bernie Mehen', 'strong_opening_core', 'YNB'),
            _member('farrobi01', 'Bill Farrow', 'strong_opening_core', 'YNB'),
            _member('joachch01', 'Charlie Joachim', 'strong_opening_core', 'YNB'),
            _member('hermapa01', 'Paul Herman', 'strong_opening_core', 'YNB'),
            _member('sattlwi01', 'Bill Sattler', 'strong_opening_core', 'YNB'),
            _member('shannfr01', 'Frank Shannon', 'strong_opening_core', 'YNB'),
            _member('moelled01', 'Ed Moeller', 'strong_opening_core', 'YNB'),
            _member('bosakjo01', 'John Bosak', 'strong_opening_core', 'YNB'),
            _member('schuwi01', 'Wilbur Schu', 'strong_opening_core', 'YNB'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Anderson Duffey Packers',
        league='NBL',
        confidence='C+',
        evidence='Probable opening roster; two fringe positions remain uncertain',
        members=(
            _member('hapacwi01', 'Bill Hapac', 'probable', 'ADP'),
            _member('stanced01', 'Ed Stanczak', 'probable', 'ADP'),
            _member('schulho01', 'Howie Schultz', 'probable', 'ADP'),
            _member('seltzro01', 'Rollie Seltz', 'probable', 'ADP'),
            _member('gaineel01', 'Elmer Gainer', 'probable', 'ADP'),
            _member('lewined01', 'Ed Lewinski', 'probable', 'ADP'),
            _member('bolyaro01', 'Bob Bolyard', 'probable', 'ADP'),
            _member('gatesfr01', 'Frank Gates', 'probable', 'ADP'),
            _member('moreyda01', 'Dale Morey', 'probable', 'ADP'),
            _member('fureyri01', 'Dick Furey', 'probable', 'ADP'),
            _member('stantjo01', 'Jack Stanton', 'probable', 'ADP'),
            _member('gardnbe01', 'Ben Gardner', 'probable', 'ADP'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Detroit Gems',
        league='NBL',
        confidence='C',
        evidence='Strong opening/early core; unresolved bench omitted',
        members=(
            _member('lorande01', 'Del Loranger', 'strong_early_core', 'DTG'),
            _member('latteda01', 'Dave Latter', 'strong_early_core', 'DTG'),
            _member('juntupa01', 'Paul Juntunen', 'strong_early_core', 'DTG'),
            _member('campbfr01', 'Fred Campbell', 'strong_early_core', 'DTG'),
            _member('parryed01', 'Ed Parry', 'strong_early_core', 'DTG'),
            _member('schefhe01', 'Herb Scheffler', 'strong_early_core', 'DTG'),
            _member('mccarho01', 'Howie McCarty', 'strong_early_core', 'DTG'),
            _member('dykstro01', 'Bob Dykstra', 'strong_early_core', 'DTG'),
            _member('czarnwa01', 'Walt Czarnecki', 'strong_early_core', 'DTG'),
        ),
    ),
    AuthoredOpeningRosterTeam(
        team_name='Sheboygan Red Skins',
        league='NBL',
        confidence='C+',
        evidence='Opening core plus documented pre-transfer players; unresolved reserves omitted',
        members=(
            _member('harrilu03', 'Luther Harris', 'strong_opening_core', 'SHR'),
            _member('lewisfr01', 'Fred Lewis', 'strong_opening_core', 'SHR'),
            _member('dancked01', 'Ed Dancker', 'strong_opening_core', 'SHR'),
            _member('lautere01', 'Rube Lautenschlager', 'strong_opening_core', 'SHR'),
            _member('holmro01', 'Bobby Holm', 'strong_opening_core', 'SHR'),
            _member('lucasal01', 'Al Lucas', 'strong_opening_core', 'SHR'),
            _member('greneal01', 'Al Grenert', 'strong_opening_core', 'SHR'),
            _member('sueseke01', 'Kenny Suesens', 'strong_opening_core', 'SHR'),
            _member('novakmi01', 'Mike Novak', 'strong_opening_core', 'SHR'),
            _member('sharkst01', 'Steve Sharkey', 'strong_opening_core', 'SHR'),
        ),
    ),
)


AUTHORED_OPENING_ROSTER_TEAMS_1947 = {team.team_name: team for team in AUTHORED_OPENING_ROSTERS_1947}
AUTHORED_OPENING_ROSTER_BY_PLAYER_ID_1947 = {
    member.player_id: (team, member)
    for team in AUTHORED_OPENING_ROSTERS_1947
    for member in team.members
    if member.player_id is not None
}


def authored_opening_rosters_for_season(season: int) -> tuple[AuthoredOpeningRosterTeam, ...]:
    return AUTHORED_OPENING_ROSTERS_1947 if int(season) == 1947 else ()


def _validate_authored_rosters() -> None:
    team_names = tuple(team.team_name for team in AUTHORED_OPENING_ROSTERS_1947)
    if len(team_names) != len(set(team_names)):
        raise ValueError("duplicate authored 1947 opening-roster team")
    player_ids = tuple(
        member.player_id
        for team in AUTHORED_OPENING_ROSTERS_1947
        for member in team.members
        if member.player_id is not None
    )
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("a 1947 opening-roster player ID is authored for more than one team")


_validate_authored_rosters()


__all__ = [
    "AUTHORED_OPENING_ROSTER_BY_PLAYER_ID_1947",
    "AUTHORED_OPENING_ROSTER_TEAMS_1947",
    "AUTHORED_OPENING_ROSTERS_1947",
    "AuthoredOpeningRosterMember",
    "AuthoredOpeningRosterTeam",
    "authored_opening_rosters_for_season",
]
