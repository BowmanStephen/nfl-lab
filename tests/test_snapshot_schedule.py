"""The pre-kickoff cron has to land inside the two-hour window.

Week 5's London game kicked at 13:30 UTC. The 11:15 UTC refresh was 15 minutes
early, and the next snapshot was 16:15 UTC, after kickoff. Week 6 has the same
London slot.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nfl_lab.config import PRE_KICKOFF_MINUTES

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "nightly.yml"

# (kickoff UTC, label). Week 5 is the card. Week 6 is the next slate, including
# the Thursday nighter and the London game.
KICKOFFS = [
    ("2026-10-09T00:15:00+00:00", "week 5 TB-DAL"),
    ("2026-10-11T13:30:00+00:00", "week 5 PHI-JAX London"),
    ("2026-10-11T17:00:00+00:00", "week 5 Sunday 1pm"),
    ("2026-10-11T20:05:00+00:00", "week 5 Sunday 4:05"),
    ("2026-10-11T20:25:00+00:00", "week 5 Sunday 4:25"),
    ("2026-10-12T00:20:00+00:00", "week 5 Sunday night"),
    ("2026-10-13T00:15:00+00:00", "week 5 Monday night"),
    ("2026-10-16T00:15:00+00:00", "week 6 Thursday night"),
    ("2026-10-18T13:30:00+00:00", "week 6 HOU-JAX London"),
    ("2026-10-18T17:00:00+00:00", "week 6 Sunday 1pm"),
    ("2026-10-18T20:05:00+00:00", "week 6 Sunday 4:05"),
    ("2026-10-18T20:25:00+00:00", "week 6 Sunday 4:25"),
    ("2026-10-19T00:20:00+00:00", "week 6 Sunday night"),
    ("2026-10-20T00:15:00+00:00", "week 6 Monday night"),
]


def _cron_specs(text: str) -> list[tuple[set[int], set[int] | None]]:
    """(hours, dow or None for every day) for each scheduled cron."""
    specs = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('- cron:'):
            continue
        expr = line.split('"')[1]
        minute, hour, _dom, _month, dow = expr.split()
        assert minute == "15"
        hours: set[int] = set()
        for part in hour.split(","):
            if "-" in part:
                start, end = part.split("-")
                hours.update(range(int(start), int(end) + 1))
            else:
                hours.add(int(part))
        if dow == "*":
            specs.append((hours, None))
        else:
            specs.append((hours, {int(d) for d in dow.split(",")}))
    return specs


def _covered(kick: datetime, specs: list[tuple[set[int], set[int] | None]]) -> bool:
    window = timedelta(minutes=PRE_KICKOFF_MINUTES)
    start = kick - window
    slot = start.replace(minute=15, second=0, microsecond=0)
    if slot < start:
        slot += timedelta(hours=1)
    while slot < kick:
        dow = slot.weekday()
        # cron dow: 0 is Sunday. Python weekday: 0 is Monday.
        cron_dow = (dow + 1) % 7
        for hours, days in specs:
            if slot.hour in hours and (days is None or cron_dow in days):
                return True
        slot += timedelta(hours=1)
    return False


def test_pre_kickoff_crons_cover_london_and_the_rest_of_the_slate():
    text = WORKFLOW.read_text()
    assert 'cron: "15 11 * * *"' in text
    assert 'cron: "15 12-23,0-4 * * 0,1,4,5,6"' in text
    # The morning refresh is the only schedule that rebuilds the card.
    # The else of that check, not a stray string, assigns line-snapshot.
    assert (
        'elif [ "${{ github.event.schedule }}" = "15 11 * * *" ]; then\n'
        '            CMD="refresh"\n'
        "          else\n"
        '            CMD="line-snapshot"'
    ) in text
    specs = _cron_specs(text)
    missed = [
        label for raw, label in KICKOFFS
        if not _covered(datetime.fromisoformat(raw), specs)
    ]
    assert missed == []


def test_buf_la_is_inside_the_515_and_615_pm_ct_runs():
    """Kickoff is 7:15 PM CT. 5:15 and 6:15 PM CT are 22:15 and 23:15 UTC."""
    specs = _cron_specs(WORKFLOW.read_text())
    kick = datetime.fromisoformat("2026-10-13T00:15:00+00:00")
    for label, raw in (
        ("5:15 PM CT", "2026-10-12T22:15:00+00:00"),
        ("6:15 PM CT", "2026-10-12T23:15:00+00:00"),
    ):
        slot = datetime.fromisoformat(raw)
        assert timedelta(0) < kick - slot <= timedelta(minutes=PRE_KICKOFF_MINUTES)
        cron_dow = (slot.weekday() + 1) % 7
        assert any(
            slot.hour in hours and slot.minute == 15 and (days is None or cron_dow in days)
            for hours, days in specs
        ), label
