"""The :class:`Academy` facade - a tiny in-memory registry/service layer.

The academy is the only object the CLI talks to. It keeps private indexes of
students, mentors and courses and exposes intention revealing operations. It is
also the best place to show **polymorphism in action**: a single method such as
:meth:`Academy.broadcast` or :meth:`Academy.people` walks a heterogeneous
collection of ``Student``/``Mentor``/``PremiumMentor`` objects and lets each
object decide how it presents itself.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, ClassVar

from cms.course import Course
from cms.exceptions import UnknownUserError, ValidationError
from cms.mentor import Mentor, PremiumMentor
from cms.student import Student
from cms.user import User

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cms.enrollment import Enrollment

__all__ = ["Academy"]


class Academy:
    """Registry + service layer in front of the domain model."""

    INSTITUTION: ClassVar[str] = "Euron Institute of Technology"

    def __init__(self, name: str = INSTITUTION) -> None:
        self.__name = name
        self.__students: dict[str, Student] = {}
        self.__mentors: dict[str, Mentor] = {}
        self.__courses: dict[str, Course] = {}
        self.__activity: list[str] = []

    # ------------------------------------------------------------------
    # Read only accessors
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        return self.__name

    @property
    def students(self) -> tuple[Student, ...]:
        return tuple(self.__students.values())

    @property
    def mentors(self) -> tuple[Mentor, ...]:
        return tuple(self.__mentors.values())

    @property
    def courses(self) -> tuple[Course, ...]:
        return tuple(self.__courses.values())

    @property
    def activity_log(self) -> tuple[str, ...]:
        return tuple(self.__activity)

    def people(self) -> tuple[User, ...]:
        """Every user of the academy in one polymorphic collection."""
        return (*self.students, *self.mentors)

    def user(self, user_id: str) -> User:
        key = user_id.strip().upper()
        for registry in (self.__students, self.__mentors):
            if key in registry:
                return registry[key]
        raise UnknownUserError(f"No user registered with id '{user_id}'")

    def student(self, name_or_id: str) -> Student:
        found = self.__find(self.__students, name_or_id)
        if not isinstance(found, Student):
            raise UnknownUserError(f"'{name_or_id}' is not a student")
        return found

    def mentor(self, name_or_id: str) -> Mentor:
        found = self.__find(self.__mentors, name_or_id)
        if not isinstance(found, Mentor):
            raise UnknownUserError(f"'{name_or_id}' is not a mentor")
        return found

    def course(self, code: str) -> Course:
        key = self.__normalise_code(code)
        if key not in self.__courses:
            raise ValidationError(f"Course '{code}' is not offered this term")
        return self.__courses[key]

    def enrollments(self) -> tuple[Enrollment, ...]:
        return tuple(record for course in self.courses for record in course)

    # ------------------------------------------------------------------
    # Registry operations
    # ------------------------------------------------------------------
    def admit_student(
        self, name: str, email: str, program: str = "BSc Computer Science", year: int = 1
    ) -> Student:
        student = Student.register(name, email, program)
        student.year = year
        self.__students[student.user_id] = student
        self._log(f"admitted {student.name} ({student.user_id})")
        return student

    def hire_mentor(
        self, name: str, email: str, department: str = "Computer Science", rating: float = 4.5
    ) -> Mentor:
        mentor = Mentor.appoint(name, email, department, rating)
        self.__register_mentor(mentor)
        return mentor

    def hire_premium_mentor(
        self, name: str, email: str, department: str = "Computer Science", rating: float = 4.9
    ) -> PremiumMentor:
        mentor = PremiumMentor.hire(name, email, department)
        mentor.rating = rating
        self.__register_mentor(mentor)
        return mentor

    def offer_course(
        self,
        title: str,
        credits: int = 3,
        capacity: int = 30,
        prerequisites: Iterable[str] = (),
        fee: float = 0.0,
        mentor: Mentor | str | None = None,
    ) -> Course:
        """Create a course, resolve its prerequisites and attach a mentor."""
        codes = tuple(self.__normalise_code(code) for code in prerequisites)
        for code in codes:
            if code not in self.__courses:
                raise ValidationError(f"Prerequisite '{code}' is not offered this term")
        course = Course.offer(title, credits, capacity, codes, fee)
        if course.code in self.__courses:
            raise ValidationError(f"Course code '{course.code}' is already in use")
        if mentor is not None:
            if isinstance(mentor, str):
                mentor = self.mentor(mentor)
            mentor.teach(course)
        self.__courses[course.code] = course
        self._log(f"offered {course.code} '{course.title}' ({course.credits} cr, {capacity} seats)")
        return course

    def close_registration(self, code: str) -> Course:
        course = self.course(code)
        course.close_enrollment()
        self._log(f"closed enrollment for {course.code}")
        return course

    # ------------------------------------------------------------------
    # Cross-entity operations
    # ------------------------------------------------------------------
    def enroll(self, student: Student | str, course: Course | str) -> Enrollment:
        who = self.student(student) if isinstance(student, str) else student
        what = self.course(course) if isinstance(course, str) else course
        record = who.enroll(what)
        self._log(f"{who.name} enrolled in {what.code}")
        return record

    def drop(self, student: Student | str, course: Course | str) -> Enrollment:
        who = self.student(student) if isinstance(student, str) else student
        what = self.course(course) if isinstance(course, str) else course
        record = who.drop(what)
        self._log(f"{who.name} dropped {what.code}")
        return record

    def submit_score(
        self, student: Student | str, course: Course | str, score: float
    ) -> Enrollment:
        who = self.student(student) if isinstance(student, str) else student
        what = self.course(course) if isinstance(course, str) else course
        record = who.submit_score(what, score)
        self._log(f"{who.name} submitted a score for {what.code}")
        return record

    def grade(
        self, mentor: Mentor | str, student: Student | str, course: Course | str, score: float
    ) -> Enrollment:
        who = self.mentor(mentor) if isinstance(mentor, str) else mentor
        learner = self.student(student) if isinstance(student, str) else student
        what = self.course(course) if isinstance(course, str) else course
        record = who.grade(what, learner, score)
        self._log(f"{who.name} graded {learner.name} in {what.code}: {record.grade}")
        return record

    def broadcast(self, message: str, audience: str = "all") -> tuple[str, ...]:
        """Send *message* to a group of users - one polymorphic call, many shapes."""
        targets = self.__audience(audience)
        if not targets:
            raise ValidationError(f"Unknown audience '{audience}'")
        sent = tuple(user.notify(f"{message} [{audience}]") for user in targets)
        self._log(f"broadcast to {len(sent)} {audience} recipient(s): {message}")
        return sent

    def __audience(self, audience: str) -> tuple[User, ...]:
        key = audience.strip().lower()
        match key:
            case "all" | "everyone":
                return self.people()
            case "students":
                return self.students
            case "mentors" | "faculty":
                return self.mentors
            case "premium":
                return tuple(m for m in self.mentors if isinstance(m, PremiumMentor))
        return ()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def __register_mentor(self, mentor: Mentor) -> None:
        self.__mentors[mentor.user_id] = mentor
        self._log(f"appointed {mentor.name} as {mentor.role} ({mentor.user_id})")

    def _log(self, message: str) -> None:
        self.__activity.append(message)

    @staticmethod
    def __normalise_code(code: str) -> str:
        return str(code).strip().upper()

    @staticmethod
    def __find(registry: Mapping[str, User], token: str) -> User | None:
        key = str(token).strip().upper()
        if key in registry:
            return registry[key]
        lowered = str(token).strip().lower()
        for user in registry.values():
            if user.name.lower() == lowered:
                return user
        return None
