"""The Reports summary (user decision 2026-11-16): built from the full reports, with a status per study and
a short detail behind every card, ring and study (demo data; no AI)."""

from __future__ import annotations

from fastapi.testclient import TestClient

API = "/api/v1/reports"


def test_summary_matches_the_full_reports(client: TestClient) -> None:
    body = client.get(f"{API}/summary").json()
    cards = {c["key"]: c for c in body["cards"]}
    assert list(cards) == ["enrolment", "milestones", "issues", "deviations"]
    delivery = client.get(f"{API}/study-delivery").json()
    overdue = next(t for t in delivery["tiles"] if t["key"] == "overdue")
    assert cards["milestones"]["value"] == overdue["value"]
    risks = client.get(f"{API}/risks-issues").json()
    assert cards["issues"]["value"] == next(t for t in risks["tiles"] if t["key"] == "open")["value"]
    deviations = client.get(f"{API}/deviations").json()
    assert cards["deviations"]["value"] == next(t for t in deviations["tiles"] if t["key"] == "open")["value"]
    etmf = client.get(f"{API}/etmf").json()
    ring = next(r for r in body["rings"] if r["key"] == "etmf")
    assert ring["percent"] == etmf["overall"]["percent"]
    assert [r["key"] for r in body["rings"]] == ["etmf", "enrolment", "sites", "ontime"]
    # Enrolled uses the same rule as the Study delivery tile ("<enrolled> of <target>").
    enrol_tile = next(t for t in delivery["tiles"] if t["key"] == "enrolment")["value"]
    assert enrol_tile.startswith(cards["enrolment"]["value"] + " ")


def test_every_card_ring_and_study_has_a_detail(client: TestClient) -> None:
    body = client.get(f"{API}/summary").json()
    keys = [c["key"] for c in body["cards"]] + [r["key"] for r in body["rings"]]
    keys += [f"study:{s['id']}" for s in body["studies"]]
    for key in keys:
        detail = body["details"][key]
        assert (
            detail["title"]
            and detail["summary"]
            and detail["report"] in ("study", "risks", "deviations", "etmf")
        )
    assert body["details"]["issues"]["report"] == "risks"
    assert body["details"]["deviations"]["report"] == "deviations"
    study = body["studies"][0]
    assert body["details"][f"study:{study['id']}"]["study_id"] == study["id"]


def test_study_status_by_fixed_rules(client: TestClient) -> None:
    studies = client.get(f"{API}/summary").json()["studies"]
    assert len(studies) == 4 and all(s["reason"] for s in studies)
    order = {"off_track": 0, "at_risk": 1, "on_track": 2}
    assert [order[s["status"]] for s in studies] == sorted(order[s["status"]] for s in studies)
    delivery = client.get(f"{API}/study-delivery").json()
    overdue = {m["study_id"] for m in delivery["milestones"] if m["state"] == "overdue"}
    for s in studies:
        assert (s["status"] == "off_track") == (s["id"] in overdue)


def test_one_study(client: TestClient) -> None:
    study_id = client.get(f"{API}/study-delivery").json()["study_options"][0]["id"]
    body = client.get(f"{API}/summary", params={"study_id": study_id}).json()
    assert [s["id"] for s in body["studies"]] == [study_id]


def test_enrolment_months_from_the_daily_figures(client: TestClient) -> None:
    body = client.get(f"{API}/summary").json()
    assert len(body["enrolment"]) == 1 and body["enrolment"][0]["new"] is None  # first month: no "new"
    assert body["enrolment"][0]["total"] == int(body["cards"][0]["value"])


def test_needs_study_access(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.auth.rbac import Role

    assert make_client(Role.BUSINESS_DEVELOPMENT).get(f"{API}/summary").status_code == 403
