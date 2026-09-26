#!/usr/bin/env python3
"""Course Management System - runnable demo.

Usage::

    python3 main.py demo        # scripted end-to-end showcase (default)
    python3 main.py dashboard   # populate a term and print the dashboard
    python3 main.py shell       # interactive command shell
    python3 main.py --help      # all options

Everything happens in memory - no database, no third party packages.
"""

from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Callable
from typing import Any

from cms.academy import Academy
from cms.exceptions import CMSError
from cms.report import Report
from cms.student import Student

LINE = "=" * 78


# ----------------------------------------------------------------------
# Scenario 1: the scripted demonstration
# ----------------------------------------------------------------------
def run_demo() -> None:
    """Run the guided, end-to-end tour of every OOP feature."""
    academy = Academy()
    print(Report.banner(f"{academy.name} - guided tour"))

    section("1. Users are created through @classmethod factories")
    learners = (
        ("Asha Rao", "BSc Computer Science", 2),
        ("Bilal Khan", "BSc Computer Science", 2),
        ("Chitra Iyer", "BCA", 1),
        ("Deepak Nair", "BSc Computer Science", 3),
    )
    asha, bilal, chitra, deepak = (
        academy.admit_student(name, f"{name.split()[0].lower()}@eurotech.edu", program, year)
        for name, program, year in learners
    )
    ravi = academy.hire_mentor("Ravi Kumar", "ravi.kumar@eurotech.edu", "Computer Science", 4.6)
    nisha = academy.hire_premium_mentor("Nisha Iyer", "nisha.iyer@eurotech.edu", "Mathematics", 4.9)
    nisha.add_slot("Monday", "10:00-12:00")
    nisha.add_slot("Thursday", "16:00-17:00")
    print(Report.people(academy))

    section("2. A mentor offers the catalogue (Course.offer derives the code)")
    oop = academy.offer_course(
        "Object Oriented Programming",
        credits=4,
        capacity=3,
        fee=1500,
        mentor=ravi,
    )
    ads = academy.offer_course(
        "Advanced Data Structures",
        credits=4,
        capacity=2,
        prerequisites=(oop.code,),
        mentor=nisha,
    )
    dbms = academy.offer_course("Database Management Systems", 3, capacity=25, mentor=ravi)
    print(Report.courses(academy))

    section("3. Enrollment validates every rule of the registry")
    for learner in (asha, bilal, chitra):
        academy.enroll(learner, oop)
    show("duplicate enrollment is rejected", lambda: academy.enroll(asha, oop))
    show(f"{deepak.name} skips the {oop.code} prerequisite", lambda: academy.enroll(deepak, ads))
    show(f"{oop.code} is full", lambda: academy.enroll(deepak, oop))

    section("4. Students submit work, mentors award grades (state machine)")
    for learner, score in ((asha, 93), (bilal, 78), (chitra, 64)):
        academy.submit_score(learner, oop, score)
        record = academy.grade(ravi, learner, oop, score)
        print(
            f"  {learner.name:<12} score={record.score:<6} grade={record.grade} "
            f"({RecordWords.of(record.grade)})"
        )
    show("a completed record cannot be re-graded", lambda: academy.grade(ravi, asha, oop, 50))

    section("5. Prerequisites unlock, premium mentors may exceed capacity")
    academy.enroll(asha, ads)
    print(f"  {asha.name} completed {oop.code} -> may now join {ads.code}")
    academy.enroll(bilal, ads)
    show(f"{ads.code} is full", lambda: academy.enroll(chitra, ads))
    nisha.override_enroll(chitra, ads)
    print(f"  {nisha.name} (premium) overrode the seat limit of {ads.code}")
    academy.enroll(deepak, dbms)
    nisha.book_session(bilal, "monday")
    not_a_student: Any = ravi
    try:
        nisha.book_session(not_a_student, "Monday")
    except CMSError as exc:
        print(f"  rejected: {exc}")

    section("6. Dropping frees the seat but keeps the audit trail")
    dropped = academy.drop(chitra, ads)
    print(f"  {dropped.enrollment_id} -> {dropped.status}")
    print(f"  seats left in {ads.code}: {ads.seats_left} (the transcript keeps the record)")

    section("7. One call, many behaviours (polymorphism)")
    for line in academy.broadcast("Mid-term examination schedule is published", audience="all"):
        print(f"  {line}")

    section("8. Reports are built from @staticmethod renderers")
    print(Report.rosters(academy))
    print(Report.section("Transcripts"))
    print(asha.transcript())
    print()
    print(chitra.transcript())

    section("9. Every domain error derives from CMSError")
    for label, action in (
        ("invalid e-mail", lambda: Student.register("Ghost User", "not-an-email")),
        ("bad year", lambda: academy.admit_student("Rogue Student", "rogue@eurotech.edu", year=9)),
        ("unknown user", lambda: academy.student("Nobody")),
        ("closed batch", lambda: closed_batch(academy)),
        ("unknown grade", lambda: Student.grade_points("Z")),
    ):
        try:
            action()
        except CMSError as exc:
            print(f"  {label:<14} -> {type(exc).__name__}: {exc}")

    print(Report.dashboard(academy))
    print(Report.section("Activity log"))
    print(Report.activity(academy))
    print(f"\n{LINE}\nDemo finished - every line above came from the OOP model in cms/.\n{LINE}")


