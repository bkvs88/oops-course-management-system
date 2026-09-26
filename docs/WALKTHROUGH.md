# Walkthrough — Course Management System (Python OOP)

> The long-form companion to [`README.md`](../README.md). It explains the **problem**, the
> **architecture**, every **OOP concept** with the exact code that implements it, the
> **Git/GitHub workflow** used to build the project, **how to execute** it and the **final output**.

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Requirements and acceptance criteria](#2-requirements-and-acceptance-criteria)
3. [Architecture](#3-architecture)
4. [Class-by-class design](#4-class-by-class-design)
5. [OOP concepts with real code](#5-oop-concepts-with-real-code)
6. [Important code walkthrough](#6-important-code-walkthrough)
7. [Git and GitHub workflow](#7-git-and-github-workflow)
8. [Execution](#8-execution)
9. [Final output](#9-final-output)
10. [Testing and quality gates](#10-testing-and-quality-gates)
11. [What I would do next](#11-what-i-would-do-next)

---

## 1. Problem statement

A training institute runs one academic term at a time. Before this project the registry lived in a
spreadsheet plus a shared folder of result sheets. That model has four concrete failure modes:

| Problem | Consequence |
| --- | --- |
| Students could be added to a full batch | Overbooking, mentor overload |
| Students joined advanced courses without the prerequisite | Academic integrity risk |
| Anyone could edit a final grade | Results could not be trusted or audited |
| Reports were rebuilt by hand every term | Two days of work, and a different number every time |

**The engineering answer is not validation in a UI layer — it is validation in the domain model.**
Rules belong next to the data they protect, so that *no* caller (CLI, web handler, test, or future
script) can bypass them.

So the goal of this project is twofold:

1. **Build a real system** that models one academic term: students, mentors, courses, seats,
   prerequisites, grading, transcripts, reports.
2. **Demonstrate every core OOP concept in Python** — abstraction, encapsulation, inheritance,
   polymorphism, instance methods, `@staticmethod`, `@classmethod` — in code that a reviewer would
   actually accept, not in a toy snippet.

Everything is in memory and depends only on the standard library, so the whole system can be
inspected, run and tested in seconds.

---

## 2. Requirements and acceptance criteria

**Functional**

- Admit students, appoint mentors, offer courses
- Enroll / drop with automatic rule enforcement
- Submit scores, award final grades, compute GPA and transcripts
- Report on students, courses, mentors and the campus as a whole

**Non-functional (the OOP brief)**

| # | Requirement | Verified by |
| --- | --- | --- |
| 1 | Inheritance | `Student(User)`, `Mentor(User)`, `PremiumMentor(Mentor)` |
| 2 | Encapsulation | private attributes + validating properties, immutable snapshots |
| 3 | Polymorphism | `role`/`duties`/`notify`/`profile` overrides, one loop over mixed users |
| 4 | Abstraction | `User(ABC)` with three abstract members, cannot be instantiated |
| 5 | Instance methods | every domain behaviour (`enroll`, `grade`, `gpa`, `roster`, …) |
| 6 | `@staticmethod` | validators, grading policy, report renderers |
| 7 | `@classmethod` | id allocation and factory constructors |

**Business rules (all enforced by the model)**

- A student cannot hold two seats in the same course
- A batch never exceeds its capacity, unless a mentor holding `override_capacity` allows it
- A prerequisite must be **completed**, not merely enrolled
- A record moves `ENROLLED → SUBMITTED → COMPLETED | DROPPED` and is immutable afterwards
- Only the assigned mentor may grade; only a student may be graded

---

## 3. Architecture

### 3.1 Layering

Dependencies point in one direction only. Higher layers may know lower ones, never the reverse.

```
Layer 4  Presentation     main.py                      argparse CLI, demo, shell
Layer 3  Service          academy.py, report.py        facade, registry, renderers
Layer 2  Domain           course.py, enrollment.py,
                          student.py, mentor.py        business rules
Layer 1  Foundation       user.py, exceptions.py       ABC + error hierarchy
```

### 3.2 The circular-import trap, and how it is avoided

`Course` creates `Enrollment` records; `Enrollment` points back at a `Course`, a `Student` and a
`Mentor`. A naive implementation imports each other and dies at import time.

The fix is one-directional:

- `enrollment.py` imports `Course`/`Student`/`Mentor` **only under `TYPE_CHECKING`** — they are
  needed for annotations, not at runtime.
- `course.py` imports `Enrollment` **normally** — it is the aggregate root that mints records.
- `student.py` imports `Enrollment` normally (it re-exports the grading policy) and `Course` only
  for typing.

```python
# cms/enrollment.py
if TYPE_CHECKING:                      # pragma: no cover - typing only
    from cms.course import Course
    from cms.mentor import Mentor
    from cms.student import Student
```

Result: `import cms` is safe, `mypy` is happy, and the direction of creation is explicit — a
`Course` owns its roster, a student merely points at it.

### 3.3 Who owns what

| Object | Owns | Exposes |
| --- | --- | --- |
| `Course` | `__records: dict[str, Enrollment]` keyed by student id | `enrollments`, `active_students`, `seats_left` — tuples, never the dict |
| `Enrollment` | one seat: `__status`, `__score`, `__grade`, `__graded_by` | read-only properties + transitions |
| `Student` | `__enrollments: list[Enrollment]` (its transcript) | `transcript()`, `gpa()`, `active_enrollments` |
| `Mentor` | `__courses: list[Course]` | `courses`, `workload`, `students(course)` |
| `Academy` | three private dict registries | resolution by id *or* name, activity log |

The one deliberate duplication — a student remembers its enrollments *and* a course remembers its
students — is kept consistent by routing every mutation through `Course` and by handing out
**immutable snapshots** (tuples) so nobody can mutate the internals from outside.

### 3.4 Exception hierarchy

Every failure is a `CMSError`, so a UI or a script can catch one class and still discriminate:

```
CMSError
├── ValidationError          bad e-mail, score out of 0-100, bad year, unknown grade
├── RolePermissionError      wrong actor: grading without teaching, booking as a mentor
├── UnknownUserError         id/name not in the registry
├── DuplicateEnrollmentError same student, same course, twice
├── EnrollmentClosedError    registration window is shut
├── CapacityFullError        no seats left
├── PrerequisiteError        prior course not completed
└── RecordLockedError        mutation of a finalized record
```

---

## 4. Class-by-class design

### 4.1 `User` — the abstract foundation

Identity and contact data are identical for every role, so they live in one place. The role-specific
parts are declared as an **abstract contract**, which is what makes the class safe to hold in a
`list[User]` and iterate over.

```python
class User(ABC):
    _id_counter: ClassVar[itertools.count[int]] = itertools.count(1)

    def __init__(self, user_id: str, name: str, email: str) -> None:
        self.__user_id = self.validate_user_id(user_id)   # __name-mangled: _User__user_id
        self.__name = self.validate_name(name)
        self.__email = self.validate_email(email)
        self.__created_at = datetime.now()
```

Private state (`__user_id`, `__name`, `__email`, `__created_at`) is exposed only through properties,
and the two that are mutable are guarded by validating setters:

```python
    @property
    def email(self) -> str:
        return self.__email

    @email.setter
    def email(self, value: str) -> None:
        self.__email = self.validate_email(value)     # invalid input never reaches the object
```

`user_id` is deliberately read-only — an identity that can be edited after the fact is not an
identity.

### 4.2 `Student` — academic state

The enrollment ledger is private. `enroll` and `drop` delegate to the `Course`, which owns
validation and record creation, so the two sides cannot drift apart:

```python
    def enroll(self, course: Course) -> Enrollment:
        """Join *course*; the course object owns validation and creation."""
        enrollment = course.enroll(self)      # all rules live in Course.enroll
        self.__enrollments.append(enrollment) # only the transcript is kept here
        return enrollment
```

### 4.3 `Mentor` / `PremiumMentor` — teaching and multi-level inheritance

`PremiumMentor` inherits from `Mentor` (which inherits from `User`). It adds capabilities *without*
duplicating the base permissions:

```python
    def permissions(self) -> frozenset[str]:
        return super().permissions() | frozenset({"schedule_1on1", "override_capacity"})
```

### 4.4 `Course` — the aggregate root

`Course` is the only class allowed to create an `Enrollment`, which is how the invariants are
guaranteed rather than merely documented.

### 4.5 `Enrollment` — a state machine in one object

```
        submit_score()            award_grade()
ENROLLED ───────────► SUBMITTED ─────────────► COMPLETED  (final, locked)
   │                       │                        │
   └───────────────────────┴──── drop() ────────────┴──► DROPPED
```

---

## 5. OOP concepts with real code

### 5.1 Abstraction — `cms/user.py:40`

`User` is an `ABC` with three abstract members. It cannot be instantiated, and any subclass that
forgets one of them fails loudly at construction time, not at 2 a.m. in production.

```python
class User(ABC):
    @property
    @abstractmethod
    def role(self) -> str: ...

    @abstractmethod
    def permissions(self) -> frozenset[str]: ...

    @abstractmethod
    def duties(self) -> str: ...
```

Proof:

```python
>>> User("STU-0001", "Asha Rao", "asha@uni.edu")
TypeError: Can't instantiate abstract class User without an implementation for
abstract methods 'duties', 'permissions', 'role'
```

Abstraction is also applied at the *behavioural* level: callers work with `course.can_enroll(student)`,
`course.seats_left`, `enrollment.grade_points` instead of poking at collections.

### 5.2 Encapsulation

Three layers of defence:

**(a) Name mangling.** `self.__enrollments` becomes `self._Student__enrollments`. It is reachable
only from inside the class, and a subclass cannot silently corrupt it either.

**(b) Validation at every door.** Construction, setters and method arguments all go through the same
policy:

```python
    @staticmethod
    def validate_email(email: str) -> str:
        """Normalise and validate an e-mail address."""
        if not isinstance(email, str) or not _EMAIL_PATTERN.match(email.strip()):
            raise ValidationError(f"'{email}' is not a valid e-mail address")
        return email.strip().lower()
```

```python
>>> s.email = "not-an-email"
ValidationError: 'not-an-email' is not a valid e-mail address
```

**(c) Defensive copies.** Mutable internals are never handed out; the caller gets a tuple:

```python
    @property
    def active_students(self) -> tuple[Student, ...]:
        return tuple(r.student for r in self.__records.values() if r.is_active)
```

An invariant such as "a completed record is immutable" is enforced by the object graph itself:

```python
    def _assert_open(self, action: str) -> None:
        if self.__status in self.CLOSED_STATES:
            raise RecordLockedError(
                f"{self.__id} is {self.__status.lower()}; cannot {action} any more"
            )
```

### 5.3 Inheritance — three levels deep

```
User (ABC)
├── Student
└── Mentor
    └── PremiumMentor        (multi-level)
```

`Student` and `Mentor` inherit identity handling, validation, `describe()`, `can()` and the id
factory. `PremiumMentor` inherits everything a mentor can do and adds the premium capabilities.
The shared base means one fix (say, a stricter e-mail pattern) lands everywhere at once.

### 5.4 Polymorphism — four flavours in one project

**(a) Method overriding.** Same method name, different behaviour per role:

```python
# User
    def notify(self, message: str) -> str:
        return f"[{self.role}] {self.name} <{self.email}> :: {message}"

# PremiumMentor
    def notify(self, message: str) -> str:
        return f"[premium-priority] {self.name} :: {message}"
```

**(b) Template method.** `describe()` is defined **once** in `User`; the layout is fixed and the
per-role part comes from the overridden hook. No subclass rewrites the format string:

```python
    def describe(self) -> str:
        """Template method: the layout lives here, the details in subclasses."""
        return f"[{self.role.upper():<15}] {self.user_id} | {self.name} | {self.duties()}"
```

**(c) Polymorphism in action — one call, many behaviours.** `broadcast` walks a heterogeneous list
and lets each object decide how to render itself. No `isinstance` chain, no `if role ==`:

```python
    def broadcast(self, message: str, audience: str = "all") -> tuple[str, ...]:
        targets = self.__audience(audience)
        sent = tuple(user.notify(f"{message} [{audience}]") for user in targets)
        self._log(f"broadcast to {len(sent)} {audience} recipient(s): {message}")
        return sent
```

Output for one call over four different objects:

```
[student] Asha Rao <asha@eurotech.edu> :: Mid-term examination schedule is published [all]
[mentor] Ravi Kumar <ravi.kumar@eurotech.edu> :: Mid-term examination schedule is published [all]
[premium-priority] Nisha Iyer :: Mid-term examination schedule is published [all]
```

**(d) Duck typing.** `Report` never imports `Student`'s type to render it; it only calls
`student.profile()`, `student.gpa()`, `course.code`. A brand-new class with the same methods would
work in every report without touching `report.py`.

### 5.5 Instance methods

The methods that *do* the work, and the ones that need `self`:

```python
    def enroll(self, course: Course) -> Enrollment: ...       # Student
    def award_grade(self, mentor: Mentor, score: float | None = None) -> Enrollment: ...  # Enrollment
    def gpa(self) -> float: ...                              # Student
    def transcript(self) -> str: ...                         # Student
    def roster(self) -> str: ...                             # Course
    def pass_percentage(self) -> float: ...                  # Course
    def override_enroll(self, student: Student, course: Course) -> Enrollment: ...  # Mentor
```

### 5.6 `@staticmethod` — policy that belongs to the class but not to an instance

A static method is called on the class, receives no `self`, and is the right home for anything that
is a *rule* rather than *state*.

```python
# cms/enrollment.py — the single source of truth for grading
    @staticmethod
    def letter_grade(percentage: float) -> str:
        """Percentage -> letter grade using the class level grading policy."""
        value = Enrollment.validate_score(percentage)
        if value >= 90: return "O"
        if value >= 80: return "A+"
        ...
        return "F"
```

```python
# cms/course.py — catalogue rules
    @staticmethod
    def build_code(title: str) -> str:
        """``'Object Oriented Programming' -> 'OOP-100'`` (acronym + level)."""
        words = [w for w in re.split(r"[^A-Za-z0-9]+", title) if w and w.lower() not in _STOP_WORDS]
        acronym = "".join(w[0] for w in words[:4]).upper()
        return f"{acronym}-{Course.infer_level(title) * 100}"
```

```python
# cms/report.py — pure rendering, no state
    @staticmethod
    def average(values: Iterable[float]) -> float:
        numbers = [float(v) for v in values]
        return round(statistics.fmean(numbers), 2) if numbers else 0.0
```

The whole `Report` class is static methods on purpose: a report has no identity of its own.

### 5.7 `@classmethod` — factories and alternative constructors

A classmethod receives `cls`, so it can allocate from class-level state and is inherited properly.

```python
# cms/user.py — one counter, shared by the whole hierarchy
    _id_counter: ClassVar[itertools.count[int]] = itertools.count(1)

    @classmethod
    def generate_id(cls, prefix: str) -> str:
        """Allocate the next identifier for *prefix* (``STU-0001`` ...)."""
        return f"{prefix.strip().upper()}-{next(cls._id_counter):04d}"
```

```python
# cms/student.py
    @classmethod
    def register(cls, name: str, email: str, program: str = "BSc Computer Science") -> Student:
        """Factory that allocates the next ``STU-xxxx`` id automatically."""
        return cls(cls.generate_id("STU"), name, email, program)

# cms/mentor.py
    @classmethod
    def appoint(cls, name, email, department="Computer Science", rating=4.5) -> Mentor:
        return cls(cls.generate_id("MEN"), name, email, department, rating)

# cms/mentor.py — the multi-level subclass uses the same inherited helper
    @classmethod
    def hire(cls, name, email, department="Computer Science", session_fee=SESSION_PRICE) -> PremiumMentor:
        return cls(cls.generate_id("PMN"), name, email, department, 4.9, session_fee=session_fee)

# cms/course.py
    @classmethod
    def offer(cls, title, credits=3, capacity=30, prerequisites=(), fee=0.0) -> Course:
        """Create a course and derive its code from the title."""
        return cls(title, credits, capacity, None, prerequisites, fee)

# cms/enrollment.py — the ONLY supported way to create a record
    @classmethod
    def open(cls, student: Student, course: Course) -> Enrollment:
        """Create a fresh record in the ``ENROLLED`` state."""
        if student.role != "student":
            raise ValidationError(f"Only students can be enrolled, got {student.role}")
        return cls(student, course)
```

`Enrollment.open` is the important one: because it is a classmethod and the `__init__` is not part
of the public contract, **every record is guaranteed to start in a valid state** with a fresh id.

### 5.8 Bonus: operator overloading and the dunder protocol

```python
# cms/mentor.py — mentors sort by rating
    def __lt__(self, other: Mentor) -> bool:
        if not isinstance(other, Mentor):
            return NotImplemented
        return self.__rating < other.__rating

>>> sorted(academy.mentors, reverse=True)[0].name
'Nisha Iyer'
```

```python
# cms/course.py — a course behaves like a collection of its records
len(course)            # seats taken
for record in course:  # iterate Enrollment objects
asha in course         # is this student on the roster?
```

---

## 6. Important code walkthrough

### 6.1 Enrollment — the heart of the system (`cms/course.py:175`)

```python
    def enroll(self, student: Student, by: Mentor | None = None) -> Enrollment:
        """Hand a seat to *student* and return the new enrollment record."""
        if student.role != "student":
            raise ValidationError(f"Only students can enroll, got {student.role!r}")
        if not self.__open:
            raise EnrollmentClosedError(f"{self.__code} enrollment window is closed")
        if self.is_enrolled(student):
            raise DuplicateEnrollmentError(f"{student.name} is already in {self.__code}")
        override = by is not None and by.can("override_capacity")
        if self.is_full and not override:
            raise CapacityFullError(
                f"{self.__code} is full ({self.__capacity}/{self.__capacity} seats taken)"
            )
        self._assert_prerequisites(student)
        record = Enrollment.open(student, self)
        self.__records[student.user_id] = record
        return record
```

Line by line, five invariants in order: *right kind of actor → window open → no duplicate seat →
seat available → prerequisites met.* Only then is a record created.

### 6.2 Permission-gated override — polymorphism replacing an `if`

```python
# cms/mentor.py:141
    def override_enroll(self, student: Student, course: Course) -> Enrollment:
        if not self.is_teaching(course):
            raise RolePermissionError(f"{self.name} does not teach {course.code}")
        if not self.can("override_capacity"):
            raise RolePermissionError(
                f"{self.name} ({self.role}) cannot exceed the capacity of {course.code}"
            )
        record = course.enroll(student, by=self)
        student._attach(record)
        return record
```

`Course` never mentions `PremiumMentor`. It asks the *object* whether it may, and the object answers
from its own `permissions()`. Adding a third role tomorrow requires no change in `Course`.

### 6.3 Grade locking — the state machine (`cms/enrollment.py:130-160`)

```python
    def submit_score(self, score: float) -> Enrollment:
        """Student action: attach an assignment score (0-100)."""
        self._assert_open("submit a score")
        if self.__score is not None:
            raise RecordLockedError(
                f"{self.__student.name} already submitted a score for {self.__course.code}"
            )
        self.__score = self.validate_score(score)
        self.__status = "SUBMITTED"
        self.__updated_at = datetime.now()
        return self

    def award_grade(self, mentor: Mentor, score: float | None = None) -> Enrollment:
        """Mentor action: award the final letter grade and close the record."""
        self._assert_open("grade")
        if score is None:
            final_score = self.__score
            if final_score is None:
                raise ValidationError("Nothing to grade: the student has not submitted a score")
        else:
            final_score = self.validate_score(score)
        self.__score = final_score
        self.__grade = self.letter_grade(final_score)
        self.__status = "COMPLETED"
        self.__graded_by = mentor          # audit trail
        self.__updated_at = datetime.now()
        return self
```

### 6.4 Dropping keeps the audit trail

`Course.unenroll` cancels the record instead of deleting it, so the seat is released *and* the
transcript still shows what happened:

```python
    def unenroll(self, student: Student) -> Enrollment:
        record = self.__records.get(student.user_id)
        if record is None:
            raise ValidationError(f"{student.name} has no enrollment record for {self.__code}")
        if not record.is_active:
            raise RecordLockedError(
                f"{record.enrollment_id} is {record.status.lower()}; "
                f"{student.name} already holds a finalised result for {self.__code}"
            )
        return record.drop()
```

### 6.5 GPA without a special case for ungraded records

```python
# cms/student.py:140
    def gpa(self) -> float:
        """Grade point average over graded records (0.0 when there are none)."""
        graded = self.graded_records
        if not graded:
            return 0.0
        return round(sum(e.grade_points for e in graded) / len(graded), 2)
```

`graded_records` filters on `grade is not None`, so a student with three enrolled courses and one
result gets a GPA over **one** course, not four.

---

## 7. Git and GitHub workflow

### 7.1 Principles applied

- `main` is always runnable; work happens on `feature/<topic>` branches
- One concern per branch, one logical change per commit
- **Conventional Commits** prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`
- Merge commits with `--no-ff`, so the branch structure stays visible in `git log --graph`
- Commit bodies explain **why**, not only **what**
- Large risky work is reviewed through a Pull Request before it lands

### 7.2 Branch graph

```
*   Merge branch 'feature/tests-and-documentation'        <- Pull Request #1
|\
| * test(cms): add 93 unit tests covering every OOP concept and rule
| * docs: add professional README and the full walkthrough
| * docs: capture the verified execution output
*   Merge branch 'feature/academy-service-and-cli'
|\
| * feat(app): add Academy service, Report renderers and the runnable demo
*   Merge branch 'feature/course-enrollment'
|\
| * feat(enrollment): add Course aggregate root and Enrollment record
*   Merge branch 'feature/student-mentor-roles'
|\
| * feat(roles): implement Student, Mentor and multi-level PremiumMentor
*   Merge branch 'feature/abstract-user-hierarchy'
|\
| * feat(user): add abstract User base class and domain exception hierarchy
* chore: bootstrap repository with packaging, lint and ignore configuration
```

### 7.3 How each branch was produced

```bash
# 1. trunk: configuration that every branch can rely on
git init -b main
git add -A
git commit -m "chore: bootstrap repository with packaging, lint and ignore configuration"

# 2. foundation
git checkout -b feature/abstract-user-hierarchy
#    ... write cms/exceptions.py + cms/user.py, then:
git commit -m "feat(user): add abstract User base class and domain exception hierarchy"
git checkout main
git merge --no-ff feature/abstract-user-hierarchy -m "Merge branch 'feature/abstract-user-hierarchy' into main"

# 3. roles            -> feature/student-mentor-roles
# 4. academic core    -> feature/course-enrollment
# 5. service + CLI    -> feature/academy-service-and-cli

# 6. tests and documentation reviewed through a Pull Request
git checkout -b feature/tests-and-documentation
#    ... write tests/ + README.md + docs/WALKTHROUGH.md
git commit -m "test(cms): add 93 unit tests covering every OOP concept and rule"
git commit -m "docs: add professional README and the full walkthrough"
git push -u origin feature/tests-and-documentation
gh pr create --fill --base main --head feature/tests-and-documentation
gh pr merge --squash --delete-branch
```

### 7.4 A branch history correction worth documenting

The roles branch was initially cut from the *unmerged* user branch, which meant the user branch
never appeared as merged in its own right. Because the working trees were identical, `main` was
rewound to the bootstrap commit and the two feature branches were merged in order, so the history
now shows each unit of work landing on the trunk separately.

```bash
git rev-parse main^{tree} feature/student-mentor-roles^{tree}   # identical → safe to rewrite
git reset --hard ef24dfc
git merge --no-ff feature/abstract-user-hierarchy
git merge --no-ff feature/student-mentor-roles
```

### 7.5 The Pull Request

`feature/tests-and-documentation` was **not** merged locally. It was pushed and merged on GitHub, so
the tests and documentation went through the review flow:

- **Title** mirrors the commit intent
- **Body** lists what changed, what was verified (93 tests, ruff, mypy) and the two design bugs the
  tests uncovered
- **Merge** with `--squash` and branch deletion, keeping `main` linear-per-PR while the individual
  commits stay visible on the feature branch

Two genuine design flaws were caught by writing the tests, and both are recorded in commit messages
rather than silently patched:

| Bug | Symptom | Fix |
| --- | --- | --- |
| `Enrollment.grade` was both a property and a method | the method silently shadowed the property; reports printed `<bound method …>` | renamed the transition to `award_grade()` |
| `Mentor.release()` required "no open seats" | a concluded batch can never satisfy it | added `Course.is_concluded` / `pending_enrollments` and released on that basis |

---

## 8. Execution

### 8.1 Prerequisites

Python 3.10+ (developed on 3.13). No third-party runtime dependency.

```bash
git clone https://github.com/bkvs88/oops-course-management-system.git
cd oops-course-management-system
python3 --version          # Python 3.10 or newer
```

### 8.2 Run

```bash
python3 main.py demo         # guided tour of every feature (default)
python3 main.py dashboard    # one screen summary of a whole term
python3 main.py shell        # interactive command shell
python3 main.py --help       # options
```

### 8.3 Test and lint

```bash
python3 -m unittest discover -s tests -v   # 93 tests, stdlib only
python3 -m pytest -q                       # same suite via pytest
python3 -m ruff check .                    # lint
python3 -m ruff format --check .           # format
python3 -m mypy .                          # strict type check
```

### 8.4 Interactive session transcript

```
$ python3 main.py shell
cms> students
ID       | NAME         | PROGRAM              | YEAR |  GPA | STANDING
---------+--------------+----------------------+------+------+------------
STU-0001 | Asha Rao     | BSc Computer Science |    2 | 9.67 | Outstanding
STU-0002 | Bilal Khan   | BSc Computer Science |    2 | 7.67 | Good
STU-0003 | Chitra Iyer  | BCA                  |    1 | 7.67 | Good
STU-0004 | Deepak Nair  | BSc Computer Science |    3 | 7.50 | Good
STU-0005 | Esha Verma   | BCA                  |    2 | 9.00 | Outstanding
STU-0006 | Farhan Ali   | BSc Computer Science |    1 | 6.00 | Average
STU-0007 | Geetha Menon | BSc Computer Science |    3 | 9.00 | Outstanding
STU-0008 | Harish Babu  | BCA                  |    1 | 8.00 | Excellent

cms> enroll "Harish Babu" OOP-100
ENR-0020 Harish Babu -> OOP-100 [ENROLLED] score=-- grade=--

cms> submit "Harish Babu" OOP-100 77
ENR-0020 Harish Babu -> OOP-100 [SUBMITTED] score=77.0 grade=--

cms> grade "Ravi Kumar" "Harish Babu" OOP-100 77
ENR-0020 Harish Babu -> OOP-100 [COMPLETED] score=77.0 grade=A

cms> drop "Harish Babu" OOP-100
  ! RecordLockedError: ENR-0020 is completed; Harish Babu already holds a finalised result for OOP-100

cms> quit

cms> broadcast "Lab exam shifted to Friday" mentors
  [mentor] Ravi Kumar <ravi.kumar@eurotech.edu> :: Lab exam shifted to Friday [mentors]
  [premium-priority] Nisha Iyer :: Lab exam shifted to Friday [mentors]
  [mentor] Farida Sheikh <farida.sheikh@eurotech.edu> :: Lab exam shifted to Friday [mentors]

cms> quit
```

Note line 4: a completed record cannot be dropped. The rule is not in the shell, it is in the model.

---

## 9. Final output

`python3 main.py demo` — abridged, verbatim from a verified run:

```
==============================================================================
                 EURON INSTITUTE OF TECHNOLOGY - GUIDED TOUR
==============================================================================

1. Users are created through @classmethod factories
------------------------------------------------------------------------------
[STUDENT        ] STU-0001 | Asha Rao | 2nd year of BSc Computer Science
[STUDENT        ] STU-0002 | Bilal Khan | 2nd year of BSc Computer Science
[STUDENT        ] STU-0003 | Chitra Iyer | 1st year of BCA
[STUDENT        ] STU-0004 | Deepak Nair | 3rd year of BSc Computer Science
[MENTOR         ] MEN-0005 | Ravi Kumar | Computer Science mentor | 0 course(s) | rating 4.6/5
[PREMIUM MENTOR ] PMN-0006 | Nisha Iyer | Mathematics mentor | 0 course(s) | rating 4.9/5 | premium 1:1 mentor | 0 session(s)

2. A mentor offers the catalogue (Course.offer derives the code)
------------------------------------------------------------------------------
CODE    | TITLE                       | LEVEL        | CR | SEATS | MENTOR
--------+-----------------------------+--------------+----+-------+-----------
OOP-100 | Object Oriented Programming | Foundation   |  4 | 0/3   | Ravi Kumar
ADS-300 | Advanced Data Structures    | Advanced     |  4 | 0/2   | Nisha Iyer
DMS-200 | Database Management Systems | Intermediate |  3 | 0/25  | Ravi Kumar

3. Enrollment validates every rule of the registry
------------------------------------------------------------------------------
  blocked: duplicate enrollment is rejected
           DuplicateEnrollmentError: Asha Rao is already in OOP-100
  blocked: Deepak Nair skips the OOP-100 prerequisite
           PrerequisiteError: Deepak Nair must complete OOP-100 before joining ADS-300
  blocked: OOP-100 is full
           CapacityFullError: OOP-100 is full (3/3 seats taken)

4. Students submit work, mentors award grades (state machine)
------------------------------------------------------------------------------
  Asha Rao     score=93.0   grade=O (Outstanding)
  Bilal Khan   score=78.0   grade=A (Very Good)
  Chitra Iyer  score=64.0   grade=B+ (Good)
  blocked: a completed record cannot be re-graded
           RecordLockedError: ENR-0001 is completed; Asha Rao already has a final grade for OOP-100

5. Prerequisites unlock, premium mentors may exceed capacity
------------------------------------------------------------------------------
  Asha Rao completed OOP-100 -> may now join ADS-300
  blocked: ADS-300 is full
           CapacityFullError: ADS-300 is full (2/2 seats taken)
  Nisha Iyer (premium) overrode the seat limit of ADS-300
  rejected: Only students can book a mentoring session

6. Dropping frees the seat but keeps the audit trail
------------------------------------------------------------------------------
  ENR-0006 -> DROPPED
  seats left in ADS-300: 0 (the transcript keeps the record)

7. One call, many behaviours (polymorphism)
------------------------------------------------------------------------------
  [student] Asha Rao <asha@eurotech.edu> :: Mid-term examination schedule is published [all]
  [student] Bilal Khan <bilal@eurotech.edu> :: Mid-term examination schedule is published [all]
  [mentor] Ravi Kumar <ravi.kumar@eurotech.edu> :: Mid-term examination schedule is published [all]
  [premium-priority] Nisha Iyer :: Mid-term examination schedule is published [all]

8. Reports are built from @staticmethod renderers
------------------------------------------------------------------------------
OOP-100 | Object Oriented Programming (Foundation)
mentor : Ravi Kumar
seats  : 0/3 taken | fee INR 1,500
--------------------------------------------------------------------
   1. Asha Rao           COMPLETED  score=  93.0 grade=O
   2. Bilal Khan         COMPLETED  score=  78.0 grade=A
   3. Chitra Iyer        COMPLETED  score=  64.0 grade=B+
--------------------------------------------------------------------
  average score 78.33 | pass rate 100.0%

Transcript for Asha Rao (STU-0001)
--------------------------------------------------------------
OOP-100    Object Oriented Programming    4cr  O   COMPLETED
ADS-300    Advanced Data Structures       4cr  --  ENROLLED
--------------------------------------------------------------
GPA: 10.00   Standing: Outstanding

9. Every domain error derives from CMSError
------------------------------------------------------------------------------
  invalid e-mail -> ValidationError: 'not-an-email' is not a valid e-mail address
  bad year       -> ValidationError: Year must be an integer between 1 and 4, got 9
  unknown user   -> UnknownUserError: 'Nobody' is not a student
  closed batch   -> EnrollmentClosedError: STL-100 enrollment window is closed
  unknown grade  -> ValidationError: Unknown grade 'Z'
```

`python3 main.py dashboard` — the whole term on one screen:

```
==============================================================================
              EURON INSTITUTE OF TECHNOLOGY - ACADEMIC DASHBOARD
==============================================================================

Key figures
------------------------------------------------------------------------------
METRIC                      | VALUE
----------------------------+------
students admitted           |     8
mentors on faculty          |     3
courses offered             |     5
enrollment records          |    18
graded records              |    15
campus average score        |  78.4
campus average grade points |  8.33
average seat occupancy %    | 13.83

Course catalogue
------------------------------------------------------------------------------
CODE    | TITLE                       | LEVEL        | CR | SEATS | MENTOR
--------+-----------------------------+--------------+----+-------+--------------
PP-100  | Python Programming          | Foundation   |  3 | 1/40  | Ravi Kumar
OOP-100 | Object Oriented Programming | Foundation   |  4 | 0/3   | Ravi Kumar
AD-200  | Algorithm Design            | Intermediate |  4 | 0/8   | Ravi Kumar
DMS-200 | Database Management Systems | Intermediate |  3 | 1/2   | Nisha Iyer
DC-100  | Digital Circuits            | Foundation   |  3 | 1/6   | Farida Sheikh

Top performers
------------------------------------------------------------------------------
RANK | STUDENT      | ID       |  GPA | STANDING
-----+--------------+----------+------+------------
   1 | Asha Rao     | STU-0001 | 9.67 | Outstanding
   2 | Geetha Menon | STU-0007 | 9.00 | Outstanding
   3 | Esha Verma   | STU-0005 | 9.00 | Outstanding

Mentor workload
------------------------------------------------------------------------------
MENTOR        | ROLE           | DEPARTMENT       | COURSES | RATING | TEACHES
--------------+----------------+------------------+---------+--------+-----------------
Nisha Iyer    | premium mentor | Mathematics      |       1 |    4.9 | DMS-200
Ravi Kumar    | mentor         | Computer Science |       3 |    4.6 | PP-100, OOP-100, AD-200
Farida Sheikh | mentor         | Electronics      |       1 |    4.1 | DC-100
```

### What the output proves

| Observation | Concept proven |
| --- | --- |
| One `describe()` line per user, identical layout, different tail | Template method + polymorphism |
| `STU-0001` / `MEN-0005` / `PMN-0006` allocated by factories | `@classmethod` with shared class state |
| `OOP-100`, `ADS-300`, `DMS-200` derived from titles | `@staticmethod` catalogue rules |
| Every rejected action names a specific exception subclass | Encapsulated invariants + exception hierarchy |
| `grade=O`, `COMPLETED`, then `RecordLockedError` on re-grade | Encapsulated state machine |
| Premium mentor overrides the seat limit; a plain mentor cannot | Polymorphic permissions instead of `if role ==` |
| `[student] … [premium-priority] …` from one `broadcast` call | Polymorphism over a heterogeneous collection |
| Transcript keeps a `DROPPED` row while the seat is released | Audit trail as a design goal |

---

## 10. Testing and quality gates

| Gate | Command | Status |
| --- | --- | --- |
| Unit tests | `python3 -m unittest discover -s tests` | 93 passed |
| Lint | `python3 -m ruff check .` | clean |
| Format | `python3 -m ruff format --check .` | clean |
| Types | `python3 -m mypy .` | no issues, 15 files |

The suite is organised by concept rather than by class, so the mapping to the brief is explicit:

| Suite | What it proves |
| --- | --- |
| `tests/test_user.py` | `User` is abstract; private state; `@staticmethod` validators; `@classmethod` factories; value equality |
| `tests/test_roles.py` | `User → Mentor → PremiumMentor` chain; overridden `role`/`duties`/`notify`/`profile`; permission sets; operator sorting |
| `tests/test_course_enrollment.py` | duplicate, capacity, prerequisite and closed-window rules; the full state machine; `RecordLockedError` guards; premium override |
| `tests/test_academy_cli.py` | registry lookups, broadcast audiences, report renderers, every shell command, domain errors reported instead of crashing |

---

## 11. What I would do next

1. **Persistence** — replace the `Academy` dicts with a repository over SQLite; the domain model needs
   no change, which is the point of the layering.
2. **A `waitlist`** — `Course.enroll` currently rejects at capacity; a `Waitlist` class would make
   promotion when a seat frees up a first-class event.
3. **Attendance and assignments** — `Assignment` and `AttendanceRecord` would compose with
   `Enrollment` instead of extending it.
4. **Role-based authorisation at the boundary** — map `permissions()` to a real auth layer so the
   same policy drives the UI.
5. **A `TimeTable` class** — schedule conflicts between mentors and rooms, another good showcase of a
   non-trivial invariant.
