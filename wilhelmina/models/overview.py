"""Exam, course, homework and lesson diary models, from a student's overview."""

import datetime
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, List, Optional

from mashumaro import DataClassDictMixin


@dataclass
class CourseTeacher(DataClassDictMixin):
    """A teacher of a course or exam."""

    id: Optional[int] = None
    name: str = ""
    code: str = ""

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "CourseTeacher":
        return cls(
            id=data.get("TeacherId"),
            name=_text(data.get("TeacherName")) or "",
            code=_text(data.get("TeacherCode")) or "",
        )


@dataclass
class Exam(DataClassDictMixin):
    """An exam of one of the student's courses, upcoming or past."""

    id: int
    """Wilma's exam ID, stable over time."""
    date: datetime.date
    subject: str = ""
    """Course title, e.g. ``Matematik``."""
    course: str = ""
    """Course caption with its code, e.g. ``ma ma05``."""
    name: str = ""
    """The exam's own name, which teachers often leave empty."""
    info: Optional[str] = None
    """What the exam covers, as the teacher wrote it."""
    grade: Optional[str] = None
    verbal_grade: Optional[str] = None
    seen: Optional[datetime.date] = None
    """When a guardian or the student marked the grade as seen in Wilma."""
    course_id: Optional[int] = None
    group_id: Optional[int] = None
    teachers: List[CourseTeacher] = field(default_factory=list)

    @property
    def graded(self) -> bool:
        """Whether the exam has a grade or a verbal assessment."""
        return bool(self.grade or self.verbal_grade)

    @property
    def teacher_names(self) -> list[str]:
        """Names of the exam's teachers."""
        return _unique(teacher.name or teacher.code for teacher in self.teachers)

    @property
    def title(self) -> str:
        """Subject, followed by the exam's name when it has one."""
        if self.name and self.name != self.subject:
            return f"{self.subject}: {self.name}" if self.subject else self.name
        return self.subject or self.course


@dataclass
class Homework(DataClassDictMixin):
    """Homework a teacher entered in a course's lesson diary."""

    date: datetime.date
    """Date of the lesson the homework was given in."""
    text: str
    row: int = 0
    """Row number within the course's diary; together with ``group_id`` it identifies the
    entry."""
    group_id: Optional[int] = None
    subject: str = ""
    course: str = ""

    @property
    def key(self) -> str:
        """Stable identity of the entry."""
        return f"{self.group_id}|{self.row}|{self.date.isoformat()}"


@dataclass
class DiaryEntry(DataClassDictMixin):
    """A lesson diary entry: what was done in a lesson."""

    date: datetime.date
    row: int = 0
    lesson: Optional[str] = None
    note: Optional[str] = None
    teacher: Optional[CourseTeacher] = None
    group_id: Optional[int] = None
    subject: str = ""
    course: str = ""


@dataclass
class Course(DataClassDictMixin):
    """A teaching group (course) the student belongs to."""

    id: int
    """Group ID."""
    name: str = ""
    """Course name, e.g. ``Matematik``."""
    code: str = ""
    """Course code, e.g. ``ma05``."""
    caption: str = ""
    """Group caption, e.g. ``ma ma05``."""
    course_id: Optional[int] = None
    start_date: Optional[datetime.date] = None
    end_date: Optional[datetime.date] = None
    committed: bool = False
    teachers: List[CourseTeacher] = field(default_factory=list)
    homework: List[Homework] = field(default_factory=list)
    """Newest first."""
    diary: List[DiaryEntry] = field(default_factory=list)
    """Newest first."""
    exams: List[Exam] = field(default_factory=list)

    @property
    def teacher_names(self) -> list[str]:
        """Names of the course's teachers."""
        return _unique(teacher.name or teacher.code for teacher in self.teachers)


@dataclass
class Overview(DataClassDictMixin):
    """A student's current courses, with their exams, homework and lesson diary."""

    courses: List[Course] = field(default_factory=list)
    exams: List[Exam] = field(default_factory=list)
    """All exams of the courses, oldest first."""

    @classmethod
    def from_api(cls, data: Mapping[str, Any]) -> "Overview":
        """Build from the ``overview`` endpoint's JSON.

        Exams are listed both on their own (with grades, seen state and teachers) and per
        course (with the exam's name and verbal grade); the two are merged by exam ID.
        """
        courses = [_parse_course(item) for item in _dicts(data.get("Groups"))]
        course_exams = {exam.id: exam for course in courses for exam in course.exams}

        exams: dict[int, Exam] = {}
        for item in _dicts(data.get("Exams")):
            exam = _parse_exam(item, course_exams.get(item.get("ExamId") or -1))
            if exam is not None:
                exams[exam.id] = exam
        # Exams only listed under their course
        for exam_id, exam in course_exams.items():
            exams.setdefault(exam_id, exam)
        for course in courses:
            course.exams = [exams[exam.id] for exam in course.exams]

        return cls(courses=courses, exams=sorted(exams.values(), key=lambda e: (e.date, e.id)))

    def upcoming_exams(self, today: datetime.date) -> list[Exam]:
        """Exams on or after ``today``, soonest first."""
        return [exam for exam in self.exams if exam.date >= today]

    def graded_exams(self) -> list[Exam]:
        """Exams with a grade or a verbal assessment, newest first."""
        return sorted(
            (exam for exam in self.exams if exam.graded),
            key=lambda e: (e.date, e.id),
            reverse=True,
        )

    @property
    def homework(self) -> list[Homework]:
        """Homework of all courses, newest first."""
        return sorted(
            (hw for course in self.courses for hw in course.homework),
            key=lambda hw: (hw.date, hw.group_id or 0, hw.row),
            reverse=True,
        )

    @property
    def diary(self) -> list[DiaryEntry]:
        """Lesson diary entries with a lesson topic or note, of all courses, newest first."""
        return sorted(
            (
                entry
                for course in self.courses
                for entry in course.diary
                if entry.lesson or entry.note
            ),
            key=lambda entry: (entry.date, entry.group_id or 0, entry.row),
            reverse=True,
        )


