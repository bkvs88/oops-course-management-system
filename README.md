# Course Management System — Python OOP Project

A production-shaped, in-memory **Course Management System (CMS)** built to demonstrate every core
Object-Oriented Programming concept in Python — *abstraction, encapsulation, inheritance,
polymorphism, instance methods, `@staticmethod` and `@classmethod`* — while solving a real domain
problem: running an academic term.

Students enroll in courses, mentors teach and grade them, prerequisites and capacity limits are
enforced by the model itself, and the whole term can be reported on with a single function call.

```
[STUDENT        ] STU-0001 | Asha Rao  | 2nd year of BSc Computer Science
[MENTOR         ] MEN-0005 | Ravi Kumar | Computer Science mentor | 2 course(s) | rating 4.6/5
[PREMIUM MENTOR ] PMN-0006 | Nisha Iyer | Mathematics mentor | 1 course(s) | rating 4.9/5 | premium 1:1 mentor
```

---

## Table of contents

- [Project description](#project-description)
- [Features](#features)
- [Architecture](#architecture)
- [Class reference](#class-reference)
- [Installation](#installation)
- [Usage](#usage)
- [Testing and quality gates](#testing-and-quality-gates)
- [OOP concepts at a glance](#oop-concepts-at-a-glance)
- [Project structure](#project-structure)
- [Git workflow](#git-workflow)
- [Further documentation](#further-documentation)

---

## Project description

A university training institute needs a system that manages one academic term:

| Actor | Responsibility |
| --- | --- |
| **Student** | Enrolls in courses, submits assignment scores, earns grades and credits, keeps a transcript |
| **Mentor** | Teaches courses, owns the roster, awards final grades |
| **PremiumMentor** | Everything a mentor can do, plus paid 1:1 sessions and the power to exceed a batch limit |
| **Course** | A bounded batch of seats with a prerequisite chain, a mentor and a grading policy |
| **Enrollment** | The seat itself: one student inside one course, with a grading state machine |
| **Academy** | In-memory registry and service layer (the only object the CLI talks to) |
| **Report** | Stateless renderers that turn the object graph into tables and dashboards |

**Zero runtime dependencies** — the project is written against the Python standard library only, so
`python3 main.py` is all you need. `pytest`, `ruff` and `mypy` are optional developer tooling.

---

## Features

**Domain rules enforced by the object model**

- No duplicate seat for the same student in the same course
- Hard capacity limit, with a permission-gated override for premium mentors
- Prerequisites must be **completed** (not merely enrolled) before enrolling in an advanced course
- Enrollment windows can be opened and closed per course
- An enrollment record is a state machine: `ENROLLED → SUBMITTED → COMPLETED | DROPPED`
- A finalized record is locked: it cannot be re-graded, re-submitted or dropped
- Only the assigned mentor may grade, and only a student may be graded

**Academic features**

- Percentage → letter grade → grade points policy in one place (`Enrollment.GRADE_SCALE`)
- GPA, academic standing, credit load, transcript rendering
- Course level inference (Foundation / Intermediate / Advanced) and derived course codes (`OOP-100`)
- Per-course analytics: average score, pass percentage, seat occupancy
- Risk list of students below a GPA threshold, top performers, mentor workload

**Application features**

- Guided demo, single-screen dashboard and an interactive shell
- Structured activity log of every registry action
- Broadcast notifications where each role formats the message its own way
- 93 unit tests, `ruff`, `ruff format` and strict `mypy` all clean

---

## Architecture

Layered, bottom-up. Each layer only knows the layer below it, and circular imports are avoided with
`TYPE_CHECKING` blocks.

```
                        ┌──────────────────────────┐
   main.py  (CLI)  ───► │  Academy   (service)     │  ◄── facade / in-memory registry
                        ├──────────────────────────┤
                        │  Report    (renderers)   │  ◄── stateless @staticmethod views
                        └────────────┬─────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        │                            │                            │
┌───────▼────────┐          ┌────────▼─────────┐         ┌───────▼────────┐
│  Course        │◄─────────┤  Enrollment      │         │  Student       │
│  (aggregate)   │  creates │  (state machine) │◄────────│  Mentor        │
└───────┬────────┘          └──────────────────┘  owns   │  PremiumMentor │
        │ assigns mentor                              └───────▲────────┘
        │                                                         │ inherits
┌───────▼─────────────────────────────────────────────────────────▼──────┐
│  User  (abstract base: ABC)                                            │
│  exceptions (CMSError hierarchy)                                       │
└────────────────────────────────────────────────────────────────────────┘
```

**Relationship map**

```
User (ABC) ──► Student
         │
         └──► Mentor ──► PremiumMentor          (multi-level inheritance)

Course ──1..*──► Enrollment ──*..1──► Student
  │                     │
  │ assigns_mentor      └── graded_by ──► Mentor
  └──► Mentor (0..1)

Academy ──► holds Student / Mentor / Course registries
Report  ──► reads any of the above
```

**Design patterns used**

| Pattern | Where | Why |
| --- | --- | --- |
| Template Method | `User.describe()` calls the abstract `duties()` hook | Output layout defined once, details per role |
| Factory (classmethod) | `User.generate_id`, `Student.register`, `Mentor.appoint`, `Course.offer`, `Enrollment.open` | Allocation policy lives with the class, not the caller |
| Strategy via permissions | `Course.enroll(..., by=mentor)` + `mentor.can("override_capacity")` | Behaviour is decided by the role object, not an `if role ==` check |
| Facade | `Academy` | The CLI never touches two objects at once |
| Repository (in-memory) | private `dict` indexes inside `Academy` | Entities are resolved by id *or* by human name |
| Value Object | `Enrollment` | Immutable-by-convention record; all mutation goes through transitions |

---

## Class reference

| Class | File | Key members | OOP concepts demonstrated |
| --- | --- | --- | --- |
| `CMSError` and 8 subclasses | `cms/exceptions.py` | — | Exception hierarchy, single catch point |
| `User` (ABC) | `cms/user.py` | `role`, `permissions`, `duties` (abstract); `describe`, `can`, `notify`; `validate_email` (`@staticmethod`); `generate_id`, `from_record` (`@classmethod`) | **Abstraction**, **Encapsulation**, **@staticmethod**, **@classmethod**, **Polymorphism** |
| `Student` | `cms/student.py` | `enroll`, `drop`, `gpa`, `transcript`; `letter_grade` (`@staticmethod`); `register` (`@classmethod`) | **Inheritance**, **Instance methods**, Encapsulated ledger |
| `Mentor` | `cms/mentor.py` | `teach`, `grade`, `release`, `override_enroll`, `__lt__`; `appoint` (`@classmethod`) | Inheritance, permission checks, **operator overloading** |
| `PremiumMentor` | `cms/mentor.py` | `book_session`, `add_slot`; overrides `role`, `permissions`, `duties`, `notify`, `profile` | **Multi-level inheritance**, **Polymorphism** |
| `Course` | `cms/course.py` | `enroll`, `unenroll`, `grade_student`, `can_enroll`, `roster`; `build_code`, `infer_level` (`@staticmethod`); `offer` (`@classmethod`); `__len__`, `__iter__`, `__contains__` | Aggregate root, Encapsulation, **@staticmethod**, **@classmethod**, dunder protocol |
| `Enrollment` | `cms/enrollment.py` | `submit_score`, `award_grade`, `drop`; `letter_grade`, `grade_description` (`@staticmethod`); `open` (`@classmethod`) | Encapsulated state machine, **@staticmethod**, **@classmethod** |
| `Academy` | `cms/academy.py` | `admit_student`, `hire_mentor`, `offer_course`, `enroll`, `grade`, `broadcast` | Facade, polymorphism over a heterogeneous collection |
| `Report` | `cms/report.py` | `banner`, `table`, `courses`, `rosters`, `toppers`, `mentor_workload`, `dashboard` — all `@staticmethod` | **@staticmethod**, polymorphic rendering |
| `RecordWords` | `main.py` | `of` (`@classmethod`) | **@classmethod** in the entry point |

---

## Installation

**Requirements:** Python 3.10 or newer (developed and tested on 3.13). Nothing else is required.

```bash
# 1. clone the repository
git clone https://github.com/bkvs88/oops-course-management-system.git
cd oops-course-management-system

# 2. (optional) create a virtual environment
python3 -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate

# 3. (optional) install the developer tooling
pip install -r requirements.txt        # pytest, ruff, mypy

# 4. run it
python3 main.py demo
```

Running straight from a clone without installing anything also works — the package is a plain
`cms/` directory on the path.

---

## Usage

### 1. Guided demo (default)

```bash
python3 main.py demo
```

Walks through nine scenarios: user creation, catalogue setup, rejected enrollments, grading,
prerequisites, premium overrides, dropping, polymorphic broadcast, error handling and the final
dashboard.

### 2. One-screen dashboard

```bash
python3 main.py dashboard
```

Builds a full term (8 students, 3 mentors, 5 courses) and prints campus statistics, the catalogue,
top performers and mentor workload.

### 3. Interactive shell

```bash
python3 main.py shell
```

```
cms> students
cms> courses
cms> roster OOP-100
cms> enroll "Harish Babu" OOP-100
ENR-0020 Harish Babu -> OOP-100 [ENROLLED] score=-- grade=--
cms> submit "Harish Babu" OOP-100 77
ENR-0020 Harish Babu -> OOP-100 [SUBMITTED] score=77.0 grade=--
cms> grade "Ravi Kumar" "Harish Babu" OOP-100 77
ENR-0020 Harish Babu -> OOP-100 [COMPLETED] score=77.0 grade=A
cms> broadcast "Lab exam shifted to Friday" mentors
cms> quit
```

> Quote names that contain spaces — the shell parses input with `shlex`.

### 4. Use it as a library

```python
from cms.academy import Academy
from cms.exceptions import CMSError

academy = Academy()
asha = academy.admit_student("Asha Rao", "asha.rao@eurotech.edu", "BSc Computer Science", 2)
ravi = academy.hire_mentor("Ravi Kumar", "ravi.kumar@eurotech.edu", "Computer Science", 4.6)

oop = academy.offer_course("Object Oriented Programming", credits=4, capacity=2,
                           fee=1500, mentor=ravi)
ads = academy.offer_course("Advanced Data Structures", credits=4, capacity=2,
                           prerequisites=(oop.code,), mentor=ravi)

academy.enroll(asha, oop)
academy.submit_score(asha, oop, 93)
academy.grade(ravi, asha, oop, 93)

print(asha.transcript())
print(asha.gpa(), asha.academic_standing())        # 10.0 Outstanding
academy.enroll(asha, ads)                          # prerequisite satisfied

try:
    academy.enroll(asha, ads)
except CMSError as exc:
    print(type(exc).__name__, exc)                 # DuplicateEnrollmentError ...
```

### 5. Run the tests

```bash
python3 -m unittest discover -s tests -v      # stdlib runner
python3 -m pytest -q                          # if pytest is installed
```

---

## Testing and quality gates

| Gate | Command | Result |
| --- | --- | --- |
| Unit tests | `python3 -m unittest discover -s tests` | 93 passed |
| Lint | `python3 -m ruff check .` | clean |
| Format | `python3 -m ruff format --check .` | clean |
| Types | `python3 -m mypy .` | no issues (15 files) |

The suites are organised by concept — `test_user.py` (abstraction/encapsulation/static/classmethod),
`test_roles.py` (inheritance/polymorphism), `test_course_enrollment.py` (invariants and the state
machine), `test_academy_cli.py` (service layer, reports, CLI).

---

## OOP concepts at a glance

| Concept | Requirement | Where to look |
| --- | --- | --- |
| **Abstraction** | `User` is an ABC that cannot be instantiated; it declares `role`, `permissions`, `duties` | `cms/user.py:40`, `cms/user.py:84`, `tests/test_user.py::TestAbstraction` |
| **Encapsulation** | `__name`, `__email`, `__enrollments`, `__records` are private and only reachable via validating properties; immutable snapshots handed out | `cms/user.py:68`, `cms/course.py:134`, `cms/enrollment.py:253` |
| **Inheritance** | `Student(User)`, `Mentor(User)`, and multi-level `PremiumMentor(Mentor)` | `cms/student.py`, `cms/mentor.py` |
| **Polymorphism** | Method overriding (`role`, `duties`, `notify`, `profile`), duck typing in report writers, `super().permissions() \| {...}` | `cms/academy.py:189` (`broadcast`), `cms/mentor.py:263` |
| **Instance methods** | Every domain behaviour: `enroll`, `grade`, `gpa`, `roster`, `transcript` | `cms/student.py:106`, `cms/course.py:270` |
| **`@staticmethod`** | Validators, the grading policy, the table renderers — all stateless | `cms/enrollment.py:184`, `cms/report.py:45` |
| **`@classmethod`** | Factories that allocate ids or open records: `generate_id`, `register`, `appoint`, `hire`, `offer`, `open` | `cms/user.py:146`, `cms/course.py:359`, `cms/enrollment.py:218` |

---

## Project structure

```
oops-course-management-system/
├── cms/
│   ├── __init__.py       package docstring and version
│   ├── exceptions.py     CMSError hierarchy (validation, capacity, prereq, locking, permissions)
│   ├── user.py           abstract User base class (ABC)
│   ├── student.py        Student role
│   ├── mentor.py         Mentor and PremiumMentor roles
│   ├── course.py         Course aggregate root
│   ├── enrollment.py     Enrollment record and grading state machine
│   ├── academy.py        Academy service layer / in-memory registry
│   └── report.py         stateless report renderers
├── tests/
│   ├── test_user.py              abstraction, encapsulation, static/classmethods
│   ├── test_roles.py             inheritance and polymorphism
│   ├── test_course_enrollment.py domain invariants and state machine
│   └── test_academy_cli.py       service layer, reports, CLI
├── docs/
│   └── WALKTHROUGH.md   problem statement, OOP deep dive, Git workflow, full output
├── main.py               demo | dashboard | shell
├── pyproject.toml        packaging, ruff and mypy configuration
├── requirements.txt      optional developer tooling
├── .gitignore
└── README.md
```

---

## Git workflow

The project was built on `main` with one feature branch per concern, meaningful commits, explicit
`--no-ff` merges, and a Pull Request for the test + documentation work.

```
*   Merge branch 'feature/tests-and-documentation'      (Pull Request #1)
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

Commit messages follow **Conventional Commits** (`feat:`, `fix:`, `test:`, `docs:`, `chore:`) and
explain *why*, not just *what*. Branch naming is `feature/<topic>`.

---

## Further documentation

[`docs/WALKTHROUGH.md`](docs/WALKTHROUGH.md) is the long-form companion: the problem statement, the
architecture decision record, every OOP concept with the exact code that implements it, the complete
Git/GitHub workflow, how to execute the project, and the verified final output.

---

## License

MIT — free to use for learning, teaching and portfolio purposes.
