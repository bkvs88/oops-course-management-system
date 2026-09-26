"""Reporting layer built on top of the domain model.

This module is deliberately *functional in style*: the report writers are
mostly ``@staticmethod`` functions that take a collection of domain objects and
return a rendered block of text. That is the natural home for static methods -
they never touch instance state, they only read the objects handed to them.

It is also the clearest demonstration of **polymorphism**: the same ranking
code works for students, mentors and courses because every object exposes
``name``/``profile``-style methods, and the same ``banner()`` renders any title.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from cms.academy import Academy
    from cms.course import Course
    from cms.student import Student

__all__ = ["Report"]

_THIN = "-" * 78


def _is_number(cell: str) -> bool:
    stripped = cell.strip().replace(".", "", 1).replace("-", "", 1)
    return stripped.isdigit() and cell.strip() != ""


def _align(cell: str, width: int, right: bool) -> str:
    return cell.rjust(width) if right else cell.ljust(width)


class Report:
    """Collection of stateless renderers (all @staticmethod)."""

    # ------------------------------------------------------------------
    # Formatting primitives
    # ------------------------------------------------------------------
    @staticmethod
    def banner(title: str, char: str = "=") -> str:
        clean = str(title).strip().upper()
        return f"\n{char * 78}\n{clean.center(78)}\n{char * 78}"

    @staticmethod
    def section(title: str) -> str:
        return f"\n{title}\n{_THIN}"

    @staticmethod
    def table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> str:
        """Render a fixed width table; numeric columns are right aligned."""
        materialised = [[str(cell) for cell in row] for row in rows]
        widths = [len(h) for h in headers]
        for row in materialised:
            for index, cell in enumerate(row):
                if index < len(widths):
                    widths[index] = max(widths[index], len(cell))
        numeric = [
            all(_is_number(row[i]) for row in materialised if i < len(row))
            for i in range(len(headers))
        ]
        header = " | ".join(_align(h.upper(), widths[i], numeric[i]) for i, h in enumerate(headers))
        divider = "-+-".join("-" * width for width in widths)
        body = [
            " | ".join(_align(cell, widths[i], numeric[i]) for i, cell in enumerate(row))
            for row in materialised
        ]
        return "\n".join([header, divider, *body]) if body else f"{header}\n{divider}\n(empty)"

    # ------------------------------------------------------------------
    # Domain reports
    # ------------------------------------------------------------------
    @staticmethod
    def people(academy: Academy) -> str:
        """Polymorphic directory: every user renders itself through describe()."""
        rows = [user.describe() for user in academy.people()]
        return "\n".join(rows)

    @staticmethod
    def courses(academy: Academy) -> str:
        rows = [
            (
                course.code,
                course.title,
                course.level,
                course.credits,
                f"{course.seats_taken}/{course.capacity}",
                course.mentor.name if course.mentor else "unassigned",
            )
            for course in academy.courses
        ]
        return Report.table(("code", "title", "level", "cr", "seats", "mentor"), rows)

    @staticmethod
    def rosters(academy: Academy) -> str:
        return "\n\n".join(course.roster() for course in academy.courses)

    @staticmethod
    def toppers(academy: Academy, limit: int = 3) -> str:
        ranked = Report.rank_students(academy.students)[:limit]
        rows = [
            (
                rank,
                student.name,
                student.user_id,
                f"{student.gpa():.2f}",
                student.academic_standing(),
            )
            for rank, student in enumerate(ranked, start=1)
        ]
        return Report.table(("rank", "student", "id", "gpa", "standing"), rows)

    @staticmethod
    def mentor_workload(academy: Academy) -> str:
        rows = [
            (
                mentor.name,
                mentor.role,
                mentor.department,
                mentor.workload,
                f"{mentor.rating:.1f}",
                ", ".join(c.code for c in mentor.courses) or "-",
            )
            for mentor in sorted(academy.mentors, reverse=True)
        ]
        return Report.table(("mentor", "role", "department", "courses", "rating", "teaches"), rows)

    @staticmethod
    def activity(academy: Academy) -> str:
        lines = [f"{index:>2}. {entry}" for index, entry in enumerate(academy.activity_log, 1)]
        return "\n".join(lines) or "(no activity recorded yet)"

    @staticmethod
    def dashboard(academy: Academy) -> str:
        """One screen summary combining the statistics of the whole academy."""
        grades = [r.grade_points for r in academy.enrollments() if r.is_graded]
        scores = [r.score for r in academy.enrollments() if r.score is not None]
        occupancy = [
            100 * course.seats_taken / course.capacity
            for course in academy.courses
            if course.capacity
        ]
        blocks = [
            Report.banner(f"{academy.name} - academic dashboard"),
            Report.section("Key figures"),
            Report.table(
                ("metric", "value"),
                [
                    ("students admitted", len(academy.students)),
                    ("mentors on faculty", len(academy.mentors)),
                    ("courses offered", len(academy.courses)),
                    ("enrollment records", len(academy.enrollments())),
                    ("graded records", len(grades)),
                    ("campus average score", Report.average(scores)),
                    ("campus average grade points", Report.average(grades)),
                    ("average seat occupancy %", Report.average(occupancy)),
                ],
            ),
            Report.section("Course catalogue"),
            Report.courses(academy),
            Report.section("Top performers"),
            Report.toppers(academy),
            Report.section("Mentor workload"),
            Report.mentor_workload(academy),
        ]
        return "\n".join(blocks)

    # ------------------------------------------------------------------
    # Ranking / aggregation helpers
    # ------------------------------------------------------------------
    @staticmethod
    def rank_students(students: Iterable[Student]) -> list[Student]:
        """Sort students by GPA, then by credits earned, then by name."""
        return sorted(
            students,
            key=lambda s: (-s.gpa(), -s.credits_registered(), s.name),
        )

    @staticmethod
    def average(values: Iterable[float]) -> float:
        numbers = [float(v) for v in values]
        return round(statistics.fmean(numbers), 2) if numbers else 0.0

    @staticmethod
    def risk_list(academy: Academy, threshold: float = 5.0) -> tuple[Student, ...]:
        """Students below the *threshold* GPA who still have active courses."""
        return tuple(
            student
            for student in academy.students
            if student.graded_records and student.gpa() < threshold
        )

    @staticmethod
    def unassigned_courses(academy: Academy) -> tuple[Course, ...]:
        return tuple(course for course in academy.courses if course.mentor is None)
