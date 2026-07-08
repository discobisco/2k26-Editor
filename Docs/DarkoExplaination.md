What Is DARKO?
DARKO is a machine learning-driven basketball player box-score projection system.

For an audio primer check out Kostya on Seth Partnow's show here.

The public basketball stats space has advanced wonderfully over the last decade, most prominently with the explosion of "all-in-one" metrics like RAPM, RPM, LEBRON, and BPM, among others. Excellent research has also been done on a number of other topics, such as positional versatility, clutch performance, shooting luck, and matchups.

However, despite these advances, there has been a relative dearth of focus on forward-looking projections as opposed to backwards-looking explanations, and even less public work on basic box-score metrics (as opposed to "all-in-one" metrics). Krishna Narsu has done excellent work on the "stability" of various stats, and I have contributed myself, but this work has been on a team level. FiveThirtyEight, meanwhile, has been releasing their CARMELO/RAPTOR player projections, but these are likewise rolled-up, "all-in-one"-style projections that tell us relatively little about where a player's growth/decline is going to come from.

DARKO (Daily Adjusted and Regressed Kalman Optimized projections) is an attempt to fill that gap. As will be familiar to baseball fans, DARKO is a basketball projection system similar in concept to Steamer, PECOTA, and ZiPS. To my knowledge, it is one of the few public computer-driven NBA box-score projection systems.

Further, unlike the baseball projection systems listed above (or the CARMELO/RAPTOR projections), DARKO is built from the ground up to update its projections daily, responding to new information as it comes. Instead of just making a projection before the season and leaving users to guess whether a given breakout is "real" or not, DARKO updates its projections for every player in the NBA, for every box-score stat, for every day of the season.

Model Summary
DARKO is built using a combination of classical statistical techniques and modern machine learning methods. DARKO is Bayesian in nature, updating its projections in response to new information, with the amount of the update varying by player and by stat, depending on DARKO's confidence in its prior estimate.

The inputs for DARKO are NBA box scores, tracking data, and other game-level information from Basketball-Reference.com, NBA.com, and aided by Darryl Blackport's work in creating pbpstats.com. DARKO is trained on every player game log since the 2001 season (about 736,000 so far).

DARKO grapples with the core problem facing every fantasy player (and fan): understanding how much of a given player's development or decline in-season reflects real talent changes, and how much is just the random noise that is part of an NBA season. DARKO addresses these issues without any arbitrary endpoints, i.e., without looking at the last X games of a player's career.

DARKO does this by modeling player performance via an exponential decay model, weighing each game a player has ever played by βt, where β is some number between 0 and 1, and 't' is the number of days ago a given game took place. The value of β differs for each stat, selected to best predict future results. A differential evolution optimizer is used to calculate each β.

DARKO also combines this exponential decay approach with a modified Kalman filter. Kalman filters are a standard approach used in time-series analysis to model the location of an object for which only noisy measurements are available. Commonly used in fields such as robotics, aviation, rocketry, and neuroscience, it is well suited for sports analysis as well.

A gradient boosted decision tree is used to combine the decay and Kalman projections.

DARKO also accounts for several sports statistics phenomena. These include:

Rest/Travel/Home Court Effects: As is widely known, players perform worse on the road or on the second night of a back-to-back. DARKO accounts for these effects on a component-by-component level, and the adjustments themselves update daily in response to new information (e.g., home court advantage has been decreasing in the NBA for some time).
Opponent Adjustments: DARKO's projections account for who each team is playing on a given night, accounting for the projected influence of a player's opponents on each individual stat.
Aging: DARKO includes an aging curve. Because players improve differently with age in different stats, DARKO uses an independent aging curve for every stat it projects. DARKO also attempts to account for the selection biases which make aging studies very difficult to carry out in sports data.
Seasonality: Throughout the NBA, offensive efficiency to start the season is usually relatively low league-wide and increases throughout the year. DARKO accounts for a temporary flattening of the rise in assist rates (and other offensive metrics) around the all-star break. All seasonality effects are calculated separately for each component.
Interaction Effects: DARKO accounts for interactions between various box-score components in making its projections. For example, if a player improves both his three-point shooting and his free throw shooting simultaneously, DARKO will be inherently more credulous of such an improvement.
Free Agency: Changing teams has a big impact on some box-score components, and DARKO accounts for that. DARKO also gets less confident in its understanding of a player's talent when they change teams, effectively increasing its "learning rate" for these players.
Accuracy
While DARKO is not intended to be a DFS tool, given the dearth of other projection systems out there for the NBA, a natural place to test DARKO was to compare how DARKO performs against DFS projections. With one exception, DARKO beat both sites in every stat tested (minutes, points, rebounds, assists, blocks, turnovers, and threes made), some by substantial margins.

The only stat where DARKO lost was in minutes projections. Predictably, playing-time projections are the hardest part of any projection system, and DARKO is no different in this respect.

Daily Plus Minus (DPM)
While DARKO is at its core a box-score projection system, it can also be used to generate plus-minus projections, similar in nature to RPM, PIPM, etc. I have called this metric DPM, for "Daily Plus Minus." This metric provides an estimate of how much DARKO thinks each player impacts the score of a game.

Daily Plus Minus is available in two flavors. A box-score-only version (Box DPM), which combines the core box-score metrics to predict player value, and another set (DPM) which adds in on-off data to do the same. Both DPM and Box DPM remain works in progress and may change substantially going forward.

Rookies
DARKO presently has no NCAA, summer league, or preseason data in it. That means rookies are all initialized to essentially the same starting point (with some differences for age), and then DARKO "learns" about them as they play.

Further Improvements
DARKO is currently calibrated to generate projections for each player for the next day of the season. The framework is extendable to other types of projections as well, such as season-long projections or upside/peak projections, along with adding more tracking data, biometric data, and G-League data into the model.