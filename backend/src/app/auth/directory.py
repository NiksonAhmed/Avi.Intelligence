"""People who can be assigned tasks and risks.

Until Microsoft Entra ID sign-in exists this is a fixed demo directory. With Entra, people will come
from the tenant directory (Microsoft Graph) and their ids will be Entra object ids; the rest of the
code only depends on `list_people()` and `get_person()`.
"""

from __future__ import annotations

from pydantic import BaseModel


class Person(BaseModel):
    id: str
    name: str
    email: str
    job_title: str
    demo: bool = True


DEMO_PEOPLE: tuple[Person, ...] = (
    Person(id="dev-user", name="Local Developer", email="dev@localhost", job_title="Developer (you)"),
    Person(id="demo-pm-1", name="Demo PM One", email="pm1@demo.invalid", job_title="Project Manager"),
    Person(id="demo-pm-2", name="Demo PM Two", email="pm2@demo.invalid", job_title="Project Manager"),
    Person(
        id="demo-cra-1",
        name="Demo CRA One",
        email="cra1@demo.invalid",
        job_title="Clinical Research Associate",
    ),
    Person(
        id="demo-cra-2",
        name="Demo CRA Two",
        email="cra2@demo.invalid",
        job_title="Clinical Research Associate",
    ),
    Person(id="demo-dm-1", name="Demo Data Manager", email="dm1@demo.invalid", job_title="Data Manager"),
    Person(
        id="demo-safety-1", name="Demo Safety Lead", email="safety1@demo.invalid", job_title="Safety / PV"
    ),
)


def list_people() -> list[Person]:
    return list(DEMO_PEOPLE)


def get_person(person_id: str) -> Person | None:
    return next((p for p in DEMO_PEOPLE if p.id == person_id), None)
