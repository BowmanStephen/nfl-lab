"""Write markdown + JSON previews, recaps, and summary tables."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import OUTPUT_DIR, PREVIEWS_DIR, RECAPS_DIR, TEAM_NAMES


def _team(abbr: str) -> str:
    return TEAM_NAMES.get(abbr, abbr)


def _json_dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def _md_table(df: pd.DataFrame, cols: list[str], fmt: dict | None = None) -> str:
    fmt = fmt or {}
    use = [c for c in cols if c in df.columns]
    lines = ["| " + " | ".join(use) + " |", "| " + " | ".join(["---"] * len(use)) + " |"]
    for _, row in df.iterrows():
        cells = []
        for c in use:
            v = row[c]
            if c in fmt and pd.notna(v) and isinstance(v, (int, float)):
                cells.append(fmt[c].format(v))
            elif pd.isna(v):
                cells.append("")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_team_stats(stats: pd.DataFrame, qb: pd.DataFrame) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    records = stats.sort_values("net_epa", ascending=False).to_dict(orient="records")
    qb_records = qb.to_dict(orient="records")
    _json_dump(OUTPUT_DIR / "team_stats.json", {"teams": records, "qbs": qb_records})

    top = stats.sort_values("net_epa", ascending=False)
    md = [
        "# NFL Lab — Team Advanced Stats",
        "",
        f"Season through available data. Net EPA = off EPA/play − def EPA/play allowed.",
        "",
        "## Team table (sorted by net EPA)",
        "",
        _md_table(
            top,
            [
                "team", "off_epa", "def_epa", "net_epa",
                "off_pass_epa", "off_rush_epa", "off_success",
                "off_early_epa", "off_proe", "off_explosive_rate",
                "def_pass_epa", "def_rush_epa",
            ],
            {
                "off_epa": "{:.3f}", "def_epa": "{:.3f}", "net_epa": "{:.3f}",
                "off_pass_epa": "{:.3f}", "off_rush_epa": "{:.3f}",
                "off_success": "{:.3f}", "off_early_epa": "{:.3f}",
                "off_proe": "{:.2f}", "off_explosive_rate": "{:.3f}",
                "def_pass_epa": "{:.3f}", "def_rush_epa": "{:.3f}",
            },
        ),
        "",
        "## QB EPA + CPOE leaders",
        "",
        _md_table(
            qb.head(20),
            ["passer", "team", "dropbacks", "qb_epa", "cpoe", "epa_cpoe"],
            {
                "qb_epa": "{:.3f}", "cpoe": "{:.2f}", "epa_cpoe": "{:.3f}",
            },
        ),
        "",
    ]
    (OUTPUT_DIR / "team_stats.md").write_text("\n".join(md))
    return {"team_stats_json": str(OUTPUT_DIR / "team_stats.json"), "team_stats_md": str(OUTPUT_DIR / "team_stats.md")}


def write_ratings(ratings: pd.DataFrame, params: dict) -> dict:
    _json_dump(OUTPUT_DIR / "ratings.json", {
        "ratings": ratings.to_dict(orient="records"),
        "model_params": params,
    })
    md = [
        "# NFL Lab — Team Ratings",
        "",
        "Opponent-adjusted EPA with prior-season shrinkage. "
        "`rating` = shrunk_off − shrunk_def (higher is better).",
        "",
        f"Model params: `{json.dumps(params)}`",
        "",
        _md_table(
            ratings,
            [
                "team", "rating", "shrunk_off_epa", "shrunk_def_epa",
                "adj_off_epa", "adj_def_epa", "off_plays", "shrink_weight_off",
            ],
            {
                "rating": "{:.4f}", "shrunk_off_epa": "{:.4f}", "shrunk_def_epa": "{:.4f}",
                "adj_off_epa": "{:.4f}", "adj_def_epa": "{:.4f}",
                "shrink_weight_off": "{:.3f}",
            },
        ),
        "",
    ]
    (OUTPUT_DIR / "ratings.md").write_text("\n".join(md))
    return {"ratings_json": str(OUTPUT_DIR / "ratings.json"), "ratings_md": str(OUTPUT_DIR / "ratings.md")}


def write_projections(proj: pd.DataFrame, week: int) -> dict:
    proj = proj.copy()
    if "spread_line" in proj.columns:
        proj["market_spread_home"] = -proj["spread_line"]
    path_json = OUTPUT_DIR / f"projections_week{week}.json"
    path_md = OUTPUT_DIR / f"projections_week{week}.md"
    _json_dump(path_json, {"week": week, "games": proj.to_dict(orient="records")})
    md = [
        f"# NFL Lab — Week {week} Projections",
        "",
        "Spread is from the home team perspective (negative = home favored). `market_spread_home` uses the same convention (= −nflverse spread_line).",
        "",
        _md_table(
            proj,
            [
                "away_team", "home_team", "proj_spread", "proj_spread_qb", "proj_total",
                "home_win_prob", "home_win_prob_qb", "model_favorite", "market_spread_home", "total_line",
            ],
            {
                "proj_spread": "{:.1f}", "proj_total": "{:.1f}",
                "home_win_prob": "{:.3f}", "home_win_prob_qb": "{:.3f}", "proj_spread_qb": "{:.1f}",
                "market_spread_home": "{:.1f}", "total_line": "{:.1f}",
            },
        ),
        "",
    ]
    path_md.write_text("\n".join(md))
    return {"projections_json": str(path_json), "projections_md": str(path_md)}


def _game_preview_md(game: dict, home_stats: dict | None, away_stats: dict | None) -> str:
    away, home = game["away_team"], game["home_team"]
    lines = [
        f"# Preview: {_team(away)} at {_team(home)}",
        "",
        f"**Week {game.get('week')} · {game.get('gameday')} {game.get('gametime') or ''}**",
        "",
        "## Model projection",
        "",
        f"- Projected spread (home): **{game.get('proj_spread'):.1f}**",
        f"- Projected total: **{game.get('proj_total'):.1f}**",
        f"- Home win probability: **{100*game.get('home_win_prob', 0):.1f}%**",
        f"- Model favorite: **{game.get('model_favorite')}**",
        f"- Home rating: {game.get('home_rating'):.4f} · Away rating: {game.get('away_rating'):.4f}",
        "",
    ]
    if game.get("proj_margin_qb") is not None and pd.notna(game.get("proj_margin_qb")):
        lines += [
            "## Starting-QB adjustment (secondary)",
            "",
            f"- Projected starters: {away} **{game.get('away_qb_name')}**, {home} **{game.get('home_qb_name')}**",
            f"- QB value vs team's rated QB mix (EPA/dropback): {away} {game.get('away_qb_delta'):+.3f}, "
            f"{home} {game.get('home_qb_delta'):+.3f}",
            f"- QB adjustment: {game.get('qb_adj_points'):+.1f} pts to home margin → "
            f"spread **{game.get('proj_spread_qb'):.1f}**, home win prob **{100*game.get('home_win_prob_qb'):.1f}%**",
        ]
        for n in (game.get("qb_notes") or []):
            lines.append(f"- ⚠️ {n}")
        lines += ["", "_The pre-registered backtest headline grades the base model; the QB adjustment was validated on 2016–2021 only._", ""]
    if game.get("spread_line") is not None and pd.notna(game.get("spread_line")):
        lines += [
            "## Market (for reference)",
            "",
            f"- Closing/current spread (home perspective): {-game.get('spread_line'):+.1f} "
            f"({home if game.get('spread_line') > 0 else away} favored by {abs(game.get('spread_line')):.1f}) · Total: {game.get('total_line')}",
            f"- Model minus market (home margin): {game.get('proj_margin') - game.get('spread_line'):+.1f} pts base"
            + (f", {game.get('proj_margin_qb') - game.get('spread_line'):+.1f} pts QB-adjusted" if pd.notna(game.get('proj_margin_qb', float('nan'))) else ""),
            "",
        ]
    lines.append("## Team EPA snapshot")
    lines.append("")
    for label, st in [(away, away_stats), (home, home_stats)]:
        if not st:
            continue
        lines.append(f"### {_team(label)} ({label})")
        lines.append("")
        lines.append(
            f"- Off EPA/play: **{st.get('off_epa'):.3f}** "
            f"(pass {st.get('off_pass_epa'):.3f}, rush {st.get('off_rush_epa'):.3f})"
            if st.get("off_pass_epa") is not None else f"- Off EPA/play: **{st.get('off_epa'):.3f}**"
        )
        lines.append(
            f"- Def EPA/play allowed: **{st.get('def_epa'):.3f}**"
        )
        if st.get("off_success") is not None:
            lines.append(f"- Success rate (off): **{st.get('off_success'):.3f}**")
        if st.get("off_early_epa") is not None:
            lines.append(f"- Early-down EPA: **{st.get('off_early_epa'):.3f}**")
        if st.get("off_proe") is not None:
            lines.append(f"- Pass rate over expected: **{st.get('off_proe'):.2f}%**")
        if st.get("off_explosive_rate") is not None:
            lines.append(f"- Explosive play rate: **{100*st.get('off_explosive_rate'):.1f}%**")
        lines.append("")
    lines.append("_Numbers from nflverse play-by-play via NFL Lab. Not betting advice._")
    lines.append("")
    return "\n".join(lines)


def write_previews(
    projections: pd.DataFrame,
    team_stats: pd.DataFrame,
    week: int,
) -> list[str]:
    PREVIEWS_DIR.mkdir(parents=True, exist_ok=True)
    stats_idx = team_stats.set_index("team").to_dict(orient="index")
    written = []
    preview_records = []
    for game in projections.to_dict(orient="records"):
        away, home = game["away_team"], game["home_team"]
        md = _game_preview_md(
            game,
            home_stats=stats_idx.get(home),
            away_stats=stats_idx.get(away),
        )
        gweek = int(game.get("week") or week)
        fname = f"week{gweek}_{away}_at_{home}.md"
        path = PREVIEWS_DIR / fname
        path.write_text(md)
        written.append(str(path))
        preview_records.append({**game, "markdown_file": fname})
    _json_dump(OUTPUT_DIR / "previews.json", {"week": week, "games": preview_records})
    written.append(str(OUTPUT_DIR / "previews.json"))
    return written


def _game_recap_md(
    game_sched: dict,
    home_stats: dict | None,
    away_stats: dict | None,
    projection: dict | None,
    game_epa: dict | None,
) -> str:
    away, home = game_sched["away_team"], game_sched["home_team"]
    hs, as_ = game_sched.get("home_score"), game_sched.get("away_score")
    margin = (hs - as_) if hs is not None and as_ is not None else game_sched.get("result")
    lines = [
        f"# Recap: {_team(away)} at {_team(home)}",
        "",
        f"**Week {game_sched.get('week')} · {game_sched.get('gameday')} · Final {int(as_)}–{int(hs)}**"
        if hs is not None else f"**Week {game_sched.get('week')} · {game_sched.get('gameday')}**",
        "",
        f"Winner: **{_team(home) if margin and margin > 0 else _team(away)}** "
        f"(margin {margin:+.0f} home perspective)" if margin is not None else "",
        "",
    ]
    if projection:
        lines += [
            "## Model vs result",
            "",
            f"- Model projected margin (home): **{projection.get('proj_margin'):.1f}**",
            f"- Actual margin (home): **{margin:.0f}**" if margin is not None else "",
            f"- Model home win prob: **{100*projection.get('home_win_prob', 0):.1f}%**",
            f"- Model favorite: **{projection.get('model_favorite')}**",
            f"- Error (|proj − actual|): **{abs(projection.get('proj_margin', 0) - (margin or 0)):.1f}**",
            "",
        ]
    if game_epa:
        lines += [
            "## Game EPA",
            "",
            f"- {away} off EPA/play: **{game_epa.get('away_off_epa'):.3f}** "
            f"({game_epa.get('away_plays')} plays)",
            f"- {home} off EPA/play: **{game_epa.get('home_off_epa'):.3f}** "
            f"({game_epa.get('home_plays')} plays)",
            f"- {away} success rate: **{game_epa.get('away_success'):.3f}**" if game_epa.get("away_success") is not None else "",
            f"- {home} success rate: **{game_epa.get('home_success'):.3f}**" if game_epa.get("home_success") is not None else "",
            "",
        ]
    lines.append("## Season EPA context")
    lines.append("")
    for label, st in [(away, away_stats), (home, home_stats)]:
        if not st:
            continue
        lines.append(
            f"- **{label}**: off {st.get('off_epa'):.3f} / def {st.get('def_epa'):.3f} / "
            f"net {st.get('net_epa'):.3f}"
        )
    lines.append("")
    lines.append("_Numbers from nflverse play-by-play via NFL Lab._")
    lines.append("")
    return "\n".join(lines)


def compute_game_epa(pbp: pd.DataFrame, game_id: str, home: str, away: str) -> dict | None:
    from .data_loader import filter_offensive_plays
    g = pbp[pbp["game_id"] == game_id]
    if len(g) == 0:
        return None
    plays = filter_offensive_plays(g)
    if len(plays) == 0:
        return None
    away_p = plays[plays["posteam"] == away]
    home_p = plays[plays["posteam"] == home]
    return {
        "away_off_epa": float(away_p["epa"].mean()) if len(away_p) else None,
        "home_off_epa": float(home_p["epa"].mean()) if len(home_p) else None,
        "away_plays": int(len(away_p)),
        "home_plays": int(len(home_p)),
        "away_success": float(away_p["success"].mean()) if len(away_p) and "success" in away_p else None,
        "home_success": float(home_p["success"].mean()) if len(home_p) and "success" in home_p else None,
    }


def write_recaps(
    schedules_week: pd.DataFrame,
    team_stats: pd.DataFrame,
    projections_lookup: dict[str, dict],
    pbp: pd.DataFrame,
    week: int,
) -> list[str]:
    RECAPS_DIR.mkdir(parents=True, exist_ok=True)
    stats_idx = team_stats.set_index("team").to_dict(orient="index")
    written = []
    records = []
    completed = schedules_week[schedules_week["home_score"].notna()]
    for game in completed.to_dict(orient="records"):
        gid = game["game_id"]
        away, home = game["away_team"], game["home_team"]
        proj = projections_lookup.get(gid)
        game_epa = compute_game_epa(pbp, gid, home, away)
        md = _game_recap_md(
            game,
            home_stats=stats_idx.get(home),
            away_stats=stats_idx.get(away),
            projection=proj,
            game_epa=game_epa,
        )
        fname = f"week{week}_{away}_at_{home}.md"
        path = RECAPS_DIR / fname
        path.write_text(md)
        written.append(str(path))
        records.append({
            **{k: game.get(k) for k in [
                "game_id", "week", "gameday", "away_team", "home_team",
                "home_score", "away_score", "result", "spread_line", "total_line",
            ]},
            "projection": proj,
            "game_epa": game_epa,
            "markdown_file": fname,
        })
    _json_dump(OUTPUT_DIR / "recaps.json", {"week": week, "games": records})
    written.append(str(OUTPUT_DIR / "recaps.json"))
    return written


def _rec_line(r: dict) -> str:
    if not r.get("wins") and not r.get("losses"):
        return "no bets"
    ci = r.get("win_rate_ci95") or [float("nan")] * 2
    return (f"{r['wins']}-{r['losses']}-{r['pushes']} · {100*r['win_rate']:.1f}% "
            f"(95% CI {100*ci[0]:.1f}–{100*ci[1]:.1f}%) · units @-110 {r['units_at_minus_110']:+.1f} · "
            f"p(>52.4%)={r['p_value_vs_breakeven_one_sided']:.3f}")


def write_backtest(res: dict) -> dict:
    pr, lm, h = res["preregistration"], res["locked_model"], res["HEADLINE_holdout"]
    tw = res["descriptive_only__tuning_window_in_sample"]
    a = h["accuracy_ats_free"]
    md = [
        "# NFL Lab — Walk-forward Backtest",
        "",
        f"Rule locked at {pr['locked_at']} (before grading). Graded at {res['graded_at']}.",
        "",
        "## Pre-registered rule",
        f"- Spread: bet model side when |model margin − closing spread| ≥ {pr['headline_rule']['spread_edge_min']} pts",
        f"- Total: bet model side when |model total − closing total| ≥ {pr['headline_rule']['total_edge_min']} pts",
        f"- Tuning: {pr['tuning_window'][0]}–{pr['tuning_window'][-1]} only. Holdout: {pr['holdout_window'][0]}–{pr['holdout_window'][-1]} (graded once).",
        f"- Break-even at -110: 52.38%",
        "",
        "## HEADLINE: holdout 2022–2025",
        f"- Spread bets (locked rule): {_rec_line(h['locked_rule']['spread'])}",
        f"- Total bets (locked rule): {_rec_line(h['locked_rule']['total'])}",
        "",
        "### Accuracy (no betting lines used)",
        f"- Games: {a['n_games']}",
        f"- MAE vs final margin: model {a['model_mae_margin']:.2f} vs closing spread {a['market_mae_margin']:.2f}",
        f"- MAE vs final total: model {a['model_mae_total']:.2f} vs closing total {a['market_mae_total']:.2f}",
        f"- Brier (home win): model {a['model_brier']:.4f} vs spread-implied {a['market_brier_from_spread']:.4f}",
        f"- Straight-up accuracy: {100*a['model_straight_up_acc']:.1f}%",
        "",
        "## Locked model",
        f"```json\n{json.dumps(lm, indent=2)}\n```",
        "",
        "## Descriptive only (NOT used to pick the rule)",
        "",
        "### Holdout spread edge buckets",
        _md_table(pd.DataFrame(h["descriptive_only__spread_edge_buckets"]),
                  ["edge_bucket", "bets", "wins", "losses", "pushes", "win_rate", "units_at_minus_110"],
                  {"win_rate": "{:.3f}", "units_at_minus_110": "{:+.1f}"}),
        "",
        "### Holdout total edge buckets",
        _md_table(pd.DataFrame(h["descriptive_only__total_edge_buckets"]),
                  ["edge_bucket", "bets", "wins", "losses", "pushes", "win_rate", "units_at_minus_110"],
                  {"win_rate": "{:.3f}", "units_at_minus_110": "{:+.1f}"}),
        "",
        "### Per season (holdout + tuning window)",
        "",
        "| season | window | games | model MAE | market MAE | spread (locked) | total (locked) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for win, block in [("tuning (in-sample)", tw), ("holdout", h)]:
        for ps in block["descriptive_only__per_season"]:
            ac, sp, to = ps["accuracy_ats_free"], ps["locked_rule_spread"], ps["locked_rule_total"]
            f = lambda r: f"{r['wins']}-{r['losses']}-{r['pushes']} ({100*r['win_rate']:.1f}%)" if r.get("win_rate") is not None else "—"
            md.append(f"| {ps['season']} | {win} | {ac['n_games']} | {ac['model_mae_margin']:.2f} | "
                      f"{ac['market_mae_margin']:.2f} | {f(sp)} | {f(to)} |")
    md += ["", "Tuning-window locked rule (in-sample coefficients, descriptive): "
           f"spread {_rec_line(tw['locked_rule']['spread'])}; total {_rec_line(tw['locked_rule']['total'])}", ""]
    path = OUTPUT_DIR / "backtest" / "backtest.md"
    path.write_text("\n".join(md))
    return {"backtest_md": str(path)}


def write_summary(summary: dict) -> str:
    path = OUTPUT_DIR / "summary.json"
    _json_dump(path, summary)
    return str(path)
