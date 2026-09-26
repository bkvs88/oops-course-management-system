"""Course invariants and the Enrollment state machine."""

from __future__ import annotations

import unittest

from cms.academy import Academy
from cms.course import Course
from cms.enrollment import Enrollment
from cms.exceptions import (
    CapacityFullError,
    DuplicateEnrollmentError,
    EnrollmentClosedError,
    PrerequisiteError,
    RecordLockedError,
    RolePermissionError,
    ValidationError,
)
from cms.mentor import Mentor
from cms.student import Student


def lab() -> tuple[Academy, Student, Mentor, Course]:
    """Build an academy with one student, one mentor and one course."""
    academy = Academy()
    asha = academy.admit_student("Asha Rao", "asha@uni.edu")
    mentor = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
    course = academy.offer_course("Python Programming", 3, capacity=2, mentor=mentor)
    return academy, asha, mentor, course


class TestCourseConstruction(unittest.TestCase):
    def test_classmethod_offer_derives_the_code(self) -> None:
        self.assertEqual(Course.offer("Python Programming").code, "PP-100")
        self.assertEqual(Course.offer("Advanced Data Structures").code, "ADS-300")

    def test_static_helpers(self) -> None:
        self.assertEqual(Course.infer_level("Python Programming"), 1)
        self.assertEqual(Course.infer_level("Algorithm Design"), 2)
        self.assertEqual(Course.infer_level("Distributed Systems"), 3)
        self.assertEqual(Course.build_code("Database Management Systems"), "DMS-200")
        with self.assertRaises(ValidationError):
            Course.validate_code("nope")
        with self.assertRaises(ValidationError):
            Course.validate_credits(99)
        with self.assertRaises(ValidationError):
            Course.validate_capacity(0)
        with self.assertRaises(ValidationError):
            Course.validate_title("ab")

    def test_level_property(self) -> None:
        self.assertEqual(Course.offer("Python Programming").level, "Foundation")
        self.assertEqual(Course.offer("Algorithm Design").level, "Intermediate")
        self.assertEqual(Course.offer("Compiler Design").level, "Advanced")

    def test_fee_and_prerequisites_validation(self) -> None:
        with self.assertRaises(ValidationError):
            Course.offer("X Y", fee=-1)
        with self.assertRaises(ValidationError):
            Course.offer("X Y", prerequisites="PP-100")  # type: ignore[arg-type]
        with self.assertRaises(ValidationError):
            Course.offer("X Y", prerequisites=("PP-100", "PP-100"))

    def test_setters_are_encapsulated(self) -> None:
        course = Course.offer("Python Programming")
        with self.assertRaises(AttributeError):
            course.code = "XXX-100"  # type: ignore[misc]
        with self.assertRaises(AttributeError):
            course.title = "Nope"  # type: ignore[misc]


