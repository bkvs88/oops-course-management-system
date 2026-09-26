"""Academy facade, report renderers and the CLI entry points."""

from __future__ import annotations

import io
import shlex
import unittest
from contextlib import redirect_stdout

import main
from cms.academy import Academy
from cms.exceptions import UnknownUserError, ValidationError
from cms.mentor import PremiumMentor
from cms.report import Report


class TestAcademyRegistry(unittest.TestCase):
    def setUp(self) -> None:
        self.academy = Academy("Test Academy")
        self.asha = self.academy.admit_student("Asha Rao", "asha@uni.edu", "BCA", 2)
        self.mentor = self.academy.hire_mentor("Ravi Kumar", "ravi@uni.edu", rating=4.4)
        self.premium = self.academy.hire_premium_mentor("Nisha Iyer", "nisha@uni.edu")
        self.python = self.academy.offer_course(
            "Python Programming", 3, capacity=2, mentor=self.mentor
        )

    def test_lookups_by_id_and_by_name(self) -> None:
        self.assertIs(self.academy.student("Asha Rao"), self.asha)
        self.assertIs(self.academy.student(self.asha.user_id), self.asha)
        self.assertIs(self.academy.mentor("ravi kumar"), self.mentor)
        self.assertIs(self.academy.user(self.mentor.user_id), self.mentor)
        self.assertIs(self.academy.course("pp-100"), self.python)

    def test_lookup_failures(self) -> None:
        with self.assertRaises(UnknownUserError):
            self.academy.student("Nobody")
        with self.assertRaises(UnknownUserError):
            self.academy.mentor("Asha Rao")
        with self.assertRaises(UnknownUserError):
            self.academy.user("STU-9999")
        with self.assertRaises(ValidationError):
            self.academy.course("ZZZ-999")

    def test_people_contains_every_user(self) -> None:
        self.assertEqual(len(self.academy.people()), 3)
        self.assertEqual(len(self.academy.students), 1)
        self.assertEqual(len(self.academy.mentors), 2)
        self.assertTrue(isinstance(self.premium, PremiumMentor))

    def test_duplicate_course_code_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            self.academy.offer_course("Python Programming")

    def test_prerequisite_must_be_offered(self) -> None:
        with self.assertRaises(ValidationError):
            self.academy.offer_course("Advanced Thing", 3, prerequisites=("ZZZ-999",))

    def test_activity_log_records_every_action(self) -> None:
        self.academy.enroll("Asha Rao", "PP-100")
        log = "\n".join(self.academy.activity_log)
        self.assertIn("admitted Asha Rao", log)
        self.assertIn("offered PP-100", log)
        self.assertIn("Asha Rao enrolled in PP-100", log)
        self.assertTrue(self.academy.activity_log)

    def test_broadcast_targets(self) -> None:
        self.assertEqual(len(self.academy.broadcast("hi", "students")), 1)
        self.assertEqual(len(self.academy.broadcast("hi", "mentors")), 2)
        self.assertEqual(len(self.academy.broadcast("hi", "premium")), 1)
        self.assertEqual(len(self.academy.broadcast("hi", "all")), 3)
        with self.assertRaises(ValidationError):
            self.academy.broadcast("hi", "aliens")

    def test_close_registration(self) -> None:
        self.academy.close_registration("PP-100")
        self.assertFalse(self.academy.course("PP-100").is_enrollment_open)


