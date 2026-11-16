from .conftest import API, login, make_student


def _err(r):
    return r.json()["error"]["code"]


async def test_wishes_flow(client, db, student_headers, admin_headers):
    r = await client.post(
        f"{API}/wishes",
        json={"menu_name": "  마라탕 ", "reason": "친구들과 먹고 싶어요", "emoji": "🌶️"},
        headers=student_headers,
    )
    assert r.status_code == 201, r.text
    wish = r.json()
    assert wish["menu_name"] == "마라탕"
    assert wish["author"] == "1학년 익명"
    assert (wish["likes"], wish["liked"], wish["is_mine"]) == (0, False, True)

    await make_student(db, "20101", name="이영희", grade=2)
    other = await login(client, "20101")

    r = await client.post(f"{API}/wishes/{wish['id']}/like", headers=other)
    assert r.json() == {"id": wish["id"], "likes": 1, "liked": True}

    items = (await client.get(f"{API}/wishes", headers=other)).json()["items"]
    assert items[0]["liked"] is True and items[0]["is_mine"] is False
    assert "student_id" not in items[0]  # 작성자 신원 비노출

    r = await client.post(f"{API}/wishes/{wish['id']}/like", headers=other)
    assert r.json() == {"id": wish["id"], "likes": 0, "liked": False}

    # 다른 학생 글은 삭제 불가, 관리자는 가능
    r = await client.delete(f"{API}/wishes/{wish['id']}", headers=other)
    assert (r.status_code, _err(r)) == (403, "FORBIDDEN")
    r = await client.delete(f"{API}/admin/wishes/{wish['id']}", headers=admin_headers)
    assert r.status_code == 204
    r = await client.post(f"{API}/wishes/{wish['id']}/like", headers=other)
    assert (r.status_code, _err(r)) == (404, "WISH_NOT_FOUND")


async def test_wish_validation(client, student_headers):
    r = await client.post(
        f"{API}/wishes", json={"menu_name": "   ", "reason": "이유"}, headers=student_headers
    )
    assert (r.status_code, _err(r)) == (422, "VALIDATION_ERROR")
    r = await client.get(f"{API}/wishes")
    assert (r.status_code, _err(r)) == (401, "INVALID_TOKEN")


async def test_allergies(client, student_headers):
    r = await client.get(f"{API}/auth/me/allergies", headers=student_headers)
    assert r.json() == {"allergies": [], "registered": False}

    r = await client.put(
        f"{API}/auth/me/allergies", json={"allergies": []}, headers=student_headers
    )
    assert r.json() == {"allergies": [], "registered": True}  # '없음'으로 등록

    r = await client.put(
        f"{API}/auth/me/allergies",
        json={"allergies": ["우유", "달걀", "우유"]},
        headers=student_headers,
    )
    assert r.json() == {"allergies": ["우유", "달걀"], "registered": True}
    r = await client.get(f"{API}/auth/me/allergies", headers=student_headers)
    assert r.json()["allergies"] == ["우유", "달걀"]

    r = await client.put(
        f"{API}/auth/me/allergies", json={"allergies": ["민트초코"]}, headers=student_headers
    )
    assert (r.status_code, _err(r)) == (422, "VALIDATION_ERROR")
