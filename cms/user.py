"""Abstract base class shared by every actor of the academy.

``User`` is intentionally abstract: it owns the identity and contact data that
``Student`` and ``Mentor`` have in common, and it declares the *contract*
(role, permissions and a human readable duty summary) that each concrete role
must fulfil.

OOP concepts demonstrated here
------------------------------
* **Abstraction** - :class:`User` cannot be instantiated, it only defines the
  blueprint (``role``, ``permissions``, ``duties``).
* **Encapsulation** - state lives in name-mangled private attributes and is only
  reachable through validating properties, so an invalid e-mail can never enter
  the object graph.
* **Instance methods** - property getters/setters, ``can`` and ``describe``.
* **@staticmethod** - pure validation helpers that belong to the class but do
  not depend on any instance (``validate_email``, ``validate_user_id``).
* **@classmethod** - ``generate_id`` builds identifiers from the shared class
  level counter and is inherited by every subclass.
* **Polymorphism** - ``describe`` is a *template method*: the base class fixes
  the output format while subclasses only override the ``duties`` hook.
"""

from __future__ import annotations

import itertools
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import ClassVar

from cms.exceptions import ValidationError

__all__ = ["User"]

_EMAIL_PATTERN = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z .'-]{1,60}$")


class User(ABC):
    """Immutable identity + contact data for any academy participant."""

    _id_counter: ClassVar[itertools.count[int]] = itertools.count(1)

    def __init__(self, user_id: str, name: str, email: str) -> None:
        self.__user_id = self.validate_user_id(user_id)
        self.__name = self.validate_name(name)
        self.__email = self.validate_email(email)
        self.__created_at = datetime.now()

    # ------------------------------------------------------------------
    # Encapsulated state, exposed through validating properties
    # ------------------------------------------------------------------
    @property
    def user_id(self) -> str:
        """Stable identifier, e.g. ``STU-0001`` (read only by design)."""
        return self.__user_id

    @property
    def name(self) -> str:
        return self.__name

    @name.setter
    def name(self, value: str) -> None:
        self.__name = self.validate_name(value)

    @property
    def email(self) -> str:
        return self.__email

    @email.setter
    def email(self, value: str) -> None:
        self.__email = self.validate_email(value)

    @property
    def created_at(self) -> datetime:
        return self.__created_at

    # ------------------------------------------------------------------
    # Abstract contract
    # ------------------------------------------------------------------
    @property
    @abstractmethod
    def role(self) -> str:
        """Short machine readable role, e.g. ``student`` or ``mentor``."""

    @abstractmethod
    def permissions(self) -> frozenset[str]:
        """Capabilities granted to this role."""

    @abstractmethod
    def duties(self) -> str:
        """One line description of what this role does in the academy."""

    # ------------------------------------------------------------------
    # Instance methods built on top of the contract
    # ------------------------------------------------------------------
    def can(self, permission: str) -> bool:
        """Return ``True`` when the role grants *permission*."""
        return permission in self.permissions()

    def describe(self) -> str:
        """Template method: the layout lives here, the details in subclasses."""
        return f"[{self.role.upper():<15}] {self.user_id} | {self.name} | {self.duties()}"

    def notify(self, message: str) -> str:
        """Deliver a message to the user (overridden by ``PremiumMentor``)."""
        return f"[{self.role}] {self.name} <{self.email}> :: {message}"

    def contact_sheet(self) -> str:
        return f"{self.user_id} | {self.name} | {self.email}"

    # ------------------------------------------------------------------
    # @staticmethod - stateless validators shared by every subclass
    # ------------------------------------------------------------------
    @staticmethod
    def validate_email(email: str) -> str:
        """Normalise and validate an e-mail address."""
        if not isinstance(email, str) or not _EMAIL_PATTERN.match(email.strip()):
            raise ValidationError(f"'{email}' is not a valid e-mail address")
        return email.strip().lower()

    @staticmethod
    def validate_name(name: str) -> str:
        """Normalise a display name and reject obvious junk."""
        if not isinstance(name, str) or not _NAME_PATTERN.match(name.strip()):
            raise ValidationError(f"'{name}' is not a valid name")
        return " ".join(name.split())

    @staticmethod
    def validate_user_id(user_id: str) -> str:
        if not isinstance(user_id, str) or not user_id.strip():
            raise ValidationError("User id must be a non empty string")
        return user_id.strip().upper()

    @staticmethod
    def initials(name: str) -> str:
        """``'Ada Lovelace' -> 'AL'`` (used for badges in the reports)."""
        parts = [part[0] for part in name.split() if part]
        return "".join(parts[:2]).upper()

    # ------------------------------------------------------------------
    # @classmethod - alternative constructors / shared factory logic
    # ------------------------------------------------------------------
    @classmethod
    def generate_id(cls, prefix: str) -> str:
        """Allocate the next identifier for *prefix* (``STU-0001`` ...)."""
        if not isinstance(prefix, str) or not prefix.strip():
            raise ValidationError("Id prefix must be a non empty string")
        return f"{prefix.strip().upper()}-{next(cls._id_counter):04d}"

    @classmethod
    def from_record(cls, record: dict[str, str]) -> User:
        """Rebuild a user from a plain dictionary (repository friendly)."""
        missing = {"user_id", "name", "email"} - record.keys()
        if missing:
            raise ValidationError(f"Missing user fields: {sorted(missing)}")
        return cls(record["user_id"], record["name"], record["email"])

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------
    def __str__(self) -> str:
        return self.describe()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self.user_id} name={self.name!r}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return NotImplemented
        return (self.user_id, type(self).__name__) == (other.user_id, type(other).__name__)

    def __hash__(self) -> int:
        return hash((self.user_id, type(self).__name__))
