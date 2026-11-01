"""Attendance (lesson notes) models for Wilma.

Wilma records absences, lateness, positive feedback, missing homework, behaviour notes and
similar lesson notes as "marks". Which mark types exist, and their codes and colours, is
configured per school; ``MarkType`` carries that configuration as Wilma reports it.
"""

import datetime
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional

from mashumaro import DataClassDictMixin


class AttendanceRange(IntEnum):
    """Predefined date ranges of the attendance view.

    Schools can have more periods than the two listed; any period number is accepted where a
    range is expected.
    """

    FOUR_WEEKS = 0
    AUTUMN = -1
    SPRING = -2
    CUSTOM = -3
    SCHOOL_YEAR = -4
    PERIOD_1 = 1
    PERIOD_2 = 2


@dataclass
class MarkType(DataClassDictMixin):
    """A kind of mark, as listed in the school's legend."""

    id: int
    code: str
    description: str
    color: Optional[str] = None
    """Background colour used by Wilma, e.g. ``#9191FF``."""


@dataclass
class AttendanceMark(DataClassDictMixin):
    """A single mark on a lesson."""

    date: datetime.date
    type: MarkType
    title: str
    """Wilma's full description of the mark, which the other text fields are parsed from."""
    name: Optional[str] = None
    """Mark name as written by the teacher, often more specific than the type's description."""
    hour: Optional[int] = None
    """Hour of the day the lesson falls in, taken from the view's column headers."""
    course: Optional[str] = None
    comment: Optional[str] = None
    teacher: Optional[str] = None
    teacher_code: Optional[str] = None
    clarification: Optional[str] = None
    """Clarification note appended to the mark, e.g. ``25.9. /Guardian Name``."""
    key: str = ""
    """Stable identifier, unique within a report.

    Wilma has no mark IDs; the key combines the date, hour, type, course, teacher and name,
    and leaves out comments and clarifications so that editing those does not make a mark
    look new. It starts with the ISO date, so keys sort chronologically.
    """

    def identity(self) -> str:
        """The key without the suffix that disambiguates identical marks."""
        return "|".join(
            str(part or "")
            for part in (
                self.date.isoformat(),
                self.hour,
                self.type.id,
                self.course,
                self.teacher_code,
                self.name,
            )
        )


@dataclass
class AttendanceReport(DataClassDictMixin):
    """Marks within a date range, plus every mark type the school uses."""

    marks: List[AttendanceMark] = field(default_factory=list)
    types: List[MarkType] = field(default_factory=list)

    @property
    def latest(self) -> Optional[AttendanceMark]:
        """The mark on the latest date and hour, if there are any marks."""
        if not self.marks:
            return None
        return max(self.marks, key=lambda mark: (mark.date, mark.hour or 0))

    def marks_of_type(self, *type_ids: int) -> list[AttendanceMark]:
        """Marks whose type is one of ``type_ids``."""
        return [mark for mark in self.marks if mark.type.id in type_ids]

    def marks_with_code(self, code: str) -> list[AttendanceMark]:
        """Marks whose type has the given legend code, e.g. ``+`` for positive feedback."""
        return [mark for mark in self.marks if mark.type.code == code]
