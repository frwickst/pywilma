"""Tests for the overview: exams, courses, homework and lesson diary."""

import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from wilhelmina import Exam, Overview, WilmaClient, WilmaError

TEACHER = {"TeacherId": 1, "TeacherName": "Teacher Anna", "TeacherCode": "tann"}
SECOND_TEACHER = {"TeacherId": 2, "TeacherName": "", "TeacherCode": "tbo"}

OVERVIEW: dict[str, Any] = {
    "Role": "guardian",
    "AddAppt": False,
    "Schedule": [],
    "Exams": [
        {
            "Id": 11,
            "ExamId": 501,
            "Course": "ma ma05",
            "CourseId": 110,
            "CourseTitle": "Matematik",
            "Grade": "9",
            "ExamSeen": "2026-10-23",
            "ExamSeenDate": "Fr 23.10.2026",
            "Teachers": [TEACHER],
            "Date": "24.9.2026",
            "Info": "Chapters 1-4  \r\nPractise tables\r\n",
        },
        {
            "Id": 12,
            "ExamId": 502,
            "Course": "sv sv05",
            "CourseId": 120,
            "CourseTitle": "Svenska",
            "Teachers": [TEACHER, SECOND_TEACHER],
            "Date": "12.11.2026",
            "Info": "Word classes",
        },
        {"Id": 12, "ExamId": None, "Date": "1.1.2026"},
    ],
    "Groups": [
        {
            "Id": 11,
            "CourseId": 110,
            "CourseName": "Matematik",
            "CourseCode": "ma05",
            "Name": "ma",
            "Caption": "ma ma05",
            "StartDate": "2026-08-11",
            "EndDate": "2027-02-19",
            "Committed": False,
            "Teachers": [TEACHER],
            "Homework": [
                {"RowNumber": 2, "Date": "2026-10-20", "Homework": "Page 12\r\n"},
                {"RowNumber": 4, "Date": "2026-10-26", "Homework": "Page 20"},
                {"RowNumber": 3, "Date": "2026-10-22", "Homework": "  "},
            ],
            "Diary": [
                {
                    "RowNumber": 4,
                    "Date": "2026-10-26",
                    "Lesson": "",
                    "Note": "Chapter 5",
                    **TEACHER,
                },
                {"RowNumber": 2, "Date": "2026-10-20", "Lesson": "", "Note": "", **TEACHER},
            ],
            "Exams": [
                {
                    "Id": 501,
                    "Date": "2026-09-24",
                    "Name": "",
                    "Info": "Chapters 1-4",
                    "Grade": "9",
                    "VerbalGrade": "Good work",
                },
                {
                    "Id": 503,
                    "Date": "2026-12-01",
                    "Name": "Final test",
                    "Info": "",
                    "Grade": "",
                    "VerbalGrade": "",
                },
            ],
        },
        {
            "Id": 12,
            "CourseId": 120,
            "CourseName": "Svenska",
            "CourseCode": "sv05",
            "Name": "sv",
            "Caption": "sv sv05",
            "StartDate": "2026-08-11",
            "EndDate": "2027-02-19",
            "Committed": True,
            "Teachers": [TEACHER, SECOND_TEACHER],
            "Homework": [{"RowNumber": 1, "Date": "2026-10-26", "Homework": "Read ch. 8"}],
            "Diary": [],
            "Exams": [{"Id": 502, "Date": "2026-11-12", "Name": "", "Info": "Word classes"}],
        },
    ],
}


def _client(response: Any) -> WilmaClient:
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "sid"
    client._get_json = AsyncMock(return_value=response)
    return client


