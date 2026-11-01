"""Tests for attendance parsing and fetching."""

import datetime
from unittest.mock import AsyncMock

import pytest

from wilhelmina import AttendanceRange, AttendanceReport, WilmaClient
from wilhelmina.parsers.attendance import _parse_title, parse_attendance_html

# Mirrors the structure of the real attendance view: inline type colours, a header with
# hour column groups of varying width, day rows, a continuation row for overlapping marks,
# a totals row, and the legend.
ATTENDANCE_HTML = """
<html><head><style>
TR TD.at-tp146, .legend .at-tp146 { background-color : #9191ff !important; color : #000000 !important; }
TR TD.at-tp135, .legend .at-tp135 { background-color : #0080FF !important; color : #000000 !important; }
TR TD.at-tp131, .legend .at-tp131 { background-color : #D4D4D4 !important; color : #000000 !important; }
TR TD.at-tp219, .legend .at-tp219 { background-color : #800040 !important; color : #FFFFFF !important; }
</style></head><body><main>
<table class="datatable first attendance-single table">
  <thead><tr>
    <th colspan="2" align="left">Datum </th>
    <th colspan="2" class="center">8</th>
    <th colspan="3" class="center">9</th>
    <th class="center">10</th>
    <th class="center">Sammanlagt </th>
    <th>Kommentarer</th>
  </tr></thead>
  <tbody>
  <tr class="odd">
    <td>Ons </td><td align="right">28.10.2026 </td>
    <td colspan="2">&nbsp;</td>
    <td class="event at-bl at-tp146" colspan="3" title="rl05; övrig positiv feedback; Worked calmly. /Anna Teacher">atea<sup>1</sup></td>
    <td>&nbsp;</td>
    <td class="total zero" align="center">0 </td>
    <td>1: Worked calmly. /atea<br></td>
  </tr>
  <tr>
    <td>Tis </td><td align="right">27.10.2026 </td>
    <td class="event at-bl at-tp135" colspan="2" title="ma05; Ogjorda uppgifter; p. 105 /Bo Teacher">btea<sup>1</sup></td>
    <td colspan="3">&nbsp;</td>
    <td class="event at-bl at-tp131" title="mo05; Beteende; Scribbled on the paper; did not work. /Bo Teacher">btea</td>
    <td class="total zero" align="center">0 </td>
    <td>&nbsp;</td>
  </tr>
  <tr class="odd">
    <td>Fre </td><td align="right">25.9.2026 </td>
    <td class="event at-bl at-tp219" colspan="2" title="gy05; Frånvaro på grund av hälsoskäl /Cy Teacher - 25.9. /Dee Guardian">C.T</td>
    <td colspan="3">&nbsp;</td>
    <td>&nbsp;</td>
    <td class="total" align="center">1 </td>
    <td>&nbsp;</td>
  </tr>
  <tr>
    <td colspan="2"> </td>
    <td colspan="2"> </td>
    <td class="event at-bl at-tp219" colspan="3" title="Frånvaro på grund av hälsoskäl /Ed Teacher">E.T</td>
    <td class="event at-bl at-tp999" title="mu05; Unlisted type /Ed Teacher">E.T</td>
  </tr>
  <tr class="total semi-bold">
    <td colspan="2">Sammanlagt</td><td colspan="6">1</td>
  </tr>
  </tbody>
</table>
<div class="legend"><table>
  <tr><td class="at-tp146 text-center">+</td><td>Övrig positiv feedback</td></tr>
  <tr><td class="at-tp135 text-center">Ogjorda uppgifter</td><td>Ogjorda läxor och uppgifter</td></tr>
  <tr><td class="at-tp131 text-center">Beteende</td><td>Störande eller dåligt beteende</td></tr>
  <tr><td class="at-tp219 text-center">FHs</td><td>Frånvaro på grund av hälsoskäl</td></tr>
  <tr><td class="at-tp188 text-center">+</td><td>Aktivt deltagande</td></tr>
</table></div>
</main></body></html>
"""


def test_parse_types() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    types = {t.id: t for t in report.types}
    assert list(types) == [146, 135, 131, 219, 188]
    assert types[146].code == "+"
    assert types[146].description == "Övrig positiv feedback"
    assert types[146].color == "#9191FF"
    assert types[135].color == "#0080FF"
    # Legend entries without a colour rule
    assert types[188].color is None


def test_parse_marks() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    assert len(report.marks) == 6
    positive, homework, behaviour, absence, continued, unlisted = report.marks

    assert positive.date == datetime.date(2026, 10, 28)
    assert positive.hour == 9
    assert positive.type.id == 146
    assert positive.type.color == "#9191FF"
    assert positive.course == "rl05"
    assert positive.name == "övrig positiv feedback"
    assert positive.comment == "Worked calmly."
    assert positive.teacher == "Anna Teacher"
    assert positive.teacher_code == "atea"
    assert positive.clarification is None

    assert homework.hour == 8
    assert homework.type.code == "Ogjorda uppgifter"
    assert homework.comment == "p. 105"

    assert behaviour.hour == 10
    assert behaviour.comment == "Scribbled on the paper; did not work."

    assert absence.date == datetime.date(2026, 9, 25)
    assert absence.teacher == "Cy Teacher"
    assert absence.clarification == "25.9. /Dee Guardian"
    assert absence.comment is None

    # Continuation rows carry the previous row's date
    assert continued.date == datetime.date(2026, 9, 25)
    assert continued.hour == 9
    assert continued.course is None
    assert continued.name == "Frånvaro på grund av hälsoskäl"
    assert continued.teacher == "Ed Teacher"

    # Types missing from the legend still produce a mark
    assert unlisted.type.id == 999
    assert unlisted.type.description == "Unlisted type"
    assert unlisted.hour == 10


