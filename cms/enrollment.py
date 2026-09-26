"""The :class:`Enrollment` record - the association between a student and a course.

Demonstrates
-------------
* **Encapsulation** - ``score``/``grade``/``status`` are writable only through
  intent revealing methods that enforce the state machine, so a record can never
  be graded twice or mutated after completion.
* **Abstraction** - the record hides the *how* of grading (percentage to letter,
  letter to grade points) behind a small public API.
* **@classmethod** - :meth:`Enrollment.open` is the only supported constructor,
  guaranteeing that a record always starts its life in the ``ENROLLED`` state.
* **@staticmethod** - the grading scale lives on the class, not on instances.
* **Polymorphism / duck typing** - ``student`` and ``course`` are type hinted
  but any object exposing the same read only API can be linked.
"""

from __future__ import annotations

import itertools
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from cms.exceptions import RecordLockedError, ValidationError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cms.course import Course
    from cms.mentor import Mentor
    from cms.student import Student

__all__ = ["Enrollment"]


class Enrollment:
    """A single seat of a student inside a course, with its grading state."""

    _id_counter: ClassVar[itertools.count[int]] = itertools.count(1)
    GRADE_SCALE: ClassVar[dict[str, float]] = {
        "O": 10.0,
        "A+": 9.0,
        "A": 8.0,
        "B+": 7.0,
        "B": 6.0,
        "C": 5.0,
        "P": 4.0,
        "F": 0.0,
    }
    OPEN_STATES: ClassVar[frozenset[str]] = frozenset({"ENROLLED", "SUBMITTED"})
    CLOSED_STATES: ClassVar[frozenset[str]] = frozenset({"COMPLETED", "DROPPED"})

    def __init__(
        self,
        student: "Student",
        course: "Course",
        score: float | None = None,
    ) -> None:
        self.__id = f"ENR-{next(self._id_counter):04d}"
        self.__student = student
        self.__course = course
        self.__score = None
        self.__grade: str | None = None
        self.__status = "ENROLLED"
        self.__graded_by: Mentor | None = None
        self.__created_at = datetime.now()
        self.__updated_at = self.__created_at
        if score is not None:
            self.submit_score(score)

    # ------------------------------------------------------------------
    # Read only view
    # ------------------------------------------------------------------
    @property
    def enrollment_id(self) -> str:
        return self.__id

    @property
    def student(self) -> "Student":
        return self.__student

    @property
    def course(self) -> "Course":
        return self.__course

    @property
    def credits(self) -> int:
        return self.__course.credits

    @property
    def score(self) -> float | None:
        return self.__score

    @property
    def grade(self) -> str | None:
        return self.__grade

    @property
    def status(self) -> str:
        return self.__status

    @property
    def graded_by(self) -> "Mentor | None":
        return self.__graded_by

    @property
    def created_at(self) -> datetime:
        return self.__created_at

    @property
    def is_active(self) -> bool:
        """``True`` while the record still holds a seat (ENROLLED/SUBMITTED)."""
        return self.__status in self.OPEN_STATES

    @property
    def is_completed(self) -> bool:
        return self.__status == "COMPLETED"

    @property
    def is_graded(self) -> bool:
        return self.__grade is not None

    @property
    def grade_points(self) -> float:
        """Grade points of the final letter (0.0 while still ungraded)."""
        if self.__grade is None:
            return 0.0
        return self.GRADE_SCALE[self.__grade]

    # ------------------------------------------------------------------
    # Instance methods - the state machine lives here
    # ------------------------------------------------------------------
    def submit_score(self, score: float) -> "Enrollment":
        """Student action: attach an assignment score (0-100)."""
        self._assert_open("submit a score")
        if self.__score is not None:
            raise RecordLockedError(
                f"{self.__student.name} already submitted a score for {self.__course.code}"
            )
        self.__score = self.validate_score(score)
        self.__status = "SUBMITTED"
        self.__updated_at = datetime.now()
        return self

    def grade(self, mentor: "Mentor", score: float | None = None) -> "Enrollment":
        """Mentor action: award the final letter grade and close the record."""
        self._assert_open("grade")
        if score is None and self.__score is None:
            raise ValidationError("Nothing to grade: the student has not submitted a score")
        final_score = self.__score if score is None else self.validate_score(score)
        self.__score = final_score
        self.__grade = self.letter_grade(final_score)
        self.__status = "COMPLETED"
        self.__graded_by = mentor
        self.__updated_at = datetime.now()
        return self

    def drop(self) -> "Enrollment":
        """Registry action: release the seat, keeping the audit trail."""
        if self.__status == "COMPLETED":
            raise RecordLockedError(f"{self.enrollment_id} is completed and cannot be dropped")
        self.__status = "DROPPED"
        self.__updated_at = datetime.now()
        return self

    def progress(self) -> float:
        """Percentage of the maximum score achieved (0.0 - 100.0)."""
        if self.__score is None:
            return 0.0
        return round(self.__score, 2)

    # ------------------------------------------------------------------
    # @staticmethod - the grading policy is class level knowledge
    # ------------------------------------------------------------------
    @staticmethod
    def validate_score(score: float) -> float:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValidationError(f"Score must be numeric, got {score!r}")
        if not 0 <= float(score) <= 100:
            raise ValidationError(f"Score must be within 0-100, got {score}")
        return round(float(score), 2)

    @staticmethod
    def letter_grade(percentage: float) -> str:
        """Percentage -> letter grade using the class level grading policy."""
        value = Enrollment.validate_score(percentage)
        if value >= 90:
            return "O"
        if value >= 80:
            return "A+"
        if value >= 70:
            return "A"
        if value >= 60:
            return "B+"
        if value >= 50:
            return "B"
        if value >= 40:
            return "C"
        return "F"

    @staticmethod
    def grade_description(letter: str) -> str:
        return {
            "O": "Outstanding",
            "A+": "Excellent",
            "A": "Very Good",
            "B+": "Good",
            "B": "Satisfactory",
            "C": "Average",
            "P": "Pass",
            "F": "Fail",
        }.get(str(letter).strip().upper(), "Ungraded")

    # ------------------------------------------------------------------
    # @classmethod - the only supported constructor
    # ------------------------------------------------------------------
    @classmethod
    def open(cls, student: "Student", course: "Course") -> "Enrollment":
        """Create a fresh record in the ``ENROLLED`` state."""
        if student.role != "student":
            raise ValidationError(f"Only students can be enrolled, got {student.role}")
        return cls(student, course)

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------
    def __str__(self) -> str:
        grade = self.__grade or "--"
        return (
            f"{self.enrollment_id} {self.__student.name} -> {self.__course.code} "
            f"[{self.status}] score={self.__score if self.__score is not None else '--'} "
            f"grade={grade}"
        )

    def __repr__(self) -> str:
        return f"<Enrollment {self.enrollment_id} {self.__student.user_id}->{self.__course.code}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Enrollment):
            return NotImplemented
        return (
            self.__student.user_id == other.student.user_id
            and self.__course.code == other.course.code
            and self.__status == other.status
        )

    def __hash__(self) -> int:
        return hash((self.__id, self.__status))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _assert_open(self, action: str) -> None:
        if self.__status in self.CLOSED_STATES:
            raise RecordLockedError(
                f"{self.enrollment_id} is {self.__status.lower()}; cannot {action} any more"
            )
