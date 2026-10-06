# Overnight model research

This folder lets an agent try to improve the NFL Lab model while Stephen sleeps, copying the
pattern of Andrej Karpathy's autoresearch. The agent may change exactly one file,
`candidate.py`, which predicts each game's home margin and total points from what was known
before kickoff. After every change a fixed scorer, `evaluate.py`, replays the 2016–2019
seasons week by week, handing the model only earlier plays and scores, never betting lines and
never the week's results. The score is the average miss on margins plus the average miss on
totals, in points. A change is kept only if it beats the best score so far by more than 0.001
points (or, for a change that only deletes code, if it is no worse than the best by more than
0.001); otherwise it is undone. Each try is one row in `results.tsv`, its code change is saved in
`experiments/`, and one replay takes about a minute on the box.

The seasons are split on purpose. 2016–2019 is the practice set the agent sees all night.
2020–2021 is a check it never sees: once per night, after the agent stops, `gate.py` replays
those two seasons for the night's best version and for the last version that passed (or the
current live model's design, the first time), and writes a single pass or fail line to
`gate_log.tsv`. Only a version with a pass may be proposed for the live model, and that
decision is still Stephen's. Every game from 2022 on is out of reach: the scorer refuses
those seasons and never downloads them. The model runs in its own separate process that is
only ever handed past games, one week at a time, and inside that process it is stopped from
reading the data files or using the internet. A scramble test replays the model from scratch
after shuffling every later result; a model that peeks changes its answers and is thrown out.

The starting model is the draft from PR #7, rebuilt inside `candidate.py` without touching
the live code. Margins come from a points-for-and-against rating with a separate scale for
weeks 1–4, 5–8 and 9 on, plus home field and the starting quarterback; totals use the EPA
scoring environment with the defense sign fixed, plus points scored and allowed. Its
practice score is 20.95, against 21.29 for the live model's design and 20.45 for the closing
lines. One caveat: for past games the starting quarterback is the one who actually started,
the same stand-in for the announced starter that the live QB adjustment was validated with. Nothing here changes the picks, the site, or the live pipeline.

A nightly run is: start an agent in the repo with the instruction "Follow
research/program.md with N=20 and T=120", then, when it finishes, run
`uv run python research/gate.py` once on its branch. The agent's rules, including the
ban on running the gate, are in `program.md`.