class RecordWords:
    """Tiny helper so the demo can print a human label for a grade letter."""

    LETTERS = {"O": "Outstanding", "A+": "Excellent", "A": "Very Good", "B+": "Good"}

    @classmethod
    def of(cls, letter: str | None) -> str:
        return cls.LETTERS.get(str(letter), "see grading policy")


def show(expectation: str, action: Callable[[], object]) -> None:
    """Run *action*, expecting the domain to reject it, and print the rejection."""
    try:
        action()
    except CMSError as exc:
        print(f"  blocked: {expectation}")
        print(f"           {type(exc).__name__}: {exc}")
    else:
        print(f"  UNEXPECTED: {expectation} was allowed")


def closed_batch(academy: Academy) -> None:
    """Offer a course, close its registration window, then try to enroll."""
    lab = academy.offer_course("Software Testing Lab", 2, capacity=4)
    academy.close_registration(lab.code)
    academy.enroll(academy.students[0], lab)


# ----------------------------------------------------------------------
# Scenario 2: populate a full term, then show only the dashboard
# ----------------------------------------------------------------------
def run_dashboard() -> None:
    """Populate a whole term and print a single screen summary."""
    academy = build_populated_term()
    print(Report.dashboard(academy))


def build_populated_term() -> Academy:
    """Build a realistic term: 8 students, 3 mentors, 5 courses."""
    academy = Academy()
    names = [
        ("Asha Rao", "BSc Computer Science", 2),
        ("Bilal Khan", "BSc Computer Science", 2),
        ("Chitra Iyer", "BCA", 1),
        ("Deepak Nair", "BSc Computer Science", 3),
        ("Esha Verma", "BCA", 2),
        ("Farhan Ali", "BSc Computer Science", 1),
        ("Geetha Menon", "BSc Computer Science", 3),
        ("Harish Babu", "BCA", 1),
    ]
    students = [
        academy.admit_student(name, f"{name.split()[0].lower()}@eurotech.edu", program, year)
        for name, program, year in names
    ]
    ravi = academy.hire_mentor("Ravi Kumar", "ravi.kumar@eurotech.edu", "Computer Science", 4.6)
    nisha = academy.hire_premium_mentor("Nisha Iyer", "nisha.iyer@eurotech.edu", "Mathematics", 4.9)
    farida = academy.hire_mentor("Farida Sheikh", "farida.sheikh@eurotech.edu", "Electronics", 4.1)

    python = academy.offer_course("Python Programming", 3, 40, mentor=ravi)
    oop = academy.offer_course("Object Oriented Programming", 4, 3, fee=1500, mentor=ravi)
    algorithms = academy.offer_course(
        "Algorithm Design", 4, 8, prerequisites=(oop.code,), mentor=ravi
    )
    databases = academy.offer_course("Database Management Systems", 3, 2, mentor=nisha)
    circuits = academy.offer_course("Digital Circuits", 3, 6, mentor=farida)

    scores = [95, 78, 66, 88, 91, 54, 83, 72]
    for learner, score in zip(students, scores, strict=True):
        academy.enroll(learner, python)
        academy.submit_score(learner, python, score)
        ravi.grade(python, learner, score)

    for learner, score in zip(students[:3], (92, 71, 65), strict=True):
        academy.enroll(learner, oop)
        academy.submit_score(learner, oop, score)
        ravi.grade(oop, learner, score)

    for learner, score in zip(students[:2], (85, 69), strict=True):
        academy.enroll(learner, algorithms)
        academy.submit_score(learner, algorithms, score)
        ravi.grade(algorithms, learner, score)

    for learner, score in zip(students[2:4], (88, 59), strict=True):
        academy.enroll(learner, databases)
        academy.submit_score(learner, databases, score)
        nisha.grade(databases, learner, score)

    academy.enroll(students[4], circuits)
    farida.grade(circuits, students[4], 74)

    academy.enroll(students[5], python)
    academy.enroll(students[6], databases)
    academy.enroll(students[7], circuits)
    return academy