class TestEnrollmentRules(unittest.TestCase):
    def test_happy_path(self) -> None:
        academy, asha, mentor, course = lab()
        record = academy.enroll(asha, course)
        self.assertEqual(record.status, "ENROLLED")
        self.assertTrue(record.is_active)
        self.assertEqual(course.seats_taken, 1)
        self.assertEqual(len(course), 1)
        self.assertIn(asha, course)
        self.assertIs(record.course, course)
        self.assertIs(record.student, asha)
        self.assertIs(course.mentor, mentor)

    def test_duplicate_seat_is_rejected(self) -> None:
        academy, asha, _, course = lab()
        academy.enroll(asha, course)
        with self.assertRaises(DuplicateEnrollmentError):
            academy.enroll(asha, course)

    def test_capacity_is_enforced(self) -> None:
        academy, asha, _, course = lab()
        bilal = academy.admit_student("Bilal Khan", "bilal@uni.edu")
        chitra = academy.admit_student("Chitra Iyer", "chitra@uni.edu")
        academy.enroll(asha, course)
        academy.enroll(bilal, course)
        self.assertTrue(course.is_full)
        with self.assertRaises(CapacityFullError):
            academy.enroll(chitra, course)
        self.assertEqual(course.seats_left, 0)
        self.assertFalse(course.has_open_seats)

    def test_closed_batch_rejects_enrollment(self) -> None:
        academy, asha, _, course = lab()
        academy.close_registration(course.code)
        self.assertFalse(course.is_enrollment_open)
        with self.assertRaises(EnrollmentClosedError):
            academy.enroll(asha, course)
        self.assertFalse(course.can_enroll(asha))
        course.open_enrollment()
        self.assertTrue(course.can_enroll(asha))

    def test_prerequisites_must_be_completed_first(self) -> None:
        academy = Academy()
        asha = academy.admit_student("Asha Rao", "asha@uni.edu")
        bilal = academy.admit_student("Bilal Khan", "bilal@uni.edu")
        ravi = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
        oop = academy.offer_course("Object Oriented Programming", 4, 5, mentor=ravi)
        ads = academy.offer_course("Algorithm Design", 4, 5, prerequisites=(oop.code,), mentor=ravi)
        with self.assertRaises(PrerequisiteError):
            academy.enroll(bilal, ads)
        self.assertFalse(ads.can_enroll(bilal))
        academy.enroll(asha, oop)
        self.assertFalse(ads.can_enroll(asha))  # enrolled, but not completed yet
        ravi.grade(oop, asha, 95)
        self.assertTrue(ads.can_enroll(asha))
        academy.enroll(asha, ads)
        self.assertTrue(asha.has_completed_code(oop.code))

    def test_roster_relationships_stay_in_sync(self) -> None:
        academy, asha, _, course = lab()
        academy.enroll(asha, course)
        self.assertEqual(academy.course(course.code), course)
        self.assertEqual(len(academy.enrollments()), 1)
        self.assertEqual(len(asha.active_enrollments), 1)
        self.assertEqual(asha.credits_registered(), 3)
        academy.drop(asha, course)
        self.assertEqual(course.seats_taken, 0)
        self.assertEqual(len(asha.enrollments), 1)  # the audit trail is kept
        self.assertEqual(asha.enrollments[0].status, "DROPPED")

    def test_only_students_can_enroll(self) -> None:
        academy, _, ravi, course = lab()
        with self.assertRaises(ValidationError):
            course.enroll(ravi)  # type: ignore[arg-type]

    def test_unsupported_role_is_rejected_by_enrollment_factory(self) -> None:
        academy, _, ravi, course = lab()
        with self.assertRaises(ValidationError):
            Enrollment.open(ravi, course)  # type: ignore[arg-type]


class TestEnrollmentStateMachine(unittest.TestCase):
    def setUp(self) -> None:
        self.academy, self.asha, self.mentor, self.course = lab()
        self.record = self.academy.enroll(self.asha, self.course)

    def test_submit_then_grade(self) -> None:
        self.record.submit_score(78)
        self.assertEqual(self.record.status, "SUBMITTED")
        self.assertEqual(self.record.progress(), 78.0)
        self.mentor.grade(self.course, self.asha, 78)
        self.assertEqual(self.record.status, "COMPLETED")
        self.assertEqual(self.record.grade, "A")
        self.assertEqual(self.record.grade_points, 8.0)
        self.assertIs(self.record.graded_by, self.mentor)
        self.assertTrue(self.record.is_graded)
        self.assertEqual(self.asha.gpa(), 8.0)
        self.assertEqual(self.asha.academic_standing(), "Excellent")

    def test_completed_record_is_locked(self) -> None:
        self.mentor.grade(self.course, self.asha, 91)
        with self.assertRaises(RecordLockedError):
            self.record.submit_score(50)
        with self.assertRaises(RecordLockedError):
            self.academy.grade(self.mentor, self.asha, self.course, 50)
        with self.assertRaises(RecordLockedError):
            self.academy.drop(self.asha, self.course)

    def test_double_submission_is_locked(self) -> None:
        self.record.submit_score(70)
        with self.assertRaises(RecordLockedError):
            self.record.submit_score(80)

    def test_grading_without_a_score_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.record.award_grade(self.mentor)

    def test_score_bounds_are_validated(self) -> None:
        for bad in (-1, 101, "80", None, True):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.record.submit_score(bad)  # type: ignore[arg-type]

    def test_grade_policy_static_helpers(self) -> None:
        self.assertEqual(Enrollment.letter_grade(95), "O")
        self.assertEqual(Enrollment.letter_grade(82), "A+")
        self.assertEqual(Enrollment.letter_grade(72), "A")
        self.assertEqual(Enrollment.letter_grade(62), "B+")
        self.assertEqual(Enrollment.letter_grade(52), "B")
        self.assertEqual(Enrollment.letter_grade(42), "C")
        self.assertEqual(Enrollment.letter_grade(2), "F")
        self.assertEqual(Enrollment.grade_description("O"), "Outstanding")
        self.assertEqual(Enrollment.grade_description("zz"), "Ungraded")

    def test_equality_and_repr(self) -> None:
        self.assertIn("ENR-", repr(self.record))
        self.assertIn("ENROLLED", str(self.record))
        self.assertEqual(hash(self.record), hash(self.record))


