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