class TestReport(unittest.TestCase):
    academy: Academy

    @classmethod
    def setUpClass(cls) -> None:
        cls.academy = main.build_populated_term()

    def test_banner_and_section(self) -> None:
        self.assertIn("ACADEMY NAME", Report.banner("Academy Name"))
        self.assertTrue(Report.section("Metrics").startswith("\nMetrics"))

    def test_table_aligns_numeric_columns(self) -> None:
        table = Report.table(("name", "score"), [("Asha", "90"), ("Bilal Khan", "7")])
        lines = table.splitlines()
        self.assertIn("NAME", lines[0])
        self.assertIn("SCORE", lines[0])
        self.assertIn("Asha", lines[2])

    def test_table_with_no_rows(self) -> None:
        self.assertIn("(empty)", Report.table(("a", "b"), []))

    def test_people_report_uses_describe(self) -> None:
        text = Report.people(self.academy)
        for user in self.academy.people():
            self.assertIn(user.user_id, text)

    def test_courses_report_columns(self) -> None:
        text = Report.courses(self.academy)
        for course in self.academy.courses:
            self.assertIn(course.code, text)
            self.assertIn(course.mentor.name if course.mentor else "unassigned", text)

    def test_toppers_are_sorted_by_gpa(self) -> None:
        ranked = Report.rank_students(self.academy.students)
        gpas = [student.gpa() for student in ranked]
        self.assertEqual(gpas, sorted(gpas, reverse=True))
        self.assertIn("RANK", Report.toppers(self.academy))

    def test_mentor_workload_is_sorted_by_rating(self) -> None:
        text = Report.mentor_workload(self.academy)
        names = [mentor.name for mentor in sorted(self.academy.mentors, reverse=True)]
        self.assertLess(text.index(names[0]), text.index(names[-1]))

    def test_dashboard_contains_every_block(self) -> None:
        dashboard = Report.dashboard(self.academy)
        for block in (
            "Key figures",
            "Course catalogue",
            "Top performers",
            "Mentor workload",
        ):
            self.assertIn(block, dashboard)
        self.assertIn("students admitted", dashboard)

    def test_aggregate_helpers(self) -> None:
        self.assertEqual(Report.average([80, 90, 70]), 80.0)
        self.assertEqual(Report.average([]), 0.0)
        self.assertEqual(Report.unassigned_courses(self.academy), ())

    def test_risk_list_flags_students_below_the_threshold(self) -> None:
        self.assertEqual(Report.risk_list(self.academy), ())
        weak_academy = Academy("Risk Academy")
        mentor = weak_academy.hire_mentor("Ravi Kumar", "ravi@uni.edu")
        course = weak_academy.offer_course("Python Programming", 3, mentor=mentor)
        weak = weak_academy.admit_student("Weak Student", "weak@uni.edu")
        healthy = weak_academy.admit_student("Healthy Student", "healthy@uni.edu")
        for learner, score in ((weak, 35), (healthy, 95)):
            weak_academy.enroll(learner, course)
            weak_academy.submit_score(learner, course, score)
            mentor.grade(course, learner, score)
        at_risk = Report.risk_list(weak_academy)
        self.assertEqual([s.name for s in at_risk], ["Weak Student"])
        self.assertLess(weak.gpa(), 5.0)

    def test_rosters_and_activity(self) -> None:
        rosters = Report.rosters(self.academy)
        for course in self.academy.courses:
            self.assertIn(course.code, rosters)
        self.assertIn("admitted", Report.activity(self.academy))


class TestEntrypoints(unittest.TestCase):
    def test_dashboard_mode_runs(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(main.main(["dashboard"]), 0)
        self.assertIn("ACADEMIC DASHBOARD", buffer.getvalue())

    def test_demo_mode_runs(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            self.assertEqual(main.main(["demo"]), 0)
        output = buffer.getvalue()
        self.assertIn("GUIDED TOUR", output)
        self.assertIn("PrerequisiteError", output)
        self.assertIn("RecordLockedError", output)

    def test_parser_defaults_to_demo(self) -> None:
        self.assertEqual(main.build_parser().parse_args([]).mode, "demo")

    def test_shell_commands(self) -> None:
        academy = main.build_populated_term()
        commands = [
            ("help", ""),
            ("students", ""),
            ("mentors", ""),
            ("courses", ""),
            ("people", ""),
            ("roster", "OOP-100"),
            ("transcript", '"Asha Rao"'),
            ("enroll", '"Harish Babu" OOP-100'),
            ("submit", '"Harish Babu" OOP-100 77'),
            ("grade", '"Ravi Kumar" "Harish Babu" OOP-100 77'),
            ("drop", '"Harish Babu" DC-100'),
            ("broadcast", "Exam schedule students"),
            ("dashboard", ""),
            ("report", ""),
            ("activity", ""),
            ("nonsense", ""),
        ]
        for command, argument_line in commands:
            with self.subTest(command=command):
                buffer = io.StringIO()
                with redirect_stdout(buffer):
                    main.handle_command(academy, command, shlex.split(argument_line))
                self.assertTrue(buffer.getvalue().strip())

    def test_shell_reports_domain_errors_instead_of_crashing(self) -> None:
        academy = main.build_populated_term()
        with self.assertRaises(UnknownUserError):
            main.handle_command(academy, "enroll", ["Ghost Student", "OOP-100"])

    def test_populated_term_is_internally_consistent(self) -> None:
        academy = main.build_populated_term()
        self.assertEqual(len(academy.students), 8)
        self.assertEqual(len(academy.mentors), 3)
        self.assertEqual(len(academy.courses), 5)
        for course in academy.courses:
            for student in course.active_students:
                self.assertTrue(student.enrolled_in(course))
                self.assertTrue(
                    all(
                        code in {c.code for c in student.completed_courses}
                        for code in course.prerequisites
                    )
                )


if __name__ == "__main__":
    unittest.main()
