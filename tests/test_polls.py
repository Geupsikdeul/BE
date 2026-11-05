import asyncio

from .conftest import API, login, make_student

POLL = {
    "title": "10월 3주차 중식 메뉴 투표",
    "description": "가장 먹고 싶은 메뉴 하나를 골라주세요.",
    "target_date": "2026-10-16",
    "opens_at": "2026-10-08T00:00:00Z",
    "closes_at": "2026-10-13T05:00:00Z",
    "options": [
        {"menu_name": "돈까스", "description": "돈까스, 우동, 단무지, 흰쌀밥"},
        {"menu_name": "제육볶음", "description": "제육볶음, 계란국, 콩나물무침, 흰쌀밥"},
    ],
}


def _err(r):
    return r.json()["error"]["code"]


async def _published_poll(client, admin_headers, **overrides) -> dict:
    r = await client.post(f"{API}/admin/polls", json={**POLL, **overrides}, headers=admin_headers)
    assert r.status_code == 201, r.text
    poll = r.json()
    assert poll["is_published"] is False
    r = await client.post(f"{API}/admin/polls/{poll['id']}/publish", headers=admin_headers)
    assert r.status_code == 200
    return poll


async def test_admin_routes_require_admin(client, student_headers):
    r = await client.get(f"{API}/admin/polls", headers=student_headers)
    assert (r.status_code, _err(r)) == (403, "FORBIDDEN")
    r = await client.get(
        f"{API}/admin/meal-signups/summary", params={"date": "2026-09-14"}, headers=student_headers
    )
    assert r.status_code == 403
    r = await client.get(f"{API}/admin/polls")
    assert r.status_code == 401


async def test_every_admin_route_rejects_students(client, student_headers):
    """Router-level require_admin: every /admin/* operation must answer 403 to a student."""
    from geupsikdeul_backend.main import app

    ops = [
        (
            method,
            path.replace("{poll_id}", "1")
            .replace("{student_id}", "1")
            .replace("{service_date}", "2026-09-14"),
        )
        for path, methods in app.openapi()["paths"].items()
        if path.startswith(f"{API}/admin")
        for method in methods
    ]
    assert len(ops) >= 15
    for method, path in ops:
        r = await client.request(method.upper(), path, headers=student_headers)
        assert (r.status_code, _err(r)) == (403, "FORBIDDEN"), (method, path)


async def test_create_poll_validation(client, admin_headers):
    r = await client.post(
        f"{API}/admin/polls",
        headers=admin_headers,
        json={**POLL, "closes_at": "2026-10-01T00:00:00Z"},
    )
    assert (r.status_code, _err(r)) == (400, "INVALID_PERIOD")
    r = await client.post(
        f"{API}/admin/polls", headers=admin_headers, json={**POLL, "options": POLL["options"][:1]}
    )
    assert (r.status_code, _err(r)) == (400, "TOO_FEW_OPTIONS")


async def test_vote_lifecycle(client, db, admin_headers, student_headers, fake_clock):
    poll = await _published_poll(client, admin_headers)
    pid, (o1, o2) = poll["id"], [o["id"] for o in poll["options"]]

    # scheduled
    fake_clock.set("2026-10-07T00:00:00Z")
    r = await client.post(
        f"{API}/polls/{pid}/vote", json={"option_id": o1}, headers=student_headers
    )
    assert (r.status_code, _err(r)) == (403, "POLL_NOT_OPEN")
    r = await client.get(f"{API}/polls", headers=student_headers)
    assert r.json()["total"] == 0  # default filter = open

    fake_clock.set("2026-10-10T00:00:00Z")
    r = await client.get(f"{API}/polls", headers=student_headers)
    item = r.json()["items"][0]
    assert (item["status"], item["has_voted"], item["total_votes"]) == ("open", False, 0)

    r = await client.post(
        f"{API}/polls/{pid}/vote", json={"option_id": 99999}, headers=student_headers
    )
    assert (r.status_code, _err(r)) == (400, "INVALID_OPTION")

    r = await client.post(
        f"{API}/polls/{pid}/vote", json={"option_id": o1}, headers=student_headers
    )
    assert r.status_code == 201
    assert r.json() == {"poll_id": pid, "option_id": o1, "voted_at": "2026-10-10T00:00:00Z"}

    r = await client.post(
        f"{API}/polls/{pid}/vote", json={"option_id": o2}, headers=student_headers
    )
    assert (r.status_code, _err(r)) == (409, "VOTE_ALREADY_CAST")

    # detail: own choice visible, no per-option counts before close
    r = await client.get(f"{API}/polls/{pid}", headers=student_headers)
    d = r.json()
    assert (d["has_voted"], d["my_option_id"]) == (True, o1)
    assert all("vote_count" not in o for o in d["options"])

    # change vote
    r = await client.put(f"{API}/polls/{pid}/vote", json={"option_id": o2}, headers=student_headers)
    assert r.status_code == 200 and r.json()["option_id"] == o2

    r = await client.get(f"{API}/polls/{pid}/result", headers=student_headers)
    assert (r.status_code, _err(r)) == (403, "RESULT_NOT_AVAILABLE")

    # second student votes o2 too; third votes o1
    for no, opt in (("10313", o2), ("10314", o1)):
        await make_student(db, no, name="학생")
        h = await login(client, no)
        r = await client.post(f"{API}/polls/{pid}/vote", json={"option_id": opt}, headers=h)
        assert r.status_code == 201

    fake_clock.set("2026-10-13T05:00:00Z")  # exactly at closes_at -> closed
    r = await client.post(
        f"{API}/polls/{pid}/vote", json={"option_id": o1}, headers=student_headers
    )
    assert _err(r) == "POLL_NOT_OPEN"
    r = await client.get(f"{API}/polls/{pid}/result", headers=student_headers)
    assert r.status_code == 200
    res = r.json()
    assert res["total_votes"] == 3
    by_id = {x["option_id"]: x for x in res["results"]}
    assert by_id[o2] == {
        "option_id": o2,
        "menu_name": "제육볶음",
        "vote_count": 2,
        "percentage": 66.7,
        "is_winner": True,
    }
    assert by_id[o1]["is_winner"] is False


