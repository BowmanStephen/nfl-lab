"""The home page must not link to a previews page that is not in public/."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"

_PREVIEW_LINK_FOR = re.compile(
    r"function previewLinkFor\(week, pageExists\) \{\s*"
    r"if \(pageExists\) \{\s*"
    r"return \{ href: `([^`]+)`, text: `([^`]+)` \};\s*"
    r"\}\s*"
    r"return \{ href: (null|`[^`]*`), text: `([^`]+)` \};\s*"
    r"\}"
)


def _fill(template: str, week: int) -> str:
    return template.replace("${week}", str(week))


def _preview_link_for(js: str, week: int, page_exists: bool) -> dict:
    match = _PREVIEW_LINK_FOR.search(js)
    assert match, "previewLinkFor must return a href only when that week's preview page exists"
    href_tpl, text_tpl, missing_href, missing_text = match.groups()
    if page_exists:
        return {"href": _fill(href_tpl, week), "text": _fill(text_tpl, week)}
    href = None if missing_href == "null" else _fill(missing_href.strip("`"), week)
    return {"href": href, "text": _fill(missing_text, week)}


def _static_preview_hrefs(index_html: str) -> list[str]:
    hrefs = []
    for href in re.findall(r'href="([^"]*previews/[^"]+\.html)"', index_html):
        hrefs.append(href.removeprefix("../"))
    return hrefs


def test_home_does_not_link_to_a_missing_preview_page():
    index = (PUBLIC / "index.html").read_text()
    js = (PUBLIC / "assets" / "site.js").read_text()
    week = int(json.loads((PUBLIC / "api" / "picks.json").read_text())["week"])
    page = PUBLIC / "previews" / f"week{week}.html"
    slot = re.search(r'<p class="next-link" id="previews-link">(.*?)</p>', index, re.S)
    assert slot is not None and slot.group(1).strip() == "", (
        "the home previews line must ship empty so a placeholder does not flash "
        "before site.js writes the link or the coming-soon text"
    )
    hrefs = _static_preview_hrefs(index)

    unconditional = 'prev.href = `previews/week${card.week}.html`'
    assert unconditional not in js, (
        f"home sets #previews-link to previews/week{week}.html "
        "without checking that the page exists"
    )
    assert '$("previews-link")' in js
    assert "previewLinkFor(card.week, await previewExists(card.week))" in js
    render = re.search(r"function renderPreviewLink\(el, link\) \{([\s\S]*?)\n\}", js)
    assert render, "renderPreviewLink must decide whether the home preview line is a link"
    body = render.group(1)
    assert "if (link.href)" in body
    assert "a.href = link.href" in body
    assert "previews/week" not in body

    link = _preview_link_for(js, week, page.is_file())
    if link["href"]:
        hrefs.append(link["href"])
    else:
        assert link["text"] == f"Week {week} previews are coming soon"

    missing = [href for href in hrefs if not (PUBLIC / href).is_file()]
    assert missing == [], f"home links to missing previews pages: {missing}"
