# NFL Lab autoresearch: instructions for the loop agent

You are improving the NFL Lab game model overnight, one small experiment at a time,
in the style of karpathy/autoresearch. Stephen may be asleep. Do not stop to ask
questions; follow these rules and stop when the budget runs out.

## Setup (once per night)

1. Pick a run tag from tonight's date, e.g. `oct07`. From the repo root:
   `git fetch origin && git checkout -b autoresearch/<tag> origin/main`
   The branch must not already exist.
2. `uv sync` then `uv run python research/evaluate.py --prepare` (builds
   `research/.cache/` from nflverse, 2010-2021 only; skips if it already exists).
3. Read `research/README.md`, `research/evaluate.py` (do not edit) and
   `research/candidate.py` (the file you edit). Skim `research/results.tsv`:
   the last `keep` row is the score to beat, and earlier rows show what was tried.
4. If `research/results.tsv` has no `keep` row, the first step is the baseline:
   `uv run python research/step.py "baseline"` with no edits.

Budget: stop after **N = 20 experiments or T = 120 minutes**, whichever comes first,
unless the person who started you gave other numbers. Count only your own rows
(the `time_ct` column shows when each ran).

## What you CAN do

- Edit `research/candidate.py`. It is the only file you may change. Everything in it is
  fair game: features, shrinkage and priors, week buckets, how and when coefficients
  are fit, regularization, the QB term, totals features, hyperparameters.
- Use only numpy, pandas and scipy (already installed). No new dependencies.

## What you CANNOT do

- Edit any other file: `research/evaluate.py`, `research/step.py`, `research/gate.py`,
  `research/reference_main.py`, this file, or anything under `src/`, `pipeline/`,
  `output/`, `public/`, `picks/`. `step.py` refuses to run if the harness changed.
- **Run `research/gate.py`, or call its code, ever.** The 2020-2021 GATE check runs once
  per night after you finish, by whoever started you. Do not score 2020-2021 any other
  way either, and do not read `research/gate_log.tsv` for hints.
- Look at any season after 2021, in the candidate or in your own scratch analysis.
  Do not open `data/`, `output/`, `public/` or nflverse data for 2022 or later.
- Make the candidate read files, use the network, start processes, inspect the
  evaluator's memory, or use betting lines. The harness blocks most of this and the
  scramble test catches peeking; a `leak` row is a serious failure, not a near miss.
- Hard-code answers for particular games, teams or seasons.

## The loop

Repeat until the budget is spent:

1. Pick one idea. Small and explainable beats clever.
2. Edit `research/candidate.py`.
3. `git commit -q -m "exp: <idea>" -- research/candidate.py`
4. `uv run python research/step.py "<one-line description of the idea>"`
   (add `--simplification` only when the change removes code or settings).
   It runs `research/evaluate.py` (TUNE = 2016-2019, about 30 s, hard timeout 10 min),
   writes the full output to `research/run.log`, and then, by rule:
   - **keep** if `tune_score` beats the last kept score by more than 0.001 points
     (with `--simplification`: if it is no worse than last kept + 0.001);
   - **discard** otherwise, **crash** if the run errors or times out, **leak** if the
     scramble test fails. Anything but keep is undone with `git reset --hard HEAD~1`.
   - It appends a row to `research/results.tsv` (commit, time, TUNE score, margin and
     total MAE, info-only hit rates, status, seconds, your description) and commits it.
5. If it crashed, read `research/run.log`. If it was a typo, fix it and run again as a
   new experiment. If the idea is broken, move on.

`tune_score = mean |pred_margin - margin| + mean |pred_total - total|` over every
regular-season game 2016-2019, in points. Lower is better. The market's score on the
same games is the `market` row: a yardstick, not a target. The ATS and totals hit rates
are information only. Never chase them.

## Judgment

- Simplicity wins ties. A 0.002 gain that adds 30 lines of special cases is not worth
  keeping; a change that deletes code and scores the same is. Prefer ideas with a
  football reason behind them.
- 1,024 games is a small sample and you will see the score many times. Tiny gains from
  fiddling constants are mostly noise that the GATE check will expose. Move constants in
  coarse steps and prefer structural ideas.
- Keep every answer causal: anything cached at module level must depend only on data
  from before the week it is used for.

## When you stop

1. `git push -u origin autoresearch/<tag>`.
2. Report, in a few lines: how many experiments, what was kept, the TUNE score before
   and after, and anything that crashed or leaked. Then stop. Do not run the gate, do
   not open a PR into the live model, do not touch picks or the site.
