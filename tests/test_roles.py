"""Inheritance and polymorphism across the ``User`` hierarchy."""

from __future__ import annotations

import unittest

from cms.academy import Academy
from cms.course import Course
from cms.enrollment import Enrollment
from cms.exceptions import RolePermissionError, ValidationError
from cms.mentor import Mentor, PremiumMentor
from cms.student import Student
from cms.user import User


def build_academy() -> tuple[Academy, Student, Mentor, PremiumMentor, Course]:
    """Build a small academy with one student per role and one course."""
    academy = Academy()
    asha = academy.admit_student("Asha Rao", "asha@uni.edu")
    academy.admit_student("Bilal Khan", "bilal@uni.edu")
    ravi = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu", "Computer Science", 4.6)
    nisha = academy.hire_premium_mentor("Nisha Iyer", "nisha@uni.edu", "Mathematics", 4.9)
    nisha.add_slot("Monday", "10:00-12:00")
    oop = academy.offer_course(
        "Object Oriented Programming", credits=4, capacity=1, fee=1500, mentor=ravi
    )
    asha.enroll(oop)
    return academy, asha, ravi, nisha, oop


class TestInheritance(unittest.TestCase):
    def test_roles_inherit_from_user(self) -> None:
        academy, asha, ravi, nisha, _ = build_academy()
        self.assertIsInstance(asha, User)
        self.assertIsInstance(ravi, User)
        self.assertIsInstance(nisha, User)

    def test_premium_mentor_is_a_multi_level_subclass(self) -> None:
        _, _, ravi, nisha, _ = build_academy()
        self.assertTrue(issubclass(PremiumMentor, Mentor))
        self.assertTrue(issubclass(Mentor, User))
        self.assertIsInstance(nisha, Mentor)
        self.assertNotIsInstance(ravi, PremiumMentor)

    def test_inherited_constructor_behaviour(self) -> None:
        academy, asha, _, _, _ = build_academy()
        self.assertEqual(asha.email, "asha@uni.edu")
        self.assertEqual(academy.user(asha.user_id), asha)
        self.assertTrue(asha.created_at <= academy.user(asha.user_id).created_at)


class TestPolymorphism(unittest.TestCase):
    def test_role_and_duties_are_overridden(self) -> None:
        _, asha, ravi, nisha, _ = build_academy()
        self.assertEqual(asha.role, "student")
        self.assertEqual(ravi.role, "mentor")
        self.assertEqual(nisha.role, "premium mentor")
        self.assertIn("year of", asha.duties())
        self.assertIn("rating", ravi.duties())
        self.assertIn("premium", nisha.duties())

    def test_template_method_keeps_one_layout(self) -> None:
        _, asha, ravi, nisha, _ = build_academy()
        for user in (asha, ravi, nisha):
            with self.subTest(role=user.role):
                line = user.describe()
                self.assertTrue(line.startswith(f"[{user.role.upper():<15}]"))
                self.assertIn(user.user_id, line)
                self.assertIn(user.duties(), line)

    def test_notify_is_overridden_by_premium_mentor(self) -> None:
        _, asha, ravi, nisha, _ = build_academy()
        self.assertIn("[student]", asha.notify("hi"))
        self.assertIn("[mentor]", ravi.notify("hi"))
        self.assertIn("[premium-priority]", nisha.notify("hi"))

    def test_one_loop_handles_every_user(self) -> None:
        academy, *_ = build_academy()
        rendered = {user.role for user in academy.people()}
        self.assertEqual(rendered, {"student", "mentor", "premium mentor"})
        for line in academy.broadcast("exam schedule", audience="all"):
            self.assertIn("exam schedule", line)
        self.assertEqual(len(academy.broadcast("x", audience="all")), 4)

    def test_permissions_differ_per_role(self) -> None:
        _, asha, ravi, nisha, _ = build_academy()
        self.assertTrue(asha.can("enroll"))
        self.assertFalse(asha.can("grade"))
        self.assertTrue(ravi.can("grade"))
        self.assertFalse(ravi.can("override_capacity"))
        self.assertTrue(nisha.can("override_capacity"))

    def test_subclass_extends_permission_set(self) -> None:
        mentor = Mentor("MEN-1", "Ravi Kumar", "ravi@uni.edu")
        premium = PremiumMentor("PMN-1", "Nisha Iyer", "nisha@uni.edu")
        self.assertTrue(premium.permissions() >= mentor.permissions())
        self.assertIn("schedule_1on1", premium.permissions())

    def test_profile_is_polymorphic(self) -> None:
        _, asha, ravi, nisha, _ = build_academy()
        self.assertIn("GPA", asha.profile())
        self.assertIn("rating", ravi.profile())
        self.assertIn("premium", nisha.profile())


