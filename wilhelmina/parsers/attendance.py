"""Parser for the Wilma attendance view (``/<user_id>/attendance/view``).

The view is a server-rendered table with one row per school day and one column group per
hour of the day. Each mark is a ``td.event`` cell whose ``at-tp<N>`` class identifies its mark
type and whose ``title`` holds the description. A legend maps type IDs to codes and
descriptions, and an inline stylesheet assigns each type its colour.
"""

import datetime
import re
from typing import Optional

from bs4 import BeautifulSoup, Tag

from wilhelmina.models.attendance import AttendanceMark, AttendanceReport, MarkType

_TYPE_CLASS_RE = re.compile(r"^at-tp(\d+)$")
_TYPE_COLOR_RE = re.compile(
    r"\.at-tp(\d+)\s*\{[^}]*?background-color\s*:\s*(#[0-9a-fA-F]{3,8})", re.IGNORECASE
)
_DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")

# Titles look like "<course>; <name>[; <comment>] /<teacher>[ - <d.m.> /<clarifier>]". The
# course and the teacher suffix are not always present.
_TEACHER_SUFFIX_RE = re.compile(
    r"^(?P<body>.*?) /(?P<teacher>[^/]+?)"
    r"(?: - (?P<clarification>\d{1,2}\.\d{1,2}\.(?:\d{4})? /.+))?$",
    re.DOTALL,
)
# Course codes are single tokens ending in a digit, e.g. "ma05" or "ena205".
_COURSE_RE = re.compile(r"^\S+\d$")


def parse_attendance_html(html: str) -> AttendanceReport:
    """Parse the attendance view HTML into marks and mark types."""
    soup = BeautifulSoup(html, "html.parser")
    types = _parse_types(soup, html)
    types_by_id = {mark_type.id: mark_type for mark_type in types}

    marks: list[AttendanceMark] = []
    for table in _attendance_tables(soup):
        marks.extend(_parse_table(table, types_by_id))
    _assign_keys(marks)

    return AttendanceReport(marks=marks, types=types)


def _assign_keys(marks: list[AttendanceMark]) -> None:
    occurrences: dict[str, int] = {}
    for mark in marks:
        identity = mark.identity()
        occurrences[identity] = occurrences.get(identity, 0) + 1
        count = occurrences[identity]
        mark.key = identity if count == 1 else f"{identity}#{count}"


def _type_id(cell: Tag) -> Optional[int]:
    for css_class in cell.get("class") or []:
        match = _TYPE_CLASS_RE.match(css_class)
        if match:
            return int(match.group(1))
    return None


def _parse_types(soup: BeautifulSoup, html: str) -> list[MarkType]:
    colors = {int(type_id): color.upper() for type_id, color in _TYPE_COLOR_RE.findall(html)}

    types = []
    for legend in soup.select(".legend"):
        for row in legend.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            type_id = _type_id(cells[0])
            if type_id is None:
                continue
            types.append(
                MarkType(
                    id=type_id,
                    code=cells[0].get_text(strip=True),
                    description=cells[1].get_text(strip=True),
                    color=colors.get(type_id),
                )
            )
    return types


def _attendance_tables(soup: BeautifulSoup) -> list[Tag]:
    tables = [
        table
        for table in soup.find_all("table")
        if any(c.startswith("attendance") for c in table.get("class") or [])
    ]
    if tables:
        return tables
    # Fall back to any table containing marks outside the legend
    return [
        table
        for table in soup.find_all("table")
        if table.select_one("td.event") and not table.find_parent(class_="legend")
    ]


def _colspan(cell: Tag) -> int:
    try:
        return max(1, int(str(cell.get("colspan") or 1)))
    except ValueError:
        return 1


def _hour_by_column(table: Tag) -> list[Optional[int]]:
    """Map each grid column to the hour shown in the header above it."""
    header_row = table.select_one("thead tr")
    if header_row is None:
        return []

    hours: list[Optional[int]] = []
    for th in header_row.find_all(["th", "td"]):
        text = th.get_text(strip=True)
        hour = int(text) if text.isdigit() else None
        hours.extend([hour] * _colspan(th))
    return hours


def _parse_table(table: Tag, types_by_id: dict[int, MarkType]) -> list[AttendanceMark]:
    hours = _hour_by_column(table)
    body = table.find("tbody")
    if not isinstance(body, Tag):
        body = table

    marks = []
    date: Optional[datetime.date] = None
    for row in body.find_all("tr", recursive=False):
        cells = row.find_all(["td", "th"], recursive=False)
        # Overlapping marks on the same day continue on extra rows without a date
        date = _row_date(cells) or date
        if date is None:
            continue

        column = 0
        for cell in cells:
            if "event" in (cell.get("class") or []):
                hour = hours[column] if column < len(hours) else None
                mark = _parse_mark(cell, date, hour, types_by_id)
                if mark is not None:
                    marks.append(mark)
            column += _colspan(cell)
    return marks


def _row_date(cells: list[Tag]) -> Optional[datetime.date]:
    for cell in cells[:3]:
        text = cell.get_text(strip=True)
        if _DATE_RE.match(text):
            return datetime.datetime.strptime(text, "%d.%m.%Y").date()
    return None


def _parse_mark(
    cell: Tag,
    date: datetime.date,
    hour: Optional[int],
    types_by_id: dict[int, MarkType],
) -> Optional[AttendanceMark]:
    type_id = _type_id(cell)
    if type_id is None:
        return None

    title = str(cell.get("title") or "").strip()
    course, name, comment, teacher, clarification = _parse_title(title)

    mark_type = types_by_id.get(type_id) or MarkType(
        id=type_id, code=name or "", description=name or ""
    )

    # The cell shows the teacher's short code, followed by a footnote number for comments
    for sup in cell.find_all("sup"):
        sup.extract()
    teacher_code = cell.get_text(strip=True) or None

    return AttendanceMark(
        date=date,
        type=mark_type,
        title=title,
        name=name,
        hour=hour,
        course=course,
        comment=comment,
        teacher=teacher,
        teacher_code=teacher_code,
        clarification=clarification,
    )


def _parse_title(
    title: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Split a mark title into course, name, comment, teacher and clarification."""
    teacher: Optional[str] = None
    clarification: Optional[str] = None
    body = title

    match = _TEACHER_SUFFIX_RE.match(title)
    if match:
        body = match.group("body")
        teacher = match.group("teacher").strip() or None
        clarification = match.group("clarification")

    segments = [segment.strip() for segment in body.split(";")]
    course: Optional[str] = None
    if len(segments) > 1 and _COURSE_RE.match(segments[0]):
        course = segments.pop(0)

    name = (segments[0] or None) if segments else None
    comment = "; ".join(segments[1:]).strip() or None
    return course, name, comment, teacher, clarification