def test_report_filters() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    assert [m.type.id for m in report.marks_with_code("+")] == [146]
    assert len(report.marks_of_type(219)) == 2
    assert len(report.marks_of_type(146, 135)) == 2


def test_report_serializes() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    data = report.to_dict()
    assert data["marks"][0]["date"] == "2026-10-28"
    assert AttendanceReport.from_dict(data) == report


def test_parse_empty_page() -> None:
    report = parse_attendance_html("<html><body><p>Nothing here</p></body></html>")
    assert report.marks == []
    assert report.types == []


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("gy05; aktivt deltagande /A B", ("gy05", "aktivt deltagande", None, "A B", None)),
        ("ma05; Ogjorda; p. 5 /A B", ("ma05", "Ogjorda", "p. 5", "A B", None)),
        ("Frånvaro /A B", (None, "Frånvaro", None, "A B", None)),
        ("Beteende; Was rude /A B", (None, "Beteende", "Was rude", "A B", None)),
        (
            "bk05; Utan material; *Topic \nBook at home /A B",
            ("bk05", "Utan material", "*Topic \nBook at home", "A B", None),
        ),
        ("gy05; Frånvaro /A B - 25.9. /C D", ("gy05", "Frånvaro", None, "A B", "25.9. /C D")),
        ("ma05; Ogjorda; see p. 4 /5 /A B", ("ma05", "Ogjorda", "see p. 4 /5", "A B", None)),
        ("No teacher", (None, "No teacher", None, None, None)),
        ("", (None, None, None, None, None)),
    ],
)
def test_parse_title(title: str, expected: tuple) -> None:
    assert _parse_title(title) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "params"),
    [
        ({}, {"range": "-4"}),
        ({"period": AttendanceRange.FOUR_WEEKS}, {"range": "0"}),
        ({"period": 3}, {"range": "3"}),
        (
            {"start": datetime.date(2024, 8, 1), "end": datetime.date(2025, 7, 31)},
            {"range": "-3", "first": "1.8.2024", "last": "31.7.2025"},
        ),
    ],
)
async def test_get_attendance_params(authenticated_client: WilmaClient, kwargs, params) -> None:
    client = authenticated_client
    client._get_text = AsyncMock(return_value=ATTENDANCE_HTML)

    report = await client.get_attendance(**kwargs)

    client._get_text.assert_awaited_once_with("attendance/view", params=params, user_id=None)
    assert len(report.marks) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": datetime.date(2025, 1, 1)},
        {"end": datetime.date(2025, 1, 1)},
        {"start": datetime.date(2025, 2, 1), "end": datetime.date(2025, 1, 1)},
        {"period": AttendanceRange.CUSTOM},
    ],
)
async def test_get_attendance_invalid_range(authenticated_client: WilmaClient, kwargs) -> None:
    client = authenticated_client
    client._get_text = AsyncMock()

    with pytest.raises(ValueError):
        await client.get_attendance(**kwargs)
    client._get_text.assert_not_awaited()


def test_mark_keys() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    keys = [m.key for m in report.marks]
    assert len(set(keys)) == len(keys)
    assert keys[0] == "2026-10-28|9|146|rl05|atea|övrig positiv feedback"
    # Keys don't depend on the comment or clarification
    assert all(m.key.startswith(m.date.isoformat()) for m in report.marks)
    assert report.marks[3].clarification and "Dee" not in report.marks[3].key


def test_identical_marks_get_distinct_keys() -> None:
    row = (
        '<td class="event at-tp146" title="gy05; aktivt deltagande /A B">A.B</td>'
        '<td class="event at-tp146" title="gy05; aktivt deltagande; other comment /A B">A.B</td>'
    )
    html = (
        '<table class="attendance-single"><thead><tr><th colspan="2">Datum</th>'
        '<th colspan="2">8</th></tr></thead><tbody><tr><td>Mån</td><td>1.9.2025</td>'
        f"{row}</tr></tbody></table>"
    )
    keys = [m.key for m in parse_attendance_html(html).marks]
    assert keys == [
        "2025-09-01|8|146|gy05|A.B|aktivt deltagande",
        "2025-09-01|8|146|gy05|A.B|aktivt deltagande#2",
    ]


def test_report_latest() -> None:
    report = parse_attendance_html(ATTENDANCE_HTML)

    assert report.latest is not None
    assert report.latest.date == datetime.date(2026, 10, 28)
    assert AttendanceReport().latest is None
