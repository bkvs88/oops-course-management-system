"""Abstraction, encapsulation, static methods and class methods of ``User``."""

from __future__ import annotations

import unittest

from cms.exceptions import ValidationError
from cms.mentor import Mentor, PremiumMentor
from cms.student import Student
from cms.user import User


class TestAbstraction(unittest.TestCase):
    """The base class must never be instantiated directly."""

    def test_user_is_abstract(self) -> None:
        with self.assertRaises(TypeError):
            User("STU-0001", "Asha Rao", "asha@uni.edu")  # type: ignore[abstract]

    def test_abstract_contract_is_declared(self) -> None:
        self.assertTrue(User.__abstractmethods__)
        self.assertEqual(User.__abstractmethods__, frozenset({"role", "permissions", "duties"}))

    def test_every_concrete_role_can_be_built(self) -> None:
        for role in (Student, Mentor, PremiumMentor):
            user = role(role.generate_id("X"), "Asha Rao", "asha@uni.edu")
            self.assertIsInstance(user, User)


class TestEncapsulation(unittest.TestCase):
    """State must be reachable only through validating properties."""

    def setUp(self) -> None:
        self.student = Student.register("Asha Rao", "asha.rao@uni.edu")

    def test_private_attributes_are_name_mangled(self) -> None:
        self.assertFalse(hasattr(self.student, "_Student__enrollments") is False)
        self.assertIn("_Student__enrollments", vars(self.student))

    def test_invalid_email_is_rejected_by_the_setter(self) -> None:
        with self.assertRaises(ValidationError):
            self.student.email = "not-an-email"
        self.assertEqual(self.student.email, "asha.rao@uni.edu")

    def test_valid_email_is_normalised(self) -> None:
        self.student.email = "  NEW.Address@Uni.EDU "
        self.assertEqual(self.student.email, "new.address@uni.edu")

    def test_user_id_is_read_only(self) -> None:
        with self.assertRaises(AttributeError):
            self.student.user_id = "STU-9999"  # type: ignore[misc]

    def test_name_is_whitespace_normalised(self) -> None:
        self.student.name = "  Asha   Rao  "
        self.assertEqual(self.student.name, "Asha Rao")

    def test_roster_property_returns_a_defensive_copy(self) -> None:
        snapshot = self.student.enrollments
        self.assertIsInstance(snapshot, tuple)
        self.assertEqual(snapshot, ())


class TestStaticMethods(unittest.TestCase):
    """``@staticmethod`` helpers: no instance state, no ``self``."""

    def test_validate_email(self) -> None:
        self.assertEqual(User.validate_email(" ADA@Uni.EDU "), "ada@uni.edu")
        for bad in ("", "ada@", "@uni.edu", "ada uni.edu", 42):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                User.validate_email(bad)  # type: ignore[arg-type]

    def test_validate_name(self) -> None:
        self.assertEqual(User.validate_name(" Asha  Rao "), "Asha Rao")
        with self.assertRaises(ValidationError):
            User.validate_name("7")

    def test_validate_user_id_upper_cases(self) -> None:
        self.assertEqual(User.validate_user_id(" stu-0001 "), "STU-0001")

    def test_initials(self) -> None:
        self.assertEqual(User.initials("Asha Rao"), "AR")
        self.assertEqual(User.initials("Chitra"), "C")

    def test_static_methods_are_callable_on_the_class(self) -> None:
        self.assertTrue(callable(User.validate_email))
        self.assertIsInstance(User.__dict__["validate_email"], staticmethod)


class TestClassMethods(unittest.TestCase):
    """``@classmethod`` factories keep the identifier policy in one place."""

    def test_generate_id_is_monotonic(self) -> None:
        first = User.generate_id("abc")
        second = User.generate_id("abc")
        prefix_a, number_a = first.rsplit("-", 1)
        prefix_b, number_b = second.rsplit("-", 1)
        self.assertEqual(prefix_a, "ABC")
        self.assertEqual(prefix_a, prefix_b)
        self.assertEqual(int(number_b), int(number_a) + 1)
        self.assertEqual(len(number_a), 4)

    def test_generate_id_rejects_empty_prefix(self) -> None:
        with self.assertRaises(ValidationError):
            User.generate_id("  ")

    def test_factories_use_the_inherited_id_policy(self) -> None:
        student = Student.register("Asha Rao", "asha@uni.edu")
        mentor = Mentor.appoint("Ravi Kumar", "ravi@uni.edu")
        self.assertTrue(student.user_id.startswith("STU-"))
        self.assertTrue(mentor.user_id.startswith("MEN-"))
        self.assertNotEqual(student.user_id, mentor.user_id)

    def test_from_record_round_trip(self) -> None:
        student = Student.from_record(
            {"user_id": "STU-0042", "name": "Asha Rao", "email": "asha@uni.edu"}
        )
        self.assertEqual(student.user_id, "STU-0042")
        with self.assertRaises(ValidationError):
            Student.from_record({"name": "Asha"})


class TestIdentity(unittest.TestCase):
    """Dunder protocol on the base class."""

    def test_equality_uses_id_and_concrete_type(self) -> None:
        one = Student("STU-0001", "Asha Rao", "asha@uni.edu")
        two = Student("STU-0001", "Asha Rao", "asha@uni.edu")
        mentor = Mentor("STU-0001", "Asha Rao", "asha@uni.edu")
        self.assertEqual(one, two)
        self.assertNotEqual(one, mentor)
        self.assertNotEqual(one, "STU-0001")

    def test_hashable(self) -> None:
        one = Student("STU-0001", "Asha Rao", "asha@uni.edu")
        two = Student("STU-0001", "Asha Rao", "asha@uni.edu")
        self.assertEqual(len({one, two}), 1)

    def test_repr_and_str(self) -> None:
        student = Student("STU-0001", "Asha Rao", "asha@uni.edu")
        self.assertIn("STU-0001", repr(student))
        self.assertIn("STUDENT", str(student))


if __name__ == "__main__":
    unittest.main()
