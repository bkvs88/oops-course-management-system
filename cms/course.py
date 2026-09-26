"""The :class:`Course` aggregate root.

A course owns its roster, its capacity rules and its prerequisite chain. It is
the only object that is allowed to create :class:`~cms.enrollment.Enrollment`
records, which guarantees the invariants:

* no duplicate seat for the same student,
* never more students than ``capacity`` (unless a premium mentor overrides it),
* prerequisites are satisfied **before** a seat is handed out.

OOP concepts
------------
* **Encapsulation** - ``__records``/``__mentor``/``__open`` are private and the
  ``roster``/``enrollments`` properties hand out immutable snapshots.
* **Abstraction** - callers work with ``capacity``/``seats_left``/``is_full``
  instead of manipulating collections.
* **@staticmethod** - title to course-code normalisation and credit rules.
* **@classmethod** - :meth:`Course.offer` alternative constructor.
* **Polymorphism** - the roster is a list of ``Student`` objects and the mentor
  may be any ``User`` subclass, so a generic loop can publish announcements.
* **Dunder protocol** - ``len(course)``, ``for record in course`` and
  ``student in course`` all work.
"""

from __future__ import annotations

import re
import statistics
from typing import TYPE_CHECKING, ClassVar, Iterator

from cms.enrollment import Enrollment
from cms.exceptions import (
    CapacityFullError,
    DuplicateEnrollmentError,
    EnrollmentClosedError,
    PrerequisiteError,
    ValidationError,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cms.mentor import Mentor
    from cms.student import Student

__all__ = ["Course"]

_CODE_PATTERN = re.compile(r"^[A-Z]{2,4}-\d{3}$")
_STOP_WORDS = frozenset({"and", "of", "the", "for", "in", "to", "&"})


class Course:
    """A single offering of a subject with a bounded number of seats."""

    LEVELS: ClassVar[dict[int, str]] = {1: "Foundation", 2: "Intermediate", 3: "Advanced"}
    LEVEL_KEYWORDS: ClassVar[dict[int, tuple[str, ...]]] = {
        3: ("advanced", "distributed", "compiler", "machine learning"),
        2: ("intermediate", "data structure", "algorithm", "database", "web"),
    }
    MAX_CREDITS: ClassVar[int] = 6

    def __init__(
        self,
        title: str,
        credits: int = 3,
        capacity: int = 30,
        code: str | None = None,
        prerequisites: tuple[str, ...] = (),
        fee: float = 0.0,
    ) -> None:
        self.__title = self.validate_title(title)
        self.__code = self.validate_code(code or self.build_code(title))
        self.__credits = self.validate_credits(credits)
        self.__capacity = self.validate_capacity(capacity)
        self.__prerequisites = self._validate_prerequisites(prerequisites)
        self.__fee = self._validate_fee(fee)
        self.__mentor: Mentor | None = None
        self.__records: dict[str, Enrollment] = {}
        self.__open = True

    # ------------------------------------------------------------------
    # Immutable descriptors
    # ------------------------------------------------------------------
    @property
    def code(self) -> str:
        return self.__code

    @property
    def title(self) -> str:
        return self.__title

    @property
    def credits(self) -> int:
        return self.__credits

    @property
    def capacity(self) -> int:
        return self.__capacity

    @property
    def prerequisites(self) -> tuple[str, ...]:
        return self.__prerequisites

    @property
    def fee(self) -> float:
        return self.__fee

    @property
    def level(self) -> str:
        """Heuristic level derived from the title (Foundation/Intermediate/...)."""
        return self.LEVELS[self.infer_level(self.__title)]

    @staticmethod
    def infer_level(title: str) -> int:
        """Classify a course title into 1 (Foundation), 2 or 3 (Advanced)."""
        lowered = str(title).lower()
        for level in sorted(Course.LEVEL_KEYWORDS, reverse=True):
            if any(keyword in lowered for keyword in Course.LEVEL_KEYWORDS[level]):
                return level
        return 1

    @property
    def mentor(self) -> "Mentor | None":
        return self.__mentor

    # ------------------------------------------------------------------
    # Roster (encapsulated, exposed as snapshots)
    # ------------------------------------------------------------------
    @property
    def enrollments(self) -> tuple[Enrollment, ...]:
        return tuple(self.__records.values())

    @property
    def active_students(self) -> tuple["Student", ...]:
        return tuple(r.student for r in self.__records.values() if r.is_active)

    @property
    def seats_taken(self) -> int:
        return sum(1 for record in self.__records.values() if record.is_active)

    @property
    def seats_left(self) -> int:
        return self.__capacity - self.seats_taken

    @property
    def is_full(self) -> bool:
        return self.seats_taken >= self.__capacity

    @property
    def has_open_seats(self) -> bool:
        return self.seats_left > 0

    @property
    def is_enrollment_open(self) -> bool:
        return self.__open

    def is_enrolled(self, student: "Student") -> bool:
        return any(
            record.student is student and record.is_active for record in self.__records.values()
        )

    # ------------------------------------------------------------------
    # Instance methods - the aggregate behaviour
    # ------------------------------------------------------------------
    def enroll(self, student: "Student", by: "Mentor | None" = None) -> Enrollment:
        """Hand a seat to *student* and return the new enrollment record."""
        if student.role != "student":
            raise ValidationError(f"Only students can enroll, got {student.role!r}")
        if not self.__open:
            raise EnrollmentClosedError(f"{self.__code} enrollment window is closed")
        if self.is_enrolled(student):
            raise DuplicateEnrollmentError(f"{student.name} is already in {self.__code}")
        override = by is not None and by.can("override_capacity")
        if self.is_full and not override:
            raise CapacityFullError(
                f"{self.__code} is full ({self.__capacity}/{self.__capacity} seats taken)"
            )
        self._assert_prerequisites(student)
        record = Enrollment.open(student, self)
        self.__records[student.user_id] = record
        return record

    def unenroll(self, student: "Student") -> Enrollment:
        """Cancel the seat of *student* and keep the record for the audit trail."""
        record = self.__records.get(student.user_id)
        if record is None or not record.is_active:
            raise ValidationError(f"{student.name} is not enrolled in {self.__code}")
        return record.drop()

    def assign_mentor(self, mentor: "Mentor | None") -> None:
        """Attach (or detach with ``None``) the mentor responsible for the course."""
        if mentor is not None and not mentor.can("teach"):
            raise ValidationError(f"{mentor.name} is not allowed to teach")
        self.__mentor = mentor

    def grade_student(
        self, student: "Student", score: float, graded_by: "Mentor | None" = None
    ) -> Enrollment:
        """Mentor facing entry point that awards the final grade."""
        record = self.__records.get(student.user_id)
        if record is None or not record.is_active:
            raise ValidationError(f"{student.name} is not enrolled in {self.__code}")
        if graded_by is not None and not self.is_teaching(graded_by):
            raise ValidationError(f"{graded_by.name} does not teach {self.__code}")
        return record.grade(graded_by or self.__mentor, score)

    def is_teaching(self, mentor: "Mentor") -> bool:
        return self.__mentor is not None and self.__mentor is mentor

    def open_enrollment(self) -> "Course":
        self.__open = True
        return self

    def close_enrollment(self) -> "Course":
        self.__open = False
        return self

    def can_enroll(self, student: "Student") -> bool:
        """Non raising eligibility check used by the CLI."""
        try:
            self._assert_prerequisites(student)
        except PrerequisiteError:
            return False
        return (
            self.__open
            and not self.is_enrolled(student)
            and (self.has_open_seats or bool(self.__mentor and self.__mentor.can("override_capacity")))
        )

    # ------------------------------------------------------------------
    # Reporting helpers (purely derived data)
    # ------------------------------------------------------------------
    def average_score(self) -> float:
        scores = [r.score for r in self.__records.values() if r.score is not None]
        return round(statistics.fmean(scores), 2) if scores else 0.0

    def average_grade_points(self) -> float:
        points = [r.grade_points for r in self.__records.values() if r.is_graded]
        return round(statistics.fmean(points), 2) if points else 0.0

    def pass_percentage(self) -> float:
        graded = [r for r in self.__records.values() if r.is_graded]
        if not graded:
            return 0.0
        passed = [r for r in graded if r.grade_points > 0]
        return round(100 * len(passed) / len(graded), 2)

    def roster(self) -> str:
        """Human readable roster table."""
        lines = [
            f"{self.__code} | {self.__title} ({self.level})",
            f"mentor : {self.__mentor.name if self.__mentor else 'unassigned'}",
            f"seats  : {self.seats_taken}/{self.__capacity} taken | fee INR {self.__fee:,.0f}",
        ]
        if self.__prerequisites:
            lines.append(f"pre-req: {', '.join(self.__prerequisites)}")
        lines.append("-" * 68)
        if not self.__records:
            lines.append("  (no enrollments yet)")
        for index, record in enumerate(self.__records.values(), start=1):
            lines.append(
                f"  {index:>2}. {record.student.name:<18} {record.status:<10} "
                f"score={str(record.score if record.score is not None else '--'):>6} "
                f"grade={record.grade or '--'}"
            )
        lines.append("-" * 68)
        lines.append(
            f"  average score {self.average_score():.2f} | pass rate {self.pass_percentage():.1f}%"
        )
        return "\n".join(lines)

    def summary(self) -> str:
        return (
            f"{self.__code:<9} {self.__title:<34} {self.level:<13} "
            f"{self.__credits}cr  {self.seats_taken:>3}/{self.__capacity:<3} "
            f"{'OPEN' if self.__open else 'CLOSED'}"
        )

    # ------------------------------------------------------------------
    # @staticmethod - pure course catalogue rules
    # ------------------------------------------------------------------
    @staticmethod
    def build_code(title: str) -> str:
        """``'Object Oriented Programming' -> 'OOP-100'`` (acronym + level)."""
        words = [w for w in re.split(r"[^A-Za-z0-9]+", title) if w and w.lower() not in _STOP_WORDS]
        if not words:
            raise ValidationError(f"Cannot derive a course code from '{title}'")
        acronym = "".join(w[0] for w in words[:4]).upper()
        return f"{acronym}-{Course.infer_level(title) * 100}"

    @staticmethod
    def validate_code(code: str) -> str:
        if not isinstance(code, str) or not _CODE_PATTERN.match(code.strip().upper()):
            raise ValidationError(f"'{code}' is not a valid course code (expected ABC-123)")
        return code.strip().upper()

    @staticmethod
    def validate_title(title: str) -> str:
        if not isinstance(title, str) or len(title.strip()) < 4:
            raise ValidationError("Course title must be at least 4 characters long")
        return " ".join(title.split())

    @staticmethod
    def validate_credits(credits: int) -> int:
        if isinstance(credits, bool) or not isinstance(credits, int):
            raise ValidationError(f"Credits must be an integer, got {credits!r}")
        if not 1 <= credits <= Course.MAX_CREDITS:
            raise ValidationError(f"Credits must be within 1-{Course.MAX_CREDITS}, got {credits}")
        return credits

    @staticmethod
    def validate_capacity(capacity: int) -> int:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or not 1 <= capacity <= 500:
            raise ValidationError(f"Capacity must be an integer within 1-500, got {capacity!r}")
        return capacity

    @staticmethod
    def _validate_prerequisites(prerequisites: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        if isinstance(prerequisites, str):
            raise ValidationError("Prerequisites must be a sequence of course codes")
        codes = tuple(Course.validate_code(code) for code in prerequisites)
        if len(set(codes)) != len(codes):
            raise ValidationError("Duplicate prerequisite codes are not allowed")
        return codes

    @staticmethod
    def _validate_fee(fee: float) -> float:
        if isinstance(fee, bool) or not isinstance(fee, (int, float)) or fee < 0:
            raise ValidationError(f"Fee must be a non negative number, got {fee!r}")
        return float(fee)

    # ------------------------------------------------------------------
    # @classmethod - alternative constructor used by the catalogue builder
    # ------------------------------------------------------------------
    @classmethod
    def offer(
        cls,
        title: str,
        credits: int = 3,
        capacity: int = 30,
        prerequisites: tuple[str, ...] = (),
        fee: float = 0.0,
    ) -> "Course":
        """Create a course and derive its code from the title."""
        return cls(title, credits, capacity, None, prerequisites, fee)

    # ------------------------------------------------------------------
    # Dunder protocol
    # ------------------------------------------------------------------
    def __len__(self) -> int:
        return self.seats_taken

    def __iter__(self) -> Iterator[Enrollment]:
        return iter(self.__records.values())

    def __contains__(self, item: object) -> bool:
        return any(record.student is item for record in self.__records.values())

    def __str__(self) -> str:
        return self.summary()

    def __repr__(self) -> str:
        return f"<Course {self.__code} '{self.__title}' {self.seats_taken}/{self.__capacity}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Course):
            return NotImplemented
        return self.__code == other.code

    def __hash__(self) -> int:
        return hash(self.__code)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _assert_prerequisites(self, student: "Student") -> None:
        missing = [code for code in self.__prerequisites if not student.has_completed_code(code)]
        if missing:
            raise PrerequisiteError(
                f"{student.name} must complete {', '.join(missing)} before joining {self.__code}"
            )
