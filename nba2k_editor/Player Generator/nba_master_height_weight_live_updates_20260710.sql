-- NBA_DATA_Master height/weight updates from exact live game roster matches.
-- Source DB: nba2k_editor/Player Generator/NBA Player Data/NBA_DATA_Master.sqlite
-- NBA Player Data/ is gitignored; this SQL records the data edits for repo history.

BEGIN TRANSACTION;

UPDATE player_info SET ht_in_in = 75, wt = 190 WHERE player_id = 'gardnbe01' AND player = 'Ben Gardner';
UPDATE player_info SET ht_in_in = 74, wt = 200 WHERE player_id = 'hapacwi01' AND player = 'Bill Hapac';
UPDATE player_info SET ht_in_in = 72, wt = 186 WHERE player_id = 'bolyaro01' AND player = 'Bob Bolyard';
UPDATE player_info SET ht_in_in = 76, wt = 180 WHERE player_id = 'perrych01' AND player = 'Charles Perry';
UPDATE player_info SET ht_in_in = 75, wt = 205 WHERE player_id = 'hawlech01' AND player = 'Chuck Hawley';
UPDATE player_info SET ht_in_in = 72, wt = 180 WHERE player_id = 'moreyda01' AND player = 'Dale Morey';
UPDATE player_info SET ht_in_in = 75, wt = 175 WHERE player_id = 'lorande01' AND player = 'Del Loranger';
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'fureyri01' AND player = 'Dick Furey';
UPDATE player_info SET ht_in_in = 74, wt = 185 WHERE player_id = 'parryed01' AND player = 'Eddie Parry';
UPDATE player_info SET ht_in_in = 76, wt = 220 WHERE player_id = 'mekulfr01' AND player = 'Frank Mekules';
UPDATE player_info SET ht_in_in = 73, wt = 190 WHERE player_id = 'sabofr01' AND player = 'Frank Sabo';
UPDATE player_info SET ht_in_in = 76, wt = 220 WHERE player_id = 'schefhe01' AND player = 'Herb Scheffler';
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'hoffmho01' AND player = 'Howie Hoffman';
UPDATE player_info SET ht_in_in = 73, wt = 190 WHERE player_id = 'wilkiru01' AND player = 'Russ Wilkin';
UPDATE player_info SET ht_in_in = 78, wt = 215 WHERE player_id = 'meyerto01' AND player = 'Tom Meyer';
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'waddeva01' AND player = 'Vaughn Waddell';
UPDATE player_info SET ht_in_in = 67, wt = 155 WHERE player_id = 'kingwi02' AND player = 'Willie King';
UPDATE player_info SET ht_in_in = 71, wt = 150 WHERE player_id = 'wertira01' AND player = 'Ray Wertis';

COMMIT;

