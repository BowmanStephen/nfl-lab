"""Per-game facts behind a weekly plain-English recap.

Usage: python pipeline/recap/week_facts.py PBP_PARQUET SEASON WEEK OUT_JSON

Reads nflverse play-by-play (play_by_play_{season}.parquet from the
nflverse-data `pbp` release) and writes every number the recap cites.
QB points = sum of qb_epa over the QB's dropbacks (dropbacks x EPA per dropback).
Turnovers = interceptions thrown plus fumbles the team lost (fumbled_1_team).
Success rate and EPA per play use run and pass plays, no kneels or spikes.
Explosive = pass of 20+ yards or run of 10+ yards.
Red-zone trip = a drive with a run, pass or field-goal snap at the opponent 20 or closer.
Special teams = EPA on kickoffs, punts, field goals and extra points, net of the opponent.
"""
from __future__ import annotations

import json
import sys

import pandas as pd


def team_facts(g: pd.DataFrame, t: str) -> dict:
    o = g[g.posteam == t]
    plays = o[o.play_type.isin(["pass", "run"]) & (o.qb_kneel != 1) & (o.qb_spike != 1)]
    early = plays[plays.down.isin([1, 2])]
    third = plays[plays.down == 3]
    fourth = plays[plays.down == 4]
    rush = plays[plays.rush == 1]
    db = o[o.qb_dropback == 1]
    qbs = db.groupby("name").agg(dropbacks=("qb_epa", "size"), qb_points=("qb_epa", "sum"),
                                 play_epa=("epa", "sum"))
    ints = o[o.interception == 1]
    fum = g[(g.fumble_lost == 1) & (g.fumbled_1_team == t) & (g.fumble_recovery_1_team != t)]
    to = pd.concat([ints, fum])
    rz = g[(g.posteam == t) & g.play_type.isin(["pass", "run", "field_goal"])
           & (g.two_point_attempt != 1) & (g.yardline_100 <= 20)]
    rz_res = rz.groupby("drive").fixed_drive_result.first()
    st = g[g.play_type.isin(["punt", "kickoff", "field_goal", "extra_point"])]
    fg = g[(g.posteam == t) & (g.play_type == "field_goal")]
    conv = lambda d: int(((d.first_down == 1) | (d.touchdown == 1)).sum())
    return {
        "plays": int(len(plays)),
        "epa_per_play": round(float(plays.epa.mean()), 3),
        "success_rate": round(float(plays.success.mean()), 3),
        "early_down_success": round(float(early.success.mean()), 3),
        "pass_play_epa": round(float(plays[plays["pass"] == 1].epa.sum()), 1),
        "rush_epa": round(float(rush.epa.sum()), 1),
        "rushes": int(len(rush)),
        "rush_yards": int(rush.yards_gained.sum()),
        "third_down": f"{conv(third)}/{len(third)}",
        "fourth_down": f"{conv(fourth)}/{len(fourth)}",
        "explosive": int(((plays["pass"] == 1) & (plays.yards_gained >= 20)).sum()
                         + ((plays.rush == 1) & (plays.yards_gained >= 10)).sum()),
        "sacks_taken": int(o.sack.fillna(0).sum()),
        "turnovers": int(len(to)),
        "turnover_epa": round(float(to.epa.sum()), 1),
        "red_zone_trips": int(len(rz_res)),
        "red_zone_tds": int((rz_res == "Touchdown").sum()),
        "special_teams_net_epa": round(float(st[st.posteam == t].epa.sum() - st[st.defteam == t].epa.sum()), 1),
        "field_goals": [f"{int(r.kick_distance)} {r.field_goal_result}" for _, r in fg.iterrows()],
        "qbs": {n: {"dropbacks": int(r.dropbacks), "qb_points": round(float(r.qb_points), 1),
                    "play_epa": round(float(r.play_epa), 1)}
                for n, r in qbs.iterrows() if r.dropbacks >= 3},
    }


def main(path: str, season: int, week: int, out: str) -> None:
    p = pd.read_parquet(path)
    p = p[(p.season == season) & (p.week == week) & (p.season_type == "REG")]
    games = {}
    for gid, g in p.groupby("game_id"):
        last = g.iloc[-1]
        a, h = last.away_team, last.home_team
        games[gid] = {
            "away": a, "home": h,
            "away_score": int(last.total_away_score), "home_score": int(last.total_home_score),
            "overtime": bool((g.qtr == 5).any()),
            a: team_facts(g, a), h: team_facts(g, h),
        }
    # Week-wide checks the opening lines rely on
    decided = [v for v in games.values() if v["away_score"] != v["home_score"]]
    def wl(v):
        return (v["away"], v["home"]) if v["away_score"] > v["home_score"] else (v["home"], v["away"])
    better_epa = sum(v[wl(v)[0]]["epa_per_play"] > v[wl(v)[1]]["epa_per_play"] for v in decided)
    better_sr = sum(v[wl(v)[0]]["success_rate"] > v[wl(v)[1]]["success_rate"] for v in decided)
    fewer_to = sum(v[wl(v)[0]]["turnovers"] < v[wl(v)[1]]["turnovers"] for v in decided)
    more_to = sum(v[wl(v)[0]]["turnovers"] > v[wl(v)[1]]["turnovers"] for v in decided)
    qb_rows = [(n, t, q["qb_points"], q["dropbacks"]) for v in games.values()
               for t in (v["away"], v["home"]) for n, q in v[t]["qbs"].items()]
    summary = {
        "games": len(games), "decided": len(decided),
        "winner_better_epa_per_play": better_epa, "winner_better_success_rate": better_sr,
        "winner_fewer_turnovers": fewer_to, "winner_more_turnovers": more_to,
        "best_qb": max(qb_rows, key=lambda r: r[2]), "worst_qb": min(qb_rows, key=lambda r: r[2]),
        "worst_epa_per_play": min(((t, v[t]["epa_per_play"]) for v in games.values()
                                   for t in (v["away"], v["home"])), key=lambda r: r[1]),
        "worst_success_rate": min(((t, v[t]["success_rate"]) for v in games.values()
                                   for t in (v["away"], v["home"])), key=lambda r: r[1]),
    }
    with open(out, "w") as f:
        json.dump({"season": season, "week": week, "source": "nflverse play_by_play",
                   "summary": summary, "games": games}, f, indent=1)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4])
