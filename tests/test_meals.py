from .conftest import API, login, make_student

DAY = {
    "service_date": "2026-09-14",
    "breakfast_available": True,
    "breakfast_deadline": "2026-09-13T09:00:00Z",
    "breakfast_menu": "미역국, 계란말이, 김치, 흰쌀밥",
    "dinner_available": True,
    "dinner_deadline": "2026-09-14T03:00:00Z",
    "dinner_menu": "치킨마요덮밥, 유부장국, 단무지",
}


def _err(r):
    return r.json()["error"]["code"]


async def _setup_calendar(client, admin_headers):
    r = await client.post(
        f"{API}/admin/meal-calendar",
        json=[
            DAY,
            {
                "service_date": "2026-09-15",
                "breakfast_available": True,
                "breakfast_deadline": "2026-09-14T09:00:00Z",
                "dinner_available": False,
                "dinner_reason": "exam_period",
            },
        ],
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text


async def test_calendar_view(client, admin_headers, student_headers, fake_clock):
    await _setup_calendar(client, admin_headers)
    r = await client.get(
        f"{API}/meal-calendar",
        params={"from": "2026-09-14", "to": "2026-09-19"},
        headers=student_headers,
    )
    assert r.status_code == 200, r.text
    items = {i["service_date"]: i for i in r.json()["items"]}
    assert len(items) == 6
    assert items["2026-09-14"]["breakfast"] == {
        "available": True,
        "reason": None,
        "selectable_from": "2026-08-31",
        "deadline": "2026-09-13T09:00:00Z",
        "menu": "미역국, 계란말이, 김치, 흰쌀밥",
    }
    assert items["2026-09-15"]["dinner"]["reason"] == "exam_period"
    assert items["2026-09-16"]["breakfast"]["reason"] == "no_service"
    assert items["2026-09-19"]["breakfast"]["reason"] == "weekend"  # Saturday

    r = await client.get(
        f"{API}/meal-calendar",
        params={"from": "2026-09-01", "to": "2026-09-20"},
        headers=student_headers,
    )
    assert (r.status_code, _err(r)) == (422, "VALIDATION_ERROR")


async def test_signup_window_kst(client, admin_headers, student_headers, fake_clock):
    await _setup_calendar(client, admin_headers)
    body = {"service_date": "2026-09-14", "meal_type": "breakfast", "will_attend": True}

    # 2026-08-30T15:00Z = 2026-08-31 00:00 KST -> exactly selectable_from
    fake_clock.set("2026-08-30T14:59:59Z")  # still 08-30 in KST
    r = await client.put(f"{API}/meal-signups", json=body, headers=student_headers)
    assert (r.status_code, _err(r)) == (400, "DATE_OUT_OF_RANGE")

    fake_clock.set("2026-08-30T15:00:00Z")
    r = await client.put(f"{API}/meal-signups", json=body, headers=student_headers)
    assert r.status_code == 200, r.text
    assert r.json()["is_locked"] is False

    # upsert: change mind, no "already signed up" error
    fake_clock.set("2026-09-12T11:20:00Z")
    r = await client.put(
        f"{API}/meal-signups", json={**body, "will_attend": False}, headers=student_headers
    )
    assert r.status_code == 200
    assert r.json() == {
        **body,
        "will_attend": False,
        "is_locked": False,
        "updated_at": "2026-09-12T11:20:00Z",
    }

    fake_clock.set("2026-09-13T09:00:00Z")  # == deadline
    r = await client.put(f"{API}/meal-signups", json=body, headers=student_headers)
    assert (r.status_code, _err(r)) == (403, "SIGNUP_DEADLINE_PASSED")

    r = await client.put(
        f"{API}/meal-signups",
        headers=student_headers,
        json={"service_date": "2026-09-15", "meal_type": "dinner", "will_attend": True},
    )
    assert (r.status_code, _err(r)) == (400, "MEAL_NOT_AVAILABLE")

    r = await client.get(
        f"{API}/meal-signups",
        params={"from": "2026-09-14", "to": "2026-09-15"},
        headers=student_headers,
    )
    assert r.json()["items"] == [
        {
            "service_date": "2026-09-14",
            "meal_type": "breakfast",
            "will_attend": False,
            "is_locked": True,
            "updated_at": "2026-09-12T11:20:00Z",
        }
    ]


async def test_bulk_partial_success(client, admin_headers, student_headers, fake_clock):
    await _setup_calendar(client, admin_headers)
    fake_clock.set("2026-09-13T10:00:00Z")  # breakfast 14 closed, dinner 14 open
    r = await client.put(
        f"{API}/meal-signups/bulk",
        headers=student_headers,
        json={
            "signups": [
                {"service_date": "2026-09-14", "meal_type": "breakfast", "will_attend": True},
                {"service_date": "2026-09-14", "meal_type": "dinner", "will_attend": False},
                {"service_date": "2026-09-15", "meal_type": "breakfast", "will_attend": True},
            ]
        },
    )
    assert r.status_code == 200
    assert r.json() == {
        "succeeded": 2,
        "failed": 1,
        "results": [
            {
                "service_date": "2026-09-14",
                "meal_type": "breakfast",
                "status": "error",
                "code": "SIGNUP_DEADLINE_PASSED",
            },
            {"service_date": "2026-09-14", "meal_type": "dinner", "status": "ok", "code": None},
            {"service_date": "2026-09-15", "meal_type": "breakfast", "status": "ok", "code": None},
        ],
    }


async def test_summary_snapshot_is_frozen(client, db, admin_headers, student_headers, fake_clock):
    await _setup_calendar(client, admin_headers)
    await make_student(db, "20101", name="이영희", grade=2, class_no=1)
    await make_student(db, "30101", name="박민수", grade=3, class_no=1)
    h2 = await login(client, "20101")

    fake_clock.set("2026-09-12T00:00:00Z")
    for h, attend in ((student_headers, True), (h2, False)):
        r = await client.put(
            f"{API}/meal-signups",
            headers=h,
            json={"service_date": "2026-09-14", "meal_type": "breakfast", "will_attend": attend},
        )
        assert r.status_code == 200

    r = await client.get(
        f"{API}/admin/meal-signups/summary", params={"date": "2026-09-14"}, headers=admin_headers
    )
    b = r.json()["breakfast"]
    assert (b["attending"], b["not_attending"], b["no_response"], b["is_finalized"]) == (
        1,
        1,
        1,
        False,
    )

    fake_clock.set("2026-09-13T09:30:00Z")  # after breakfast deadline
    r = await client.get(
        f"{API}/admin/meal-signups/summary",
        params={"date": "2026-09-14", "meal_type": "breakfast"},
        headers=admin_headers,
    )
    data = r.json()
    assert data["dinner"] is None
    b = data["breakfast"]
    assert b["is_finalized"] is True and b["finalized_at"] == "2026-09-13T09:00:00Z"
    assert b["by_grade"] == [{"grade": 1, "attending": 1}, {"grade": 2, "attending": 0}]

    # A new student joins after finalization; the frozen number must not change.
    await make_student(db, "10399", name="신입생")
    r = await client.get(
        f"{API}/admin/meal-signups/summary",
        params={"date": "2026-09-14", "meal_type": "breakfast"},
        headers=admin_headers,
    )
    assert r.json()["breakfast"]["no_response"] == 1


async def test_export_csv_has_bom(client, admin_headers, student_headers, fake_clock):
    await _setup_calendar(client, admin_headers)
    fake_clock.set("2026-09-12T00:00:00Z")
    await client.put(
        f"{API}/meal-signups",
        headers=student_headers,
        json={"service_date": "2026-09-14", "meal_type": "breakfast", "will_attend": True},
    )
    r = await client.get(
        f"{API}/admin/meal-signups/export",
        params={"date": "2026-09-14", "meal_type": "breakfast"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.content.startswith(b"\xef\xbb\xbf")
    assert r.headers["content-disposition"] == 'attachment; filename="breakfast_20260914.csv"'
    text = r.content.decode("utf-8-sig")
    assert text.splitlines() == ["학번,이름,학년,반,신청", "10312,김철수,1,3,식사"]

    r = await client.get(
        f"{API}/admin/meal-signups/export",
        params={"date": "2026-09-14", "meal_type": "breakfast", "format": "xlsx"},
        headers=admin_headers,
    )
    assert r.status_code == 200 and r.content[:2] == b"PK"
