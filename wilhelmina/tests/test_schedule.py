"""Tests for roles and schedule."""

import datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest

from wilhelmina import Lesson, Role, WeekSchedule, WilmaClient, WilmaError

ROLES = {
    "statusCode": 200,
    "payload": [
        {"name": "Parent Account", "type": "passwd", "primusId": 1, "slug": "", "schools": []},
        {
            "name": "Child One",
            "type": "guardian",
            "primusId": 345,
            "formKey": "guardian:345:secret",
            "slug": "/!12345",
            "schools": [{"id": 58, "caption": "Test School", "features": ["school_common"]}],
        },
    ],
}


def _lesson(day: int, start: str, end: str, caption: str, teachers: int = 1) -> dict[str, Any]:
    return {
        "ReservationID": 100 + day,
        "ScheduleID": 1,
        "Day": day,
        "Start": start,
        "End": end,
        "Color": "#A6CAF0",
        "X1": 0,
        "Y1": 0,
        "X2": 10000,
        "Y2": 45,
        "Class": "3B",
        "AllowEdit": False,
        "AllowAddMoveRemove": False,
        "Groups": [
            {
                "Id": 7,
                "CourseId": 70,
                "ShortCaption": caption[:2].lower(),
                "Caption": caption,
                "FullCaption": caption,
                "Class": "3B",
                "Teachers": [
                    {
                        "Id": i,
                        "Caption": "",
                        "LongCaption": f"Teacher {i}",
                        "ScheduleVisible": False,
                    }
                    for i in range(teachers)
                ],
                "Rooms": [{"Id": 1, "Caption": "419", "LongCaption": "419 Classroom"}],
            }
        ],
    }


SCHEDULE = {
    "Schedule": [
        _lesson(2, "10:00", "10:45", "Matematik"),
        _lesson(1, "09:15", "10:00", "Svenska", teachers=2),
        _lesson(1, "08:15", "09:00", "Musik"),
    ],
    "Terms": [{"Name": "1. perioden", "StartDate": "2026-08-11", "EndDate": "2027-02-19"}],
}


def _client(responses: dict[str, Any]) -> WilmaClient:
    client = WilmaClient("https://test.inschool.fi")
    client.user_id = "!12345"
    client._sid = "sid"

    async def get_json(
        path: str,
        params: dict | None = None,
        *,
        user_scoped: bool = True,
        user_id: str | None = None,
    ):
        return responses[path]

    client._get_json = AsyncMock(side_effect=get_json)
    return client


@pytest.mark.asyncio
async def test_get_roles() -> None:
    client = _client({"api/v1/accounts/me/roles": ROLES})

    roles = await client.get_roles()

    client._get_json.assert_awaited_once_with("api/v1/accounts/me/roles", user_scoped=False)
    assert [r.type for r in roles] == ["passwd", "guardian"]
    child = roles[1]
    assert isinstance(child, Role)
    assert child.name == "Child One"
    assert child.primus_id == 345
    assert child.user_id == "!12345"
    assert child.schools[0].caption == "Test School"
    assert roles[0].user_id is None
    assert "formKey" not in str(child.to_dict())


@pytest.mark.asyncio
async def test_get_roles_unexpected_response() -> None:
    client = _client({"api/v1/accounts/me/roles": {"error": "nope"}})

    with pytest.raises(WilmaError, match="Unexpected roles response"):
        await client.get_roles()


@pytest.mark.asyncio
async def test_get_schedule() -> None:
    client = _client({"api/v1/accounts/me/roles": ROLES, "schedule/export/students/345": SCHEDULE})

    week = await client.get_schedule(datetime.date(2026, 11, 4))

    client._get_json.assert_any_await(
        "schedule/export/students/345",
        params={"date": "4.11.2026", "getfullweek": "true"},
        user_id=None,
    )
    assert isinstance(week, WeekSchedule)
    assert week.week_start == datetime.date(2026, 11, 2)
    assert week.week_end == datetime.date(2026, 11, 8)
    assert [(lesson.date.day, lesson.start.hour) for lesson in week.lessons] == [
        (2, 8),
        (2, 9),
        (3, 10),
    ]
    assert week.terms[0].end_date == datetime.date(2027, 2, 19)

    svenska = week.lessons[1]
    assert isinstance(svenska, Lesson)
    assert svenska.subject == "Svenska"
    assert svenska.teachers == ["Teacher 0", "Teacher 1"]
    assert svenska.rooms == ["419"]
    assert svenska.starts_at == datetime.datetime(2026, 11, 2, 9, 15)
    assert svenska.ends_at == datetime.datetime(2026, 11, 2, 10, 0)
    assert svenska.color == "#A6CAF0"

    assert [lesson.subject for lesson in week.lessons_on(datetime.date(2026, 11, 2))] == [
        "Musik",
        "Svenska",
    ]
    assert week.lessons_on(datetime.date(2026, 11, 5)) == []


