# Week 4 preview input

`team_stats_2026_week4.json` is an unchanged copy of
`pipeline/output/team_stats.json` from commit
`6ceff90e2b97be566fcec9df10752ae196266e2e`, "Week 5 previews: review fixes for
disclaimer, provenance, and aggregates. (#14)".

- Source Git blob: `da5cc977297eedbaa987d65ca96d9c92fa0719ca`
- SHA-256: `92a786dff1a64170d55a811057176c7788b1730cb00ff300c358a719420518b8`
- That commit's `pipeline/output/summary.json` records `current_season: 2026`,
  `through_week: 4`, `preview_week: 5`, and
  `generated_at: 2026-10-05T00:31:09.327767-05:00`.
- Every team row records `season: 2026` and `through_week: 4`.

Recover the exact fixture from the repository history with:

```bash
git show 6ceff90e2b97be566fcec9df10752ae196266e2e:pipeline/output/team_stats.json > tests/fixtures/team_stats_2026_week4.json
```

The week-5 preview remains tied to those four weeks of games.
`pipeline/src/run.py` selects the latest available PBP week and writes the
current `pipeline/output/team_stats.json`, so that path cannot serve as a
historical test input. Keep this fixture unchanged when current stats refresh.
