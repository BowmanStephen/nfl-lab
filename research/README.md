# Overnight model research

This folder lets an agent try to improve the NFL Lab model while Stephen sleeps, copying the
pattern of Andrej Karpathy's autoresearch. The agent may change exactly one file,
`candidate.py`, which predicts each game's home margin and total points from what was known
before kickoff. After every change a fixed scorer, `evaluate.py`, replays the 2016–2019
seasons week by week, handing the model only earlier plays and scores, never betting lines and
never the week's results. The score is the average miss on margins plus the average miss on
totals, in points. If the change lowers that score it is kept; otherwise it is undone. Each
try is one row in `results.tsv`, and one replay takes about 30 seconds.

The seasons are split on purpose. 2016–2019 is the practice set the agent sees all night.
2020–2021 is a check it never sees: once per night, after the agent stops, `gate.py` replays
those two seasons for the night's best version and for the last version that passed (or the
current live model's design, the first time), and writes a single pass or fail line to
`gate_log.tsv`. Only a version with a pass may be proposed for the live model, and that
decision is still Stephen's. Every game from 2022 on is out of reach: the scorer refuses
those seasons and never downloads them, and the model is blocked from reading files or the
internet. A scramble test re-asks old weeks after shuffling every later result; a model that
peeks changes its answers and is thrown out.

The starting model is the draft from PR #7, rebuilt inside `candidate.py` without touching
the live code. Margins come from a points-for-and-against rating with a separate scale for
weeks 1–4, 5–8 and 9 on, plus home field and the starting quarterback; totals use the EPA
scoring environment with the defense sign fixed, plus points scored and allowed. Its
practice score is 20.95, against 21.29 for the live model's design and 20.45 for the closing
lines. Nothing here changes the picks, the site, or the live pipeline.

A nightly run is: start an agent in the repo with the instruction "Follow
research/program.md with N=20 and T=120", then, when it finishes, run
`uv run python research/gate.py` once on its branch. The agent's rules, including the
ban on running the gate, are in `program.md`.