class TestGradingPermissions(unittest.TestCase):
    def test_only_the_assigned_mentor_may_grade(self) -> None:
        academy, asha, ravi, course = lab()
        academy.enroll(asha, course)
        outsider = academy.hire_mentor("Nisha Iyer", "nisha@uni.edu")
        with self.assertRaises(RolePermissionError):
            outsider.grade(course, asha, 88)
        with self.assertRaises(RolePermissionError):
            outsider.students(course)

    def test_students_cannot_be_graded_as_mentors(self) -> None:
        academy, asha, ravi, course = lab()
        academy.enroll(asha, course)
        with self.assertRaises(RolePermissionError):
            ravi.grade(course, ravi, 88)  # type: ignore[arg-type]

    def test_release_requires_a_concluded_batch(self) -> None:
        academy, asha, ravi, course = lab()
        academy.enroll(asha, course)
        self.assertFalse(course.is_concluded)
        with self.assertRaises(ValidationError):
            ravi.release(course)
        ravi.grade(course, asha, 88)
        self.assertTrue(course.is_concluded)
        ravi.release(course)
        self.assertIsNone(course.mentor)
        self.assertEqual(ravi.workload, 0)


class TestPremiumOverride(unittest.TestCase):
    def test_premium_mentor_can_exceed_capacity(self) -> None:
        academy = Academy()
        asha = academy.admit_student("Asha Rao", "asha@uni.edu")
        bilal = academy.admit_student("Bilal Khan", "bilal@uni.edu")
        premium = academy.hire_premium_mentor("Nisha Iyer", "nisha@uni.edu")
        tight = academy.offer_course("Python Programming", 3, capacity=1, mentor=premium)
        academy.enroll(asha, tight)
        with self.assertRaises(CapacityFullError):
            academy.enroll(bilal, tight)
        record = premium.override_enroll(bilal, tight)
        self.assertTrue(record.is_active)
        self.assertEqual(tight.seats_taken, 2)
        self.assertEqual(tight.seats_left, -1)
        self.assertTrue(bilal.enrolled_in(tight))

    def test_regular_mentor_cannot_override(self) -> None:
        academy = Academy()
        bilal = academy.admit_student("Bilal Khan", "bilal@uni.edu")
        plain = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
        tight = academy.offer_course("Python Programming", 3, capacity=0 + 1, mentor=plain)
        with self.assertRaises(RolePermissionError):
            plain.override_enroll(bilal, tight)


class TestAnalytics(unittest.TestCase):
    def test_course_aggregates(self) -> None:
        academy = Academy()
        mentor = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
        course = academy.offer_course("Python Programming", 3, capacity=5, mentor=mentor)
        for index, (name, score) in enumerate(
            [("Asha Rao", 95), ("Bilal Khan", 72), ("Chitra Iyer", 30)], start=1
        ):
            student = academy.admit_student(name, f"s{index}@uni.edu")
            academy.enroll(student, course)
            academy.submit_score(student, course, score)
            mentor.grade(course, student, score)
        self.assertEqual(course.average_score(), 65.67)
        self.assertEqual(course.average_grade_points(), 6.0)
        self.assertEqual(course.pass_percentage(), 66.67)
        self.assertIn("Asha Rao", course.roster())
        self.assertIn("average score 65.67", course.roster())
        self.assertIn("PP-100", course.summary())

    def test_student_gpa_and_transcript(self) -> None:
        academy = Academy()
        mentor = academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
        asha = academy.admit_student("Asha Rao", "asha@uni.edu")
        python = academy.offer_course("Python Programming", 3, mentor=mentor)
        oop = academy.offer_course("Object Oriented Programming", 4, mentor=mentor)
        for course, score in ((python, 95), (oop, 65)):
            academy.enroll(asha, course)
            academy.submit_score(asha, course, score)
            mentor.grade(course, asha, score)
        self.assertEqual(asha.gpa(), 8.5)
        transcript = asha.transcript()
        self.assertIn("PP-100", transcript)
        self.assertIn("OOP-100", transcript)
        self.assertIn("GPA: 8.50", transcript)
        self.assertEqual(len(asha.completed_courses), 2)


if __name__ == "__main__":
    unittest.main()
