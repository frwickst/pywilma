"""Wilma API client."""

from wilhelmina.client import AuthenticationError, WilmaClient, WilmaError
from wilhelmina.models import (
    AttendanceMark,
    AttendanceRange,
    AttendanceReport,
    MarkType,
    Message,
    MessageFolder,
    MessagesList,
    Reply,
    Sender,
)
from wilhelmina.models.schedule import (
    Lesson,
    Role,
    ScheduleGroup,
    ScheduleRoom,
    ScheduleTeacher,
    School,
    Term,
    WeekSchedule,
)

__all__ = [
    "WilmaClient",
    "WilmaError",
    "AuthenticationError",
    "AttendanceMark",
    "AttendanceRange",
    "AttendanceReport",
    "MarkType",
    "Message",
    "MessageFolder",
    "MessagesList",
    "Reply",
    "Sender",
    "Lesson",
    "Role",
    "School",
    "ScheduleGroup",
    "ScheduleRoom",
    "ScheduleTeacher",
    "Term",
    "WeekSchedule",
]
