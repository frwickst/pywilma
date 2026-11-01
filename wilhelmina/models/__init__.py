"""Models for Wilma API client."""

from wilhelmina.models.attendance import (
    AttendanceMark,
    AttendanceRange,
    AttendanceReport,
    MarkType,
)
from wilhelmina.models.messages import Message, MessageFolder, MessagesList, Reply, Sender
from wilhelmina.models.news import Bulletin, BulletinSection
from wilhelmina.models.overview import (
    Course,
    CourseTeacher,
    DiaryEntry,
    Exam,
    Homework,
    Overview,
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
    "AttendanceMark",
    "AttendanceRange",
    "AttendanceReport",
    "MarkType",
    "Message",
    "MessageFolder",
    "MessagesList",
    "Reply",
    "Sender",
    "Bulletin",
    "BulletinSection",
    "Course",
    "CourseTeacher",
    "DiaryEntry",
    "Exam",
    "Homework",
    "Overview",
    "Lesson",
    "Role",
    "School",
    "ScheduleGroup",
    "ScheduleRoom",
    "ScheduleTeacher",
    "Term",
    "WeekSchedule",
]
