"""Mentor roles: :class:`Mentor` and the multi-level subclass ``PremiumMentor``.

Demonstrates
-------------
* **Inheritance** - :class:`Mentor` extends :class:`~cms.user.User` and owns the
  courses it teaches; :class:`PremiumMentor` extends :class:`Mentor` (multi-level
  inheritance) and only *adds* 1:1 mentoring capabilities.
* **Polymorphism** - both roles answer the same ``describe``/``profile``
  contract, so reports can iterate over a mixed list of users.
* **Encapsulation** - the teaching list and the office-hour calendar are
  private and mutated only through intent revealing methods.
* **Operator overloading** - ``Mentor.__lt__`` lets mentors be sorted by rating.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from cms.exceptions import RolePermissionError, ValidationError
from cms.user import User

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cms.course import Course
    from cms.enrollment import Enrollment
    from cms.student import Student

__all__ = ["Mentor", "PremiumMentor"]


class Mentor(User):
    """An instructor who owns courses, rosters and grades."""

    DEPARTMENTS: ClassVar[tuple[str, ...]] = (
        "Computer Science",
        "Mathematics",
        "Electronics",
        "Management",
    )

    def __init__(
        self,
        user_id: str,
        name: str,
        email: str,
        department: str = "Computer Science",
        rating: float = 4.5,
    ) -> None:
        super().__init__(user_id, name, email)
        self.__department = self._validate_department(department)
        self.__rating = self._validate_rating(rating)
        self.__courses: list[Course] = []

    # ------------------------------------------------------------------
    # Encapsulated state
    # ------------------------------------------------------------------
    @property
    def department(self) -> str:
        return self.__department

    @property
    def rating(self) -> float:
        return self.__rating

    @rating.setter
    def rating(self, value: float) -> None:
        self.__rating = self._validate_rating(value)

    def review(self, stars: float) -> float:
        """Move the rating towards *stars* and return the new value."""
        updated = round(0.6 * self.__rating + 0.4 * self._validate_rating(stars), 2)
        self.__rating = updated
        return updated

    @property
    def courses(self) -> tuple[Course, ...]:
        return tuple(self.__courses)

    @property
    def workload(self) -> int:
        return len(self.__courses)

    # ------------------------------------------------------------------
    # Role contract
    # ------------------------------------------------------------------
    @property
    def role(self) -> str:
        return "mentor"

    def permissions(self) -> frozenset[str]:
        return frozenset({"create_course", "teach", "grade", "view_roster"})

    def duties(self) -> str:
        return (
            f"{self.__department} mentor | {len(self.__courses)} course(s) "
            f"| rating {self.__rating:.1f}/5"
        )

    # ------------------------------------------------------------------
    # Instance behaviour
    # ------------------------------------------------------------------
    def teach(self, course: Course) -> Course:
        """Take ownership of *course* (it cannot be orphaned)."""
        if course in self.__courses:
            raise ValidationError(f"{self.name} already teaches {course.code}")
        course.assign_mentor(self)
        self.__courses.append(course)
        return course

    def release(self, course: Course) -> None:
        """Stop teaching *course* once all its seats are closed."""
        if course.has_open_seats:
            raise ValidationError(
                f"{course.code} still has {course.seats_left} open seat(s); "
                "wait for the batch to close before releasing it"
            )
        course.assign_mentor(None)
        self.__courses = [c for c in self.__courses if c is not course]

    def is_teaching(self, course: Course) -> bool:
        return any(c is course for c in self.__courses)

    def grade(self, course: Course, student: Student, score: float) -> Enrollment:
        """Grade *student* in *course*; only the assigned mentor may do this."""
        if not self.is_teaching(course):
            raise RolePermissionError(f"{self.name} does not teach {course.code}")
        if not isinstance(student, User) or student.role != "student":
            raise RolePermissionError("Only students can be graded")
        return course.grade_student(student, score, graded_by=self)

    def students(self, course: Course) -> tuple[Student, ...]:
        """Roster of *course* - resolved through the course, not duplicated."""
        if not self.is_teaching(course):
            raise RolePermissionError(f"{self.name} does not teach {course.code}")
        return course.active_students

    def override_enroll(self, student: Student, course: Course) -> Enrollment:
        """Force a seat even when the batch is full (premium mentors only).

        The permission check is polymorphic: only a role that advertises
        ``override_capacity`` in :meth:`permissions` may take this shortcut.
        """
        if not self.is_teaching(course):
            raise RolePermissionError(f"{self.name} does not teach {course.code}")
        if not self.can("override_capacity"):
            raise RolePermissionError(
                f"{self.name} ({self.role}) cannot exceed the capacity of {course.code}"
            )
        record = course.enroll(student, by=self)
        student._attach(record)
        return record

    def profile(self) -> str:
        return (
            f"{self.name} ({self.department}) | {len(self.__courses)} course(s) "
            f"| rating {self.__rating:.1f}/5"
        )

    # ------------------------------------------------------------------
    # @staticmethod validators
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_department(department: str) -> str:
        if not isinstance(department, str) or not department.strip():
            raise ValidationError("Department must be a non empty string")
        return department.strip().title()

    @staticmethod
    def _validate_rating(rating: float) -> float:
        if isinstance(rating, bool) or not isinstance(rating, int | float):
            raise ValidationError(f"Rating must be numeric, got {rating!r}")
        if not 0 <= float(rating) <= 5:
            raise ValidationError(f"Rating must be within 0-5, got {rating}")
        return round(float(rating), 2)

    # ------------------------------------------------------------------
    # @classmethod alternative constructor
    # ------------------------------------------------------------------
    @classmethod
    def appoint(
        cls, name: str, email: str, department: str = "Computer Science", rating: float = 4.5
    ) -> Mentor:
        """Factory allocating the next ``MEN-xxxx`` identifier."""
        return cls(cls.generate_id("MEN"), name, email, department, rating)

    # ------------------------------------------------------------------
    # Operator overloading: sort mentors by rating
    # ------------------------------------------------------------------
    def __lt__(self, other: Mentor) -> bool:
        if not isinstance(other, Mentor):
            return NotImplemented
        return self.__rating < other.__rating

    def __le__(self, other: Mentor) -> bool:
        if not isinstance(other, Mentor):
            return NotImplemented
        return self.__rating <= other.__rating


class PremiumMentor(Mentor):
    """Multi-level subclass: a mentor who also sells 1:1 sessions."""

    SESSION_PRICE: ClassVar[float] = 1500.0

    def __init__(
        self,
        user_id: str,
        name: str,
        email: str,
        department: str = "Computer Science",
        rating: float = 4.9,
        office_hours: dict[str, str] | None = None,
        session_fee: float = SESSION_PRICE,
    ) -> None:
        super().__init__(user_id, name, email, department, rating)
        self.__office_hours = self._normalise_hours(office_hours or {})
        self.__session_fee = self._validate_fee(session_fee)
        self.__sessions_booked = 0

    @property
    def office_hours(self) -> dict[str, str]:
        return dict(self.__office_hours)

    @property
    def session_fee(self) -> float:
        return self.__session_fee

    @property
    def sessions_booked(self) -> int:
        return self.__sessions_booked

    def add_slot(self, day: str, window: str) -> None:
        if not day.strip() or not window.strip():
            raise ValidationError("Office hour slot needs a day and a time window")
        self.__office_hours[day.strip().title()] = window.strip().upper()

    def book_session(self, student: Student, day: str) -> str:
        """Book a paid 1:1 session; only a student may be a client."""
        if not isinstance(student, User) or student.role != "student":
            raise RolePermissionError("Only students can book a mentoring session")
        slot = self.__office_hours.get(day.strip().title())
        if slot is None:
            raise ValidationError(
                f"No office hour slot for {day!r}; available: {sorted(self.__office_hours)}"
            )
        self.__sessions_booked += 1
        return (
            f"{self.name} confirmed a 1:1 session with {student.name} "
            f"on {day.strip().title()} {slot} (fee INR {self.__session_fee:,.0f})"
        )

    # ------------------------------------------------------------------
    # Overridden behaviour - the base class template stays intact
    # ------------------------------------------------------------------
    @property
    def role(self) -> str:
        return "premium mentor"

    def permissions(self) -> frozenset[str]:
        return super().permissions() | frozenset({"schedule_1on1", "override_capacity"})

    def duties(self) -> str:
        return f"{super().duties()} | premium 1:1 mentor | {self.__sessions_booked} session(s)"

    def notify(self, message: str) -> str:
        return f"[premium-priority] {self.name} :: {message}"

    def profile(self) -> str:
        return f"{super().profile()} | premium | {self.__sessions_booked} 1:1 session(s)"

    @classmethod
    def hire(
        cls,
        name: str,
        email: str,
        department: str = "Computer Science",
        session_fee: float = SESSION_PRICE,
    ) -> PremiumMentor:
        return cls(cls.generate_id("PMN"), name, email, department, 4.9, session_fee=session_fee)

    @staticmethod
    def _normalise_hours(hours: dict[str, str]) -> dict[str, str]:
        return {
            str(day).strip().title(): str(window).strip().upper() for day, window in hours.items()
        }

    @staticmethod
    def _validate_fee(fee: float) -> float:
        if isinstance(fee, bool) or not isinstance(fee, int | float) or fee <= 0:
            raise ValidationError(f"Session fee must be a positive number, got {fee!r}")
        return float(fee)
