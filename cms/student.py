"""Concrete ``Student`` role.

Demonstrates
-------------
* **Inheritance** - ``Student`` reuses identity handling from the abstract
  :class:`~cms.user.User` and only adds academic state.
* **Encapsulation** - the enrollment list is private; it can only grow or
  shrink through :meth:`Student.enroll` / :meth:`Student.drop`, which keeps the
  course and the student sides of the object graph consistent.
* **Polymorphism** - ``duties``/``permissions`` satisfy the abstract contract so
  the same loop can treat students and mentors uniformly.
* **@staticmethod / @classmethod** - grading helpers and the ``register`` factory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cms.exceptions import ValidationError
from cms.user import User

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids a circular import
    from cms.course import Course
    from cms.enrollment import Enrollment

__all__ = ["Student"]


class Student(User):
    """A learner who can enroll in courses and earn credit."""

    MAX_CREDITS: ClassVar[int] = 24
    GRADE_TABLE: ClassVar[dict[str, float]] = {
        "O": 10.0,
        "A+": 9.0,
        "A": 8.0,
        "B+": 7.0,
        "B": 6.0,
        "C": 5.0,
        "P": 4.0,
        "F": 0.0,
    }
    STANDING_BANDS: ClassVar[tuple[tuple[float, str], ...]] = (
        (9.0, "Outstanding"),
        (8.0, "Excellent"),
        (6.5, "Good"),
        (5.0, "Average"),
        (0.0, "Needs Improvement"),
    )

    def __init__(
        self,
        user_id: str,
        name: str,
        email: str,
        program: str = "BSc Computer Science",
        year: int = 1,
    ) -> None:
        super().__init__(user_id, name, email)
        self.__program = self._validate_program(program)
        self.__year = self._validate_year(year)
        self.__enrollments: list[Enrollment] = []

    # ------------------------------------------------------------------
    # Encapsulated academic state
    # ------------------------------------------------------------------
    @property
    def program(self) -> str:
        return self.__program

    @property
    def year(self) -> int:
        return self.__year

    @year.setter
    def year(self, value: int) -> None:
        self.__year = self._validate_year(value)

    def promote(self) -> int:
        """Advance the student to the next academic year."""
        if self.__year >= 4:
            raise ValidationError(f"{self.name} has already reached the final year")
        self.__year += 1
        return self.__year

    @property
    def enrollments(self) -> tuple["Enrollment", ...]:
        """Read only view of the enrollment records (defensive copy)."""
        return tuple(self.__enrollments)

    @property
    def active_enrollments(self) -> tuple["Enrollment", ...]:
        return tuple(e for e in self.__enrollments if e.is_active)

    @property
    def completed_courses(self) -> tuple["Course", ...]:
        return tuple(e.course for e in self.__enrollments if e.is_completed)

    # ------------------------------------------------------------------
    # Role contract
    # ------------------------------------------------------------------
    @property
    def role(self) -> str:
        return "student"

    def permissions(self) -> frozenset[str]:
        return frozenset({"enroll", "drop", "submit_score", "view_transcript"})

    def duties(self) -> str:
        return f"{self._ordinal(self.__year)} year of {self.__program}"

    # ------------------------------------------------------------------
    # Instance behaviour
    # ------------------------------------------------------------------
    def enroll(self, course: "Course") -> "Enrollment":
        """Join *course*; the course object owns validation and creation."""
        enrollment = course.enroll(self)
        self.__enrollments.append(enrollment)
        return enrollment

    def drop(self, course: "Course") -> "Enrollment":
        """Leave *course*.

        The cancelled record stays on the transcript, only the active seat is
        released, which mirrors how a real registry behaves.
        """
        return course.unenroll(self)

    def submit_score(self, course: "Course", score: float) -> "Enrollment":
        """Hand in an assignment score; the mentor still has to grade it."""
        return self._enrollment_for(course).submit_score(score)

    def enrolled_in(self, course: "Course") -> bool:
        return any(e.course is course and e.is_active for e in self.__enrollments)

    def has_completed(self, course: "Course") -> bool:
        """Prerequisite check used by :class:`~cms.course.Course`."""
        return any(e.course.code == course.code and e.is_completed for e in self.__enrollments)

    def credits_registered(self) -> int:
        return sum(e.course.credits for e in self.active_enrollments)

    def gpa(self) -> float:
        """Grade point average over graded records (0.0 when there are none)."""
        graded = self.graded_records
        if not graded:
            return 0.0
        return round(sum(e.grade_points for e in graded) / len(graded), 2)

    @property
    def graded_records(self) -> tuple["Enrollment", ...]:
        return tuple(e for e in self.__enrollments if e.grade is not None)

    def academic_standing(self) -> str:
        """Map the GPA onto a qualitative band."""
        if not self.graded_records:
            return "Not graded yet"
        current = self.gpa()
        for threshold, label in self.STANDING_BANDS:
            if current >= threshold:
                return label
        return "Unclassified"

    def profile(self) -> str:
        """Polymorphic summary line used by the report writers."""
        return (
            f"{self.name} ({self.program}, year {self.year}) "
            f"| GPA {self.gpa():.2f} | {self.academic_standing()} "
            f"| active {len(self.active_enrollments)}"
        )

    def transcript(self) -> str:
        if not self.__enrollments:
            return f"Transcript for {self.name}: no enrollments"
        lines = [f"Transcript for {self.name} ({self.user_id})", "-" * 62]
        for record in self.__enrollments:
            lines.append(
                f"{record.course.code:<10} {record.course.title:<28} "
                f"{record.credits:>3}cr  {str(record.grade or '--'):<3} {record.status}"
            )
        lines.append("-" * 62)
        lines.append(f"GPA: {self.gpa():.2f}   Standing: {self.academic_standing()}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # @staticmethod helpers (no instance state involved)
    # ------------------------------------------------------------------
    @staticmethod
    def letter_grade(percentage: float) -> str:
        """Convert a score percentage into a letter grade."""
        if not 0 <= percentage <= 100:
            raise ValidationError(f"Score percentage must be within 0-100, got {percentage}")
        if percentage >= 90:
            return "O"
        if percentage >= 80:
            return "A+"
        if percentage >= 70:
            return "A"
        if percentage >= 60:
            return "B+"
        if percentage >= 50:
            return "B"
        if percentage >= 40:
            return "C"
        return "F"

    @staticmethod
    def grade_points(letter: str) -> float:
        """Reverse lookup used when a mentor records a letter grade."""
        try:
            return Student.GRADE_TABLE[str(letter).strip().upper()]
        except KeyError as exc:
            raise ValidationError(f"Unknown grade '{letter}'") from exc

    @staticmethod
    def _validate_program(program: str) -> str:
        if not isinstance(program, str) or not program.strip():
            raise ValidationError("Program must be a non empty string")
        return " ".join(program.split())

    @staticmethod
    def _validate_year(year: int) -> int:
        if not isinstance(year, int) or isinstance(year, bool) or not 1 <= year <= 4:
            raise ValidationError(f"Year must be an integer between 1 and 4, got {year!r}")
        return year

    @staticmethod
    def _ordinal(year: int) -> str:
        return {1: "1st", 2: "2nd", 3: "3rd"}.get(year, "final")

    # ------------------------------------------------------------------
    # @classmethod alternative constructor
    # ------------------------------------------------------------------
    @classmethod
    def register(cls, name: str, email: str, program: str = "BSc Computer Science") -> "Student":
        """Factory that allocates the next ``STU-xxxx`` id automatically."""
        return cls(cls.generate_id("STU"), name, email, program)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _enrollment_for(self, course: "Course") -> "Enrollment":
        for record in self.__enrollments:
            if record.course is course and record.is_active:
                return record
        raise ValidationError(f"{self.name} is not enrolled in {course.code}")