class TestStudentBehaviour(unittest.TestCase):
    def test_grade_helpers_are_static(self) -> None:
        self.assertEqual(Student.letter_grade(95), "O")
        self.assertEqual(Student.letter_grade(85), "A+")
        self.assertEqual(Student.letter_grade(75), "A")
        self.assertEqual(Student.letter_grade(45), "C")
        self.assertEqual(Student.letter_grade(10), "F")
        self.assertEqual(Student.grade_points("A+"), 9.0)

    def test_grade_policy_is_shared_with_enrollment(self) -> None:
        self.assertIs(Student.GRADE_TABLE, Enrollment.GRADE_SCALE)
        self.assertEqual(Student.letter_grade(92), Enrollment.letter_grade(92))

    def test_promote_and_standing(self) -> None:
        student = Student("STU-1", "Asha Rao", "asha@uni.edu", year=3)
        self.assertEqual(student.promote(), 4)
        self.assertEqual(student.academic_standing(), "Not graded yet")
        with self.assertRaises(ValidationError):
            student.promote()

    def test_transcript_of_an_empty_student(self) -> None:
        student = Student("STU-1", "Asha Rao", "asha@uni.edu")
        self.assertIn("no enrollments", student.transcript())


class TestMentorBehaviour(unittest.TestCase):
    def test_rating_validation_and_review(self) -> None:
        mentor = Mentor("MEN-1", "Ravi Kumar", "ravi@uni.edu", rating=4.0)
        self.assertEqual(mentor.review(5.0), 4.4)
        with self.assertRaises(ValidationError):
            mentor.rating = 9

    def test_sorting_mentors_by_rating_uses_dunder(self) -> None:
        low = Mentor("MEN-1", "Low Rated", "low@uni.edu", rating=3.0)
        high = Mentor("MEN-2", "High Rated", "high@uni.edu", rating=4.8)
        self.assertEqual([m.name for m in sorted([low, high])], ["Low Rated", "High Rated"])
        self.assertEqual(sorted([low, high], reverse=True)[0].name, "High Rated")
        self.assertTrue(low <= high)
        self.assertFalse(high < low)

    def test_premium_session_booking(self) -> None:
        _, asha, _, nisha, _ = build_academy()
        bilal = Student("STU-9", "Bilal Khan", "bilal@uni.edu")
        message = nisha.book_session(bilal, "monday")
        self.assertIn("Bilal Khan", message)
        self.assertIn("1,500", message)
        self.assertEqual(nisha.sessions_booked, 1)
        with self.assertRaises(ValidationError):
            nisha.book_session(bilal, "Sunday")

    def test_premium_session_rejects_non_students(self) -> None:
        _, _, ravi, nisha, _ = build_academy()
        with self.assertRaises(RolePermissionError):
            nisha.book_session(ravi, "Monday")  # type: ignore[arg-type]

    def test_workload_and_teaching_queries(self) -> None:
        academy, _, ravi, nisha, oop = build_academy()
        self.assertEqual(ravi.workload, 1)
        self.assertTrue(ravi.is_teaching(oop))
        self.assertEqual(len(ravi.students(oop)), 1)
        self.assertEqual(nisha.workload, 0)
        self.assertEqual(academy.mentor("ravi kumar"), ravi)

    def test_cannot_teach_the_same_course_twice(self) -> None:
        _, _, ravi, _, oop = build_academy()
        with self.assertRaises(ValidationError):
            ravi.teach(oop)


if __name__ == "__main__":
    unittest.main()