@pytest.mark.asyncio
async def test_get_schedule_sunday_belongs_to_preceding_week() -> None:
    client = _client({"api/v1/accounts/me/roles": ROLES, "schedule/export/students/345": SCHEDULE})

    week = await client.get_schedule(datetime.date(2026, 11, 8))

    assert week.week_start == datetime.date(2026, 11, 2)


@pytest.mark.asyncio
async def test_get_schedule_defaults_to_today_and_caches_role() -> None:
    client = _client({"api/v1/accounts/me/roles": ROLES, "schedule/export/students/345": SCHEDULE})

    first = await client.get_schedule()
    await client.get_schedule()

    today = client.today()
    assert first.week_start == today - datetime.timedelta(days=today.weekday())
    paths = [call.args[0] for call in client._get_json.await_args_list]
    assert paths.count("api/v1/accounts/me/roles") == 1


@pytest.mark.asyncio
async def test_get_schedule_empty_week() -> None:
    client = _client(
        {"api/v1/accounts/me/roles": ROLES, "schedule/export/students/345": {"Schedule": []}}
    )

    week = await client.get_schedule(datetime.date(2026, 10, 14))

    assert week.lessons == []
    assert week.terms == []


@pytest.mark.asyncio
async def test_get_schedule_without_matching_role() -> None:
    client = _client({"api/v1/accounts/me/roles": {"payload": ROLES["payload"][:1]}})

    with pytest.raises(WilmaError, match="No role found"):
        await client.get_schedule()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        ["not", "a", "dict"],
        {"Schedule": [{"Day": 1, "Start": "nonsense", "End": "10:00"}]},
        {"Schedule": [{"Start": "09:00", "End": "10:00"}]},
    ],
)
async def test_get_schedule_unexpected_response(payload: Any) -> None:
    client = _client({"api/v1/accounts/me/roles": ROLES, "schedule/export/students/345": payload})

    with pytest.raises(WilmaError, match="Unexpected schedule response"):
        await client.get_schedule(datetime.date(2026, 11, 4))


def test_week_schedule_serializes() -> None:
    week = WeekSchedule(week_start=datetime.date(2026, 11, 2))
    assert WeekSchedule.from_dict(week.to_dict()) == week


TWO_CHILDREN = {
    "payload": [
        {"name": "Parent", "type": "passwd", "primusId": 1, "slug": ""},
        {"name": "Child One", "type": "guardian", "primusId": 345, "slug": "/!12345"},
        {"name": "Child Two", "type": "guardian", "primusId": 678, "slug": "/!67890"},
        {"name": "Some Teacher", "type": "teacher", "primusId": 9, "slug": "/!09999"},
    ]
}


@pytest.mark.asyncio
async def test_get_students() -> None:
    client = _client({"api/v1/accounts/me/roles": TWO_CHILDREN})

    students = await client.get_students()

    assert [(s.name, s.user_id) for s in students] == [
        ("Child One", "!12345"),
        ("Child Two", "!67890"),
    ]


@pytest.mark.asyncio
async def test_get_schedule_for_other_student() -> None:
    client = _client(
        {"api/v1/accounts/me/roles": TWO_CHILDREN, "schedule/export/students/678": SCHEDULE}
    )

    week = await client.get_schedule(datetime.date(2026, 11, 4), user_id="!67890")

    client._get_json.assert_any_await(
        "schedule/export/students/678",
        params={"date": "4.11.2026", "getfullweek": "true"},
        user_id="!67890",
    )
    assert len(week.lessons) == 3