async def test_concurrent_votes_only_one_succeeds(
    client, admin_headers, student_headers, fake_clock
):
    poll = await _published_poll(client, admin_headers)
    fake_clock.set("2026-10-10T00:00:00Z")
    o1 = poll["options"][0]["id"]
    rs = await asyncio.gather(
        *[
            client.post(
                f"{API}/polls/{poll['id']}/vote", json={"option_id": o1}, headers=student_headers
            )
            for _ in range(5)
        ]
    )
    codes = sorted(r.status_code for r in rs)
    assert codes == [201, 409, 409, 409, 409]


async def test_unpublished_poll_hidden(client, admin_headers, student_headers):
    r = await client.post(f"{API}/admin/polls", json=POLL, headers=admin_headers)
    pid = r.json()["id"]
    r = await client.get(f"{API}/polls/{pid}", headers=student_headers)
    assert (r.status_code, _err(r)) == (404, "POLL_NOT_FOUND")


async def test_admin_stats_nonvoters_delete_close(
    client, db, admin_headers, student_headers, fake_clock
):
    poll = await _published_poll(client, admin_headers)
    pid, o1 = poll["id"], poll["options"][0]["id"]
    await make_student(db, "20101", name="이영희", grade=2, class_no=1)

    # options can be edited before start
    fake_clock.set("2026-10-01T00:00:00Z")
    r = await client.patch(
        f"{API}/admin/polls/{pid}",
        headers=admin_headers,
        json={"options": [{"menu_name": "A"}, {"menu_name": "B"}, {"menu_name": "C"}]},
    )
    assert r.status_code == 200 and len(r.json()["options"]) == 3
    o1 = r.json()["options"][0]["id"]

    fake_clock.set("2026-10-10T00:00:00Z")
    r = await client.patch(
        f"{API}/admin/polls/{pid}",
        headers=admin_headers,
        json={"options": [{"menu_name": "X"}, {"menu_name": "Y"}]},
    )
    assert (r.status_code, _err(r)) == (409, "POLL_ALREADY_STARTED")
    r = await client.patch(
        f"{API}/admin/polls/{pid}", headers=admin_headers, json={"title": "수정된 제목"}
    )
    assert r.status_code == 200 and r.json()["title"] == "수정된 제목"

    await client.post(f"{API}/polls/{pid}/vote", json={"option_id": o1}, headers=student_headers)

    r = await client.get(f"{API}/admin/polls/{pid}/stats", headers=admin_headers)
    s = r.json()
    assert (s["total_votes"], s["eligible_students"], s["participation_rate"]) == (1, 2, 50.0)
    assert s["by_grade"] == [
        {"grade": 1, "voted": 1, "eligible": 1, "rate": 100.0},
        {"grade": 2, "voted": 0, "eligible": 1, "rate": 0.0},
    ]
    assert "student" not in str(s["by_option"])  # aggregate only

    r = await client.get(f"{API}/admin/polls/{pid}/non-voters", headers=admin_headers)
    assert r.json() == {
        "items": [{"student_no": "20101", "name": "이영희", "grade": 2, "class_no": 1}],
        "total": 1,
    }

    r = await client.delete(f"{API}/admin/polls/{pid}", headers=admin_headers)
    assert (r.status_code, _err(r)) == (409, "POLL_HAS_VOTES")

    r = await client.post(f"{API}/admin/polls/{pid}/close", headers=admin_headers)
    assert r.json()["status"] == "closed"
    r = await client.get(f"{API}/polls/{pid}/result", headers=student_headers)
    assert r.status_code == 200

    other = await _published_poll(client, admin_headers)
    r = await client.delete(f"{API}/admin/polls/{other['id']}", headers=admin_headers)
    assert r.status_code == 204
