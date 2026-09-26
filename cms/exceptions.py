"""Custom exception hierarchy for the Course Management System.

Every error raised by the domain model derives from :class:`CMSError`, so the
CLI and the test-suite can catch a single base class and still discriminate
between the individual failure modes.
"""

from __future__ import annotations

__all__ = [
    "CMSError",
    "ValidationError",
    "RolePermissionError",
    "UnknownUserError",
    "DuplicateEnrollmentError",
    "EnrollmentClosedError",
    "CapacityFullError",
    "PrerequisiteError",
    "RecordLockedError",
]


class CMSError(Exception):
    """Base class for every error raised by the academy."""


class ValidationError(CMSError):
    """Raised when user supplied data fails validation."""


class RolePermissionError(CMSError):
    """Raised when a user attempts an action outside of their role."""


class UnknownUserError(CMSError):
    """Raised when a user id cannot be resolved in the academy registry."""


class DuplicateEnrollmentError(CMSError):
    """Raised when a student joins the same course twice."""


class EnrollmentClosedError(CMSError):
    """Raised when a course is not accepting new enrollments."""


class CapacityFullError(CMSError):
    """Raised when a course has no seats left."""


class PrerequisiteError(CMSError):
    """Raised when a student has not completed the required prior courses."""


class RecordLockedError(CMSError):
    """Raised when a finalized enrollment record is mutated."""
