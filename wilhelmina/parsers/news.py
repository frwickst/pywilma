"""Parsers for the Wilma bulletin board (``/<user_id>/news``).

The board is a server-rendered page with three kinds of panels: recent bulletins under date
headings (``19.10.``), and two link-only panels for pinned and older bulletins. The older
bulletins panel is rendered twice, for small and large screens, which is how it is told
apart from the pinned one without relying on the page language.
"""

import datetime
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from wilhelmina.models.news import Bulletin, BulletinSection

_NEWS_LINK_RE = re.compile(r"/news/(\d+)(?:$|[?#])")
_SHORT_DATE_RE = re.compile(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})?$")
# A date inside text, with or without a year: "Published 23.2.2023" or "Published 19.10."
_DATE_IN_TEXT_RE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{4})?(?![\d])")

_SECTION_PRIORITY = {
    BulletinSection.CURRENT: 0,
    BulletinSection.PERMANENT: 1,
    BulletinSection.OLD: 2,
}


def parse_bulletin_list(html: str, today: datetime.date) -> list[Bulletin]:
    """Parse the bulletin board into bulletins, current ones first and newest first.

    ``today`` resolves dates shown without a year to their most recent occurrence.
    """
    soup = BeautifulSoup(html, "html.parser")
    root = soup.find("main") or soup

    found: dict[int, Bulletin] = {}
    for panel in root.select(".panel"):
        if _date_headings(panel):
            bulletins = _parse_current_panel(panel, today)
        else:
            classes: list[str] = list(panel.get("class") or [])
            section = (
                BulletinSection.OLD
                if any(c.startswith("hidden-") for c in classes)
                else BulletinSection.PERMANENT
            )
            bulletins = _parse_link_panel(panel, section)

        for bulletin in bulletins:
            existing = found.get(bulletin.id)
            if existing is None or _rank(bulletin) < _rank(existing):
                found[bulletin.id] = bulletin

    return sorted(
        found.values(),
        key=lambda b: (_rank(b), -(b.date.toordinal() if b.date else 0), -b.id),
    )


def parse_bulletin(html: str, news_id: int, today: datetime.date) -> Bulletin:
    """Parse a single bulletin page.

    ``today`` resolves a published date shown without a year to its most recent occurrence.
    """
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="news-content")
    body = content.find_parent(class_="panel-body") if isinstance(content, Tag) else None
    if not isinstance(body, Tag):
        body = soup.select_one("main .panel-body") or soup.body or soup

    heading = body.find(["h1", "h2", "h3"])
    title = heading.get_text(" ", strip=True) if isinstance(heading, Tag) else ""

    # Content is the lead paragraphs before the main content block, then that block
    parts: list[str] = []
    if isinstance(content, Tag):
        for sibling in content.find_previous_siblings():
            if sibling is heading:
                break
            if isinstance(sibling, Tag) and sibling.name not in ("h1", "h2", "h3"):
                parts.insert(0, str(sibling))
        parts.append(content.decode_contents())
    content_html = "\n".join(part.strip() for part in parts if part.strip()) or None

    published: Optional[datetime.date] = None
    author: Optional[str] = None
    footer = body.select_one(".horizontal-link-container")
    if isinstance(footer, Tag):
        for span in footer.find_all("span", recursive=False):
            text = span.get_text(" ", strip=True)
            match = _DATE_IN_TEXT_RE.search(text)
            if match and published is None:
                day, month, year = match.groups()
                published = _resolve_short_date(f"{day}.{month}.{year or ''}", today)
            elif text and author is None and "vismaicon" not in (span.get("class") or []):
                author = text

    audience: Optional[str] = None
    separator = body.find("hr")
    if isinstance(separator, Tag):
        following = separator.find_next_sibling("div")
        if isinstance(following, Tag) and following is not footer:
            audience = following.get_text(" ", strip=True) or None

    return Bulletin(
        id=news_id,
        title=title,
        date=published,
        author=author,
        audience=audience,
        content_html=content_html,
    )


def _rank(bulletin: Bulletin) -> int:
    return _SECTION_PRIORITY.get(bulletin.section or BulletinSection.OLD, 3)


def _news_id(link: Tag) -> Optional[int]:
    match = _NEWS_LINK_RE.search(str(link.get("href") or ""))
    return int(match.group(1)) if match else None


def _date_headings(panel: Tag) -> list[Tag]:
    return [
        heading
        for heading in panel.find_all("h2")
        if _SHORT_DATE_RE.match(heading.get_text(strip=True))
    ]


def _parse_link_panel(panel: Tag, section: BulletinSection) -> list[Bulletin]:
    bulletins = []
    for link in panel.find_all("a", href=True):
        news_id = _news_id(link)
        title = link.get_text(" ", strip=True)
        if news_id is not None and title:
            bulletins.append(Bulletin(id=news_id, title=title, section=section))
    return bulletins


def _parse_current_panel(panel: Tag, today: datetime.date) -> list[Bulletin]:
    bulletins = []
    for heading in _date_headings(panel):
        day = _resolve_short_date(heading.get_text(strip=True), today)
        for sibling in heading.find_next_siblings():
            if sibling.name == "h2":
                break
            bulletin = _parse_current_item(sibling, day)
            if bulletin:
                bulletins.append(bulletin)
    return bulletins


def _parse_current_item(item: Tag, day: Optional[datetime.date]) -> Optional[Bulletin]:
    news_id = None
    for link in item.find_all("a", href=True):
        news_id = _news_id(link)
        if news_id is not None:
            break
    if news_id is None:
        return None

    title_tag = item.find(["h3", "h4"])
    title = title_tag.get_text(" ", strip=True) if isinstance(title_tag, Tag) else ""

    author = None
    for candidate in item.select("a.profile-link, span.tooltip"):
        author = str(candidate.get("title") or "").strip() or candidate.get_text(strip=True)
        if author:
            break

    return Bulletin(
        id=news_id, title=title, section=BulletinSection.CURRENT, date=day, author=author
    )


def _resolve_short_date(text: str, today: datetime.date) -> Optional[datetime.date]:
    match = _SHORT_DATE_RE.match(text)
    if not match:
        return None
    day, month, year = match.groups()
    if year:
        return _date(year, month, day)
    resolved = _date(str(today.year), month, day)
    if resolved and resolved > today:
        resolved = _date(str(today.year - 1), month, day)
    return resolved


def _date(year: str, month: str, day: str) -> Optional[datetime.date]:
    try:
        return datetime.date(int(year), int(month), int(day))
    except ValueError:
        return None