def _parse_course(item: Mapping[str, Any]) -> Course:
    group_id = int(item["Id"])
    subject = _text(item.get("CourseName")) or ""
    caption = _text(item.get("Caption")) or ""
    context: dict[str, Any] = {"group_id": group_id, "subject": subject, "course": caption}
    homework = [
        Homework(
            date=date,
            text=text,
            row=int(entry.get("RowNumber") or 0),
            **context,
        )
        for entry in _dicts(item.get("Homework"))
        if (date := _date(entry.get("Date"))) and (text := _text(entry.get("Homework")))
    ]
    diary = [
        DiaryEntry(
            date=date,
            row=int(entry.get("RowNumber") or 0),
            lesson=_text(entry.get("Lesson")),
            note=_text(entry.get("Note")),
            teacher=CourseTeacher.from_api(entry)
            if entry.get("TeacherId") or entry.get("TeacherName")
            else None,
            **context,
        )
        for entry in _dicts(item.get("Diary"))
        if (date := _date(entry.get("Date")))
    ]
    exams = [
        Exam(
            id=int(entry["Id"]),
            date=date,
            subject=subject,
            course=caption,
            name=_text(entry.get("Name")) or "",
            info=_text(entry.get("Info")),
            grade=_text(entry.get("Grade")),
            verbal_grade=_text(entry.get("VerbalGrade")),
            course_id=item.get("CourseId"),
            group_id=group_id,
        )
        for entry in _dicts(item.get("Exams"))
        if entry.get("Id") is not None and (date := _date(entry.get("Date")))
    ]
    return Course(
        id=group_id,
        name=subject,
        code=_text(item.get("CourseCode")) or "",
        caption=caption,
        course_id=item.get("CourseId"),
        start_date=_date(item.get("StartDate")),
        end_date=_date(item.get("EndDate")),
        committed=bool(item.get("Committed")),
        teachers=[CourseTeacher.from_api(t) for t in _dicts(item.get("Teachers"))],
        homework=sorted(homework, key=lambda hw: (hw.date, hw.row), reverse=True),
        diary=sorted(diary, key=lambda entry: (entry.date, entry.row), reverse=True),
        exams=exams,
    )


def _parse_exam(item: Mapping[str, Any], from_course: Optional[Exam]) -> Optional[Exam]:
    exam_id = item.get("ExamId")
    date = _date(item.get("Date")) or (from_course.date if from_course else None)
    if exam_id is None or date is None:
        return None
    return Exam(
        id=int(exam_id),
        date=date,
        subject=_text(item.get("CourseTitle")) or (from_course.subject if from_course else ""),
        course=_text(item.get("Course")) or (from_course.course if from_course else ""),
        name=_text(item.get("Name")) or (from_course.name if from_course else ""),
        info=_text(item.get("Info")) or (from_course.info if from_course else None),
        grade=_text(item.get("Grade")) or (from_course.grade if from_course else None),
        verbal_grade=_text(item.get("VerbalGrade"))
        or (from_course.verbal_grade if from_course else None),
        seen=_date(item.get("ExamSeen")),
        course_id=item.get("CourseId"),
        group_id=item.get("Id"),
        teachers=[CourseTeacher.from_api(t) for t in _dicts(item.get("Teachers"))],
    )


def _date(value: Any) -> Optional[datetime.date]:
    """Parse an ISO (``2026-09-24``) or Finnish (``24.9.2026``) date."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        if "." in value:
            day, month, year = (int(part) for part in value.split(".")[:3])
            return datetime.date(year, month, day)
        return datetime.date.fromisoformat(value[:10])
    except ValueError:
        return None


def _text(value: Any) -> Optional[str]:
    """Normalise teacher-entered text: unified newlines, no trailing whitespace."""
    if value is None:
        return None
    lines = str(value).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    text = "\n".join(line.rstrip() for line in lines).strip()
    return text or None


def _dicts(value: Any) -> Iterable[Mapping[str, Any]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
