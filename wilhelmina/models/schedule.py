"""Schedule and role models for Wilma."""

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import List, Optional

from mashumaro import DataClassDictMixin
from mashumaro.config import BaseConfig


@dataclass
class School(DataClassDictMixin):
    """A school a role belongs to."""

    id: int
    caption: str = ""


@dataclass
class Role(DataClassDictMixin):
    """A role the logged-in account can act in, e.g. a guardian role for one child."""

    name: str
    """Name of the person the role is for; for a guardian role, the child's name."""
    type: str
    """Role type, e.g. ``guardian``, ``student`` or ``passwd`` (the account itself)."""
    primus_id: int
    slug: str = ""
    """URL prefix of the role, e.g. ``/!01234567``; empty for the account itself."""
    schools: List[School] = field(default_factory=list)

    class Config(BaseConfig):
        aliases = {"primus_id": "primusId"}

    @property
    def user_id(self) -> Optional[str]:
        """The role's user ID as used in URLs (e.g. ``!01234567``), if it has one."""
        return self.slug.lstrip("/") or None


@dataclass
class ScheduleTeacher(DataClassDictMixin):
    """A teacher of a scheduled lesson."""

    id: int
    caption: str = ""
    long_caption: str = ""

    class Config(BaseConfig):
        aliases = {"id": "Id", "caption": "Caption", "long_caption": "LongCaption"}

    @property
    def name(self) -> str:
        """The most descriptive name available."""
        return self.long_caption or self.caption


@dataclass
class ScheduleRoom(DataClassDictMixin):
    """A room of a scheduled lesson."""

    id: int
    caption: str = ""
    long_caption: str = ""

    class Config(BaseConfig):
        aliases = {"id": "Id", "caption": "Caption", "long_caption": "LongCaption"}

    @property
    def name(self) -> str:
        """The short room name, e.g. ``419``."""
        return self.caption or self.long_caption


@dataclass
class ScheduleGroup(DataClassDictMixin):
    """A teaching group (course) taking part in a lesson."""

    id: int
    course_id: Optional[int] = None
    short_caption: str = ""
    caption: str = ""
    full_caption: str = ""
    class_name: Optional[str] = None
    teachers: List[ScheduleTeacher] = field(default_factory=list)
    rooms: List[ScheduleRoom] = field(default_factory=list)

    class Config(BaseConfig):
        aliases = {
            "id": "Id",
            "course_id": "CourseId",
            "short_caption": "ShortCaption",
            "caption": "Caption",
            "full_caption": "FullCaption",
            "class_name": "Class",
            "teachers": "Teachers",
            "rooms": "Rooms",
        }


@dataclass
class Lesson(DataClassDictMixin):
    """A lesson on a specific date. Times are local time of the Wilma instance."""

    date: datetime.date
    start: datetime.time
    end: datetime.time
    groups: List[ScheduleGroup] = field(default_factory=list)
    class_name: Optional[str] = None
    color: Optional[str] = None
    reservation_id: Optional[int] = None
    schedule_id: Optional[int] = None

    @property
    def subject(self) -> str:
        """Name of the course(s) in the lesson."""
        return ", ".join(group.caption or group.short_caption for group in self.groups)

    @property
    def teachers(self) -> list[str]:
        """Names of all teachers of the lesson."""
        return _unique(teacher.name for group in self.groups for teacher in group.teachers)

    @property
    def rooms(self) -> list[str]:
        """Names of all rooms of the lesson."""
        return _unique(room.name for group in self.groups for room in group.rooms)

    @property
    def starts_at(self) -> datetime.datetime:
        """Start as a naive local datetime."""
        return datetime.datetime.combine(self.date, self.start)

    @property
    def ends_at(self) -> datetime.datetime:
        """End as a naive local datetime."""
        return datetime.datetime.combine(self.date, self.end)


@dataclass
class Term(DataClassDictMixin):
    """A school term (period)."""

    name: str
    start_date: datetime.date
    end_date: datetime.date

    class Config(BaseConfig):
        aliases = {"name": "Name", "start_date": "StartDate", "end_date": "EndDate"}


@dataclass
class WeekSchedule(DataClassDictMixin):
    """Lessons of one Monday-to-Sunday week, reflecting holidays and other exceptions."""

    week_start: datetime.date
    lessons: List[Lesson] = field(default_factory=list)
    terms: List[Term] = field(default_factory=list)

    @property
    def week_end(self) -> datetime.date:
        """The Sunday ending the week."""
        return self.week_start + datetime.timedelta(days=6)

    def lessons_on(self, day: datetime.date) -> list[Lesson]:
        """Lessons on ``day``, in order."""
        return [lesson for lesson in self.lessons if lesson.date == day]


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