-- NBA_DATA_Master height/weight updates from Basketball-Reference NBL pages.
BEGIN TRANSACTION;
UPDATE player_info SET ht_in_in = 72, wt = 175 WHERE player_id = 'rodriab01' AND player = 'Abel Rodrigues'; -- https://www.basketball-reference.com/nbl/players/r/rodriab01n.html
UPDATE player_info SET ht_in_in = 76, wt = 210 WHERE player_id = 'bakerar01' AND player = 'Art Bakeraitis'; -- https://www.basketball-reference.com/nbl/players/b/bakerar01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'grovero01' AND player = 'Art Grove'; -- https://www.basketball-reference.com/nbl/players/g/grovero01n.html
UPDATE player_info SET ht_in_in = 71, wt = 170 WHERE player_id = 'schalbe01' AND player = 'Benny Schall'; -- https://www.basketball-reference.com/nbl/players/s/schalbe01n.html
UPDATE player_info SET ht_in_in = 73, wt = 185 WHERE player_id = 'drummbe01' AND player = 'Beryl Drummond'; -- https://www.basketball-reference.com/nbl/players/d/drummbe01n.html
UPDATE player_info SET ht_in_in = 75, wt = 205 WHERE player_id = 'brownbi01' AND player = 'Bill Brown'; -- https://www.basketball-reference.com/nbl/players/b/brownbi01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'devenwi01' AND player = 'Bill DeVenzio'; -- https://www.basketball-reference.com/nbl/players/d/devenwi01n.html
UPDATE player_info SET ht_in_in = 75, wt = 205 WHERE player_id = 'durkewi01' AND player = 'Bill Durkee'; -- https://www.basketball-reference.com/nbl/players/d/durkewi01n.html
UPDATE player_info SET ht_in_in = 80, wt = 220 WHERE player_id = 'gruenro01' AND player = 'Bob Gruenig'; -- https://www.basketball-reference.com/nbl/players/g/gruenro01n.html
UPDATE player_info SET ht_in_in = 72, wt = 180 WHERE player_id = 'kittero01' AND player = 'Bob Kitterman'; -- https://www.basketball-reference.com/nbl/players/k/kittero01n.html
UPDATE player_info SET ht_in_in = 72, wt = 175 WHERE player_id = 'oshaubo01' AND player = 'Bob O''Shaughnessy'; -- https://www.basketball-reference.com/nbl/players/o/oshaubo01n.html
UPDATE player_info SET ht_in_in = 73, wt = 160 WHERE player_id = 'shaddro01' AND player = 'Bob Shaddock'; -- https://www.basketball-reference.com/nbl/players/s/shaddro01n.html
UPDATE player_info SET ht_in_in = 76, wt = 225 WHERE player_id = 'shawro01' AND player = 'Bob Shaw'; -- https://www.basketball-reference.com/nbl/players/s/shawro01n.html
UPDATE player_info SET ht_in_in = 75, wt = 190 WHERE player_id = 'skardro01' AND player = 'Bob Skarda'; -- https://www.basketball-reference.com/nbl/players/s/skardro01n.html
UPDATE player_info SET ht_in_in = 75, wt = 190 WHERE player_id = 'synnoro01' AND player = 'Bob Synnott'; -- https://www.basketball-reference.com/nbl/players/s/synnoro01n.html
UPDATE player_info SET ht_in_in = 77, wt = 190 WHERE player_id = 'lowthro01' AND player = 'Bobby Lowther'; -- https://www.basketball-reference.com/nbl/players/l/lowthro01n.html
UPDATE player_info SET ht_in_in = 75, wt = 205 WHERE player_id = 'gilbeme01' AND player = 'Boody Gilbertson'; -- https://www.basketball-reference.com/nbl/players/g/gilbeme01n.html
UPDATE player_info SET ht_in_in = 70, wt = 155 WHERE player_id = 'mendemu01' AND player = 'Bud Mendenhall'; -- https://www.basketball-reference.com/nbl/players/m/mendemu01n.html
UPDATE player_info SET ht_in_in = 71, wt = 170 WHERE player_id = 'loydca01' AND player = 'Carl Loyd'; -- https://www.basketball-reference.com/nbl/players/l/loydca01n.html
UPDATE player_info SET ht_in_in = 77, wt = 215 WHERE player_id = 'smickda01' AND player = 'Danny Smick'; -- https://www.basketball-reference.com/nbl/players/s/smickda01n.html
UPDATE player_info SET ht_in_in = 73, wt = 185 WHERE player_id = 'warehda01' AND player = 'Dave Wareham'; -- https://www.basketball-reference.com/nbl/players/w/warehda01n.html
UPDATE player_info SET ht_in_in = 72, wt = 175 WHERE player_id = 'stantjo01' AND player = 'Deacon Stanky'; -- https://www.basketball-reference.com/nbl/players/s/stantjo01n.html
UPDATE player_info SET ht_in_in = 70, wt = 180 WHERE player_id = 'starzri01' AND player = 'Dick Starzyk'; -- https://www.basketball-reference.com/nbl/players/s/starzri01n.html
UPDATE player_info SET ht_in_in = 76, wt = 220 WHERE player_id = 'bogdaed01' AND player = 'Ed Bogdanski'; -- https://www.basketball-reference.com/nbl/players/b/bogdaed01n.html
UPDATE player_info SET ht_in_in = 72, wt = 170 WHERE player_id = 'costaed01' AND player = 'Ed Costain'; -- https://www.basketball-reference.com/nbl/players/c/costaed01n.html
UPDATE player_info SET ht_in_in = 80, wt = 225 WHERE player_id = 'millsed01' AND player = 'Ed Mills'; -- https://www.basketball-reference.com/nbl/players/m/millsed01n.html
UPDATE player_info SET ht_in_in = 72, wt = 175 WHERE player_id = 'moelled01' AND player = 'Ed Moeller'; -- https://www.basketball-reference.com/nbl/players/m/moelled01n.html
UPDATE player_info SET ht_in_in = 76, wt = 220 WHERE player_id = 'erbaned01' AND player = 'Eddie Erban'; -- https://www.basketball-reference.com/nbl/players/e/erbaned01n.html
UPDATE player_info SET ht_in_in = 75, wt = 175 WHERE player_id = 'oramed01' AND player = 'Eddie Oram'; -- https://www.basketball-reference.com/nbl/players/o/oramed01n.html
UPDATE player_info SET ht_in_in = 71, wt = 170 WHERE player_id = 'sotnyem01' AND player = 'Emil Sotnyk'; -- https://www.basketball-reference.com/nbl/players/s/sotnyem01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'carswfr01' AND player = 'Frank Carswell'; -- https://www.basketball-reference.com/nbl/players/c/carswfr01n.html
UPDATE player_info SET ht_in_in = 71, wt = 180 WHERE player_id = 'gilhofr01' AND player = 'Frankie Gilhooley'; -- https://www.basketball-reference.com/nbl/players/g/gilhofr01n.html
UPDATE player_info SET ht_in_in = 71, wt = 175 WHERE player_id = 'campbfr01' AND player = 'Fred Campbell'; -- https://www.basketball-reference.com/nbl/players/c/campbfr01n.html
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'rehmfr01' AND player = 'Fred Rehm'; -- https://www.basketball-reference.com/nbl/players/r/rehmfr01n.html
UPDATE player_info SET ht_in_in = 75, wt = 170 WHERE player_id = 'ganttfr01' AND player = 'Freddie Gantt'; -- https://www.basketball-reference.com/nbl/players/g/ganttfr01n.html
UPDATE player_info SET ht_in_in = 69, wt = 160 WHERE player_id = 'lalleeu01' AND player = 'Gene Lalley'; -- https://www.basketball-reference.com/nbl/players/l/lalleeu01n.html
UPDATE player_info SET ht_in_in = 74, wt = 206 WHERE player_id = 'crowege01' AND player = 'George Crowe'; -- https://www.basketball-reference.com/nbl/players/c/crowege01n.html
UPDATE player_info SET ht_in_in = 75, wt = 200 WHERE player_id = 'flickgo01' AND player = 'Gordon Flick'; -- https://www.basketball-reference.com/nbl/players/f/flickgo01n.html
UPDATE player_info SET ht_in_in = 75, wt = 190 WHERE player_id = 'mitchgu01' AND player = 'Guy Mitchell'; -- https://www.basketball-reference.com/nbl/players/m/mitchgu01n.html
UPDATE player_info SET ht_in_in = 78, wt = 210 WHERE player_id = 'devolha01' AND player = 'Hal Devoll'; -- https://www.basketball-reference.com/nbl/players/d/devolha01n.html
UPDATE player_info SET ht_in_in = 71, wt = 170 WHERE player_id = 'gensiha01' AND player = 'Hal Gensichen'; -- https://www.basketball-reference.com/nbl/players/g/gensiha01n.html
UPDATE player_info SET ht_in_in = 77, wt = 205 WHERE player_id = 'korovha01' AND player = 'Hal Korovin'; -- https://www.basketball-reference.com/nbl/players/k/korovha01n.html
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'okeefhe01' AND player = 'Hank O''Keeffe'; -- https://www.basketball-reference.com/nbl/players/o/okeefhe01n.html
UPDATE player_info SET ht_in_in = 77, wt = 190 WHERE player_id = 'hutchha01' AND player = 'Herb Hutchisson'; -- https://www.basketball-reference.com/nbl/players/h/hutchha01n.html
UPDATE player_info SET ht_in_in = 76, wt = 200 WHERE player_id = 'brennir01' AND player = 'Irv Brenner'; -- https://www.basketball-reference.com/nbl/players/b/brennir01n.html
UPDATE player_info SET ht_in_in = 72, wt = 180 WHERE player_id = 'norenir01' AND player = 'Irv Noren'; -- https://www.basketball-reference.com/nbl/players/n/norenir01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'foresja01' AND player = 'Jack Forestieri'; -- https://www.basketball-reference.com/nbl/players/f/foresja01n.html
UPDATE player_info SET ht_in_in = 75, wt = 160 WHERE player_id = 'spencja01' AND player = 'Jack Spencer'; -- https://www.basketball-reference.com/nbl/players/s/spencja01n.html
UPDATE player_info SET ht_in_in = 74, wt = 190 WHERE player_id = 'waltoja01' AND player = 'Jack Walton'; -- https://www.basketball-reference.com/nbl/players/w/waltoja01n.html
UPDATE player_info SET ht_in_in = 67, wt = 150 WHERE player_id = 'goldsjo01' AND player = 'Jackie Goldsmith'; -- https://www.basketball-reference.com/nbl/players/g/goldsjo01n.html
UPDATE player_info SET ht_in_in = 67, wt = 160 WHERE player_id = 'steinje01' AND player = 'Jerry Steiner'; -- https://www.basketball-reference.com/nbl/players/s/steinje01n.html
UPDATE player_info SET ht_in_in = 77, wt = 195 WHERE player_id = 'gibbsji01' AND player = 'Jim Gibbs'; -- https://www.basketball-reference.com/nbl/players/g/gibbsji01n.html
UPDATE player_info SET ht_in_in = 77, wt = 220 WHERE player_id = 'homerja01' AND player = 'Jim Homer'; -- https://www.basketball-reference.com/nbl/players/h/homerja01n.html
UPDATE player_info SET ht_in_in = 76, wt = 225 WHERE player_id = 'usryja01' AND player = 'Jim Usry'; -- https://www.basketball-reference.com/nbl/players/u/usryja01n.html
UPDATE player_info SET ht_in_in = 79, wt = 190 WHERE player_id = 'zeravja01' AND player = 'Jim Zeravich'; -- https://www.basketball-reference.com/nbl/players/z/zeravja01n.html
UPDATE player_info SET ht_in_in = 77, wt = 195 WHERE player_id = 'joyceji01' AND player = 'Jimmy Joyce'; -- https://www.basketball-reference.com/nbl/players/j/joyceji01n.html
UPDATE player_info SET ht_in_in = 76, wt = 195 WHERE player_id = 'camicjo01' AND player = 'Joe Camic'; -- https://www.basketball-reference.com/nbl/players/c/camicjo01n.html
UPDATE player_info SET ht_in_in = 73, wt = 175 WHERE player_id = 'lordjo01' AND player = 'Joe Lord'; -- https://www.basketball-reference.com/nbl/players/l/lordjo01n.html
UPDATE player_info SET ht_in_in = 75, wt = 185 WHERE player_id = 'bosakjo01' AND player = 'John Bosak'; -- https://www.basketball-reference.com/nbl/players/b/bosakjo01n.html
UPDATE player_info SET ht_in_in = 78, wt = 190 WHERE player_id = 'gibbsjo01' AND player = 'John Gibbs'; -- https://www.basketball-reference.com/nbl/players/g/gibbsjo01n.html
UPDATE player_info SET ht_in_in = 71, wt = 180 WHERE player_id = 'moisejo01' AND player = 'John Moiseichik'; -- https://www.basketball-reference.com/nbl/players/m/moisejo01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'sebasjo01' AND player = 'Johnny Sebastian'; -- https://www.basketball-reference.com/nbl/players/s/sebasjo01n.html
UPDATE player_info SET ht_in_in = 72, wt = 215 WHERE player_id = 'wnoroca01' AND player = 'Kayo Wnorowski'; -- https://www.basketball-reference.com/nbl/players/w/wnoroca01n.html
UPDATE player_info SET ht_in_in = 75, wt = 190 WHERE player_id = 'careyke01' AND player = 'Keith Carey'; -- https://www.basketball-reference.com/nbl/players/c/careyke01n.html
UPDATE player_info SET ht_in_in = 74, wt = 180 WHERE player_id = 'buehlke01' AND player = 'Ken Buehler'; -- https://www.basketball-reference.com/nbl/players/b/buehlke01n.html
UPDATE player_info SET ht_in_in = 72, wt = 160 WHERE player_id = 'walteke01' AND player = 'Ken Walters'; -- https://www.basketball-reference.com/nbl/players/w/walteke01n.html
UPDATE player_info SET ht_in_in = 76, wt = 198 WHERE player_id = 'campbal01' AND player = 'Kenton Campbell'; -- https://www.basketball-reference.com/nbl/players/c/campbal01n.html
UPDATE player_info SET ht_in_in = 79, wt = 200 WHERE player_id = 'kingle01' AND player = 'LeRoy King'; -- https://www.basketball-reference.com/nbl/players/k/kingle01n.html
UPDATE player_info SET ht_in_in = 75, wt = 185 WHERE player_id = 'alterle01' AND player = 'Len Alterman'; -- https://www.basketball-reference.com/nbl/players/a/alterle01n.html
UPDATE player_info SET ht_in_in = 76, wt = 230 WHERE player_id = 'fordle01' AND player = 'Len Ford'; -- https://www.basketball-reference.com/nbl/players/f/fordle01n.html
UPDATE player_info SET ht_in_in = 75, wt = 180 WHERE player_id = 'pryorle01' AND player = 'Leroy Pryor'; -- https://www.basketball-reference.com/nbl/players/p/pryorle01n.html
UPDATE player_info SET ht_in_in = 76, wt = 210 WHERE player_id = 'deatole01' AND player = 'Les Deaton'; -- https://www.basketball-reference.com/nbl/players/d/deatole01n.html
UPDATE player_info SET ht_in_in = 75, wt = 180 WHERE player_id = 'possnlo01' AND player = 'Lou Possner'; -- https://www.basketball-reference.com/nbl/players/p/possnlo01n.html
UPDATE player_info SET ht_in_in = 72, wt = 180 WHERE player_id = 'neatly01' AND player = 'Lyle Neat'; -- https://www.basketball-reference.com/nbl/players/n/neatly01n.html
UPDATE player_info SET ht_in_in = 77, wt = 200 WHERE player_id = 'udallmo01' AND player = 'Mo Udall'; -- https://www.basketball-reference.com/nbl/players/u/udallmo01n.html
UPDATE player_info SET ht_in_in = 73, wt = 175 WHERE player_id = 'hillmo01' AND player = 'Mort Hill'; -- https://www.basketball-reference.com/nbl/players/h/hillmo01n.html
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'richioc01' AND player = 'Ocie Richie'; -- https://www.basketball-reference.com/nbl/players/r/richioc01n.html
UPDATE player_info SET ht_in_in = 70, wt = 165 WHERE player_id = 'shoafol01' AND player = 'Ollie Shoaff'; -- https://www.basketball-reference.com/nbl/players/s/shoafol01n.html
UPDATE player_info SET ht_in_in = 77, wt = 195 WHERE player_id = 'anthopa01' AND player = 'Paul Anthony'; -- https://www.basketball-reference.com/nbl/players/a/anthopa01n.html
UPDATE player_info SET ht_in_in = 74, wt = 190 WHERE player_id = 'yesawpa01' AND player = 'Paul Yesawich'; -- https://www.basketball-reference.com/nbl/players/y/yesawpa01n.html
UPDATE player_info SET ht_in_in = 76, wt = 190 WHERE player_id = 'bishora01' AND player = 'Ralph Bishop'; -- https://www.basketball-reference.com/nbl/players/b/bishora01n.html
UPDATE player_info SET ht_in_in = 74, wt = 195 WHERE player_id = 'pattera01' AND player = 'Ray Patterson'; -- https://www.basketball-reference.com/nbl/players/p/pattera01n.html
UPDATE player_info SET ht_in_in = 76, wt = 190 WHERE player_id = 'brownwi01' AND player = 'Rookie Brown'; -- https://www.basketball-reference.com/nbl/players/b/brownwi01n.html
UPDATE player_info SET ht_in_in = 80, wt = 240 WHERE player_id = 'liebesa01' AND player = 'Sam Lieberman'; -- https://www.basketball-reference.com/nbl/players/l/liebesa01n.html
UPDATE player_info SET ht_in_in = 76, wt = 225 WHERE player_id = 'hawkiea01' AND player = 'Shag Hawkins'; -- https://www.basketball-reference.com/nbl/players/h/hawkiea01n.html
UPDATE player_info SET ht_in_in = 71, wt = 195 WHERE player_id = 'woodro01' AND player = 'Sonny Wood'; -- https://www.basketball-reference.com/nbl/players/w/woodro01n.html
UPDATE player_info SET ht_in_in = 72, wt = 160 WHERE player_id = 'cookth01' AND player = 'Ted Cook'; -- https://www.basketball-reference.com/nbl/players/c/cookth01n.html
UPDATE player_info SET ht_in_in = 80, wt = 220 WHERE player_id = 'kasetan01' AND player = 'Tony Kaseta'; -- https://www.basketball-reference.com/nbl/players/k/kasetan01n.html
UPDATE player_info SET ht_in_in = 75, wt = 195 WHERE player_id = 'kraffvi01' AND player = 'Vic Krafft'; -- https://www.basketball-reference.com/nbl/players/k/kraffvi01n.html
UPDATE player_info SET ht_in_in = 70, wt = 160 WHERE player_id = 'siegevi01' AND player = 'Vic Siegel'; -- https://www.basketball-reference.com/nbl/players/s/siegevi01n.html
UPDATE player_info SET ht_in_in = 79, wt = 205 WHERE player_id = 'borrewa01' AND player = 'Wally Borrevik'; -- https://www.basketball-reference.com/nbl/players/b/borrewa01n.html
UPDATE player_info SET ht_in_in = 73, wt = 185 WHERE player_id = 'mulvibo01' AND player = 'Ward Myers'; -- https://www.basketball-reference.com/nbl/players/m/mulvibo01n.html
UPDATE player_info SET ht_in_in = 74, wt = 170 WHERE player_id = 'ajaxwa01' AND player = 'Warren Ajax'; -- https://www.basketball-reference.com/nbl/players/a/ajaxwa01n.html
UPDATE player_info SET ht_in_in = 72, wt = 185 WHERE player_id = 'dienejo01' AND player = 'Whitey Dienelt'; -- https://www.basketball-reference.com/nbl/players/d/dienejo01n.html
COMMIT;