def test_overview_exams() -> None:
    overview = Overview.from_api(OVERVIEW)

    assert [exam.id for exam in overview.exams] == [501, 502, 503]
    graded = overview.exams[0]
    assert isinstance(graded, Exam)
    assert graded.date == datetime.date(2026, 9, 24)
    assert graded.subject == "Matematik"
    assert graded.course == "ma ma05"
    assert graded.grade == "9"
    # Verbal grade only appears in the course's exam list
    assert graded.verbal_grade == "Good work"
    assert graded.seen == datetime.date(2026, 10, 23)
    assert graded.info == "Chapters 1-4\nPractise tables"
    assert graded.graded
    assert graded.teacher_names == ["Teacher Anna"]
    assert graded.group_id == 11
    assert graded.course_id == 110

    upcoming = overview.exams[1]
    assert upcoming.grade is None
    assert upcoming.seen is None
    assert not upcoming.graded
    assert upcoming.teacher_names == ["Teacher Anna", "tbo"]
    assert upcoming.title == "Svenska"

    # Only listed under its course
    only_in_course = overview.exams[2]
    assert only_in_course.subject == "Matematik"
    assert only_in_course.name == "Final test"
    assert only_in_course.title == "Matematik: Final test"
    assert only_in_course.info is None
    assert only_in_course.grade is None

    assert [e.id for e in overview.upcoming_exams(datetime.date(2026, 11, 12))] == [502, 503]
    assert [e.id for e in overview.graded_exams()] == [501]


def test_overview_courses_homework_and_diary() -> None:
    overview = Overview.from_api(OVERVIEW)

    math, swedish = overview.courses
    assert math.name == "Matematik"
    assert math.code == "ma05"
    assert math.caption == "ma ma05"
    assert math.start_date == datetime.date(2026, 8, 11)
    assert math.end_date == datetime.date(2027, 2, 19)
    assert not math.committed
    assert swedish.committed
    assert swedish.teacher_names == ["Teacher Anna", "tbo"]
    # Course exams are the merged exams
    assert math.exams[0] is overview.exams[0]

    # Empty homework entries are dropped; newest first
    assert [hw.text for hw in math.homework] == ["Page 20", "Page 12"]
    homework = overview.homework
    assert [(hw.subject, hw.text) for hw in homework] == [
        ("Svenska", "Read ch. 8"),
        ("Matematik", "Page 20"),
        ("Matematik", "Page 12"),
    ]
    assert homework[1].key == "11|4|2026-10-26"
    assert homework[1].course == "ma ma05"

    # Diary entries without content are left out of the combined list
    assert len(math.diary) == 2
    diary = overview.diary
    assert len(diary) == 1
    assert diary[0].note == "Chapter 5"
    assert diary[0].lesson is None
    assert diary[0].teacher is not None
    assert diary[0].teacher.code == "tann"
    assert diary[0].subject == "Matematik"


def test_overview_empty() -> None:
    overview = Overview.from_api({"Exams": None, "Groups": "unexpected"})

    assert overview.exams == []
    assert overview.courses == []
    assert overview.homework == []
    assert overview.diary == []


def test_overview_tolerates_bad_dates() -> None:
    overview = Overview.from_api(
        {
            "Exams": [{"Id": 1, "ExamId": 9, "Date": "not a date"}],
            "Groups": [
                {
                    "Id": 1,
                    "StartDate": "",
                    "Homework": [{"RowNumber": 1, "Date": "31.2.2026", "Homework": "x"}],
                    "Diary": [{"RowNumber": 1, "Date": None}],
                    "Exams": [],
                }
            ],
        }
    )

    assert overview.exams == []
    assert overview.courses[0].start_date is None
    assert overview.courses[0].homework == []
    assert overview.courses[0].diary == []


def test_overview_round_trip() -> None:
    overview = Overview.from_api(OVERVIEW)

    assert Overview.from_dict(overview.to_dict()) == overview


@pytest.mark.asyncio
async def test_get_overview() -> None:
    client = _client(OVERVIEW)

    overview = await client.get_overview(user_id="!67890")

    client._get_json.assert_awaited_once_with("overview", user_id="!67890")
    assert len(overview.courses) == 2
    assert len(overview.exams) == 3


@pytest.mark.asyncio
async def test_get_exams() -> None:
    client = _client(OVERVIEW)

    exams = await client.get_exams()

    client._get_json.assert_awaited_once_with("overview", user_id=None)
    assert [exam.id for exam in exams] == [501, 502, 503]


@pytest.mark.asyncio
async def test_get_overview_unexpected_response() -> None:
    with pytest.raises(WilmaError, match="Unexpected overview response"):
        await _client(["not", "a", "dict"]).get_overview()

    with pytest.raises(WilmaError, match="Unexpected overview response"):
        await _client({"Groups": [{"CourseName": "No ID"}]}).get_overview()