# ----------------------------------------------------------------------
# Scenario 3: interactive shell
# ----------------------------------------------------------------------
HELP = """commands
  students | mentors | courses | people     list the registry
  roster CODE                              show one roster
  transcript NAME                          show one transcript
  enroll NAME CODE                         enroll a student
  submit NAME CODE SCORE                   submit an assignment score
  grade MENTOR NAME CODE SCORE             award a final grade
  drop NAME CODE                           drop an enrollment
  broadcast MESSAGE [audience]             audience: all | students | mentors
  dashboard | report | activity            rendered reports
  help | quit                               this text / exit

Names containing spaces must be quoted, e.g.  grade "Ravi Kumar" "Asha Rao" OOP-100 93"""


def run_shell(academy: Academy | None = None) -> None:
    """Start the interactive command shell on a populated academy."""
    academy = academy or build_populated_term()
    print(Report.banner(f"{academy.name} - interactive shell"))
    print(HELP)
    while True:
        try:
            raw = input("\ncms> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            return
        if not raw:
            continue
        try:
            parts = shlex.split(raw)
        except ValueError as exc:
            print(f"  ! unbalanced quotes ({exc})")
            continue
        command, args = parts[0].lower(), parts[1:]
        if command in {"quit", "exit"}:
            print("Bye.")
            return
        try:
            handle_command(academy, command, args)
        except CMSError as exc:
            print(f"  ! {type(exc).__name__}: {exc}")
        except (IndexError, ValueError) as exc:
            print(f"  ! bad arguments ({exc}) - type 'help' for usage")


def handle_command(academy: Academy, command: str, args: list[str]) -> None:
    """Dispatch one shell command to the academy and print the result."""
    if command == "help":
        print(HELP)
    elif command == "students":
        print(
            Report.table(
                ("id", "name", "program", "year", "gpa", "standing"),
                [
                    (s.user_id, s.name, s.program, s.year, f"{s.gpa():.2f}", s.academic_standing())
                    for s in academy.students
                ],
            )
        )
    elif command in {"mentors", "faculty"}:
        print(Report.mentor_workload(academy))
    elif command == "courses":
        print(Report.courses(academy))
    elif command == "people":
        print(Report.people(academy))
    elif command == "roster":
        print(academy.course(args[0]).roster())
    elif command == "transcript":
        print(academy.student(args[0]).transcript())
    elif command == "enroll":
        print(academy.enroll(args[0], args[1]))
    elif command == "submit":
        print(academy.submit_score(args[0], args[1], float(args[2])))
    elif command == "grade":
        print(academy.grade(args[0], args[1], args[2], float(args[3])))
    elif command == "drop":
        print(academy.drop(args[0], args[1]))
    elif command == "broadcast":
        audience = "all"
        words = list(args)
        if words and words[-1].lower() in {"all", "students", "mentors", "faculty", "premium"}:
            audience = words.pop().lower()
        message = " ".join(words) or "General announcement"
        for line in academy.broadcast(message, audience=audience):
            print(f"  {line}")
    elif command == "dashboard":
        print(Report.dashboard(academy))
    elif command == "report":
        print(Report.toppers(academy, limit=5))
        print(Report.section("Activity"))
        print(Report.activity(academy))
    elif command == "activity":
        print(Report.activity(academy))
    else:
        print(f"  ! unknown command '{command}' - type 'help'")


# ----------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------
def section(title: str) -> None:
    """Print a titled separator block."""
    print(f"\n{LINE}\n{title}\n{LINE}")


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Course Management System - OOP demonstration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="demo",
        choices=("demo", "dashboard", "shell"),
        help="demo: guided tour (default) | dashboard: one screen report | shell: interactive",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point: dispatch to the requested demo mode."""
    args = build_parser().parse_args(argv)
    if args.mode == "demo":
        run_demo()
    elif args.mode == "dashboard":
        run_dashboard()
    else:
        run_shell()
    return 0


if __name__ == "__main__":
    sys.exit(main())
