from datetime import timedelta

from app.models import AllowedStudent

from .conftest import API, PASSWORD, login, make_student


async def _allow(db, no="10312", name="김철수"):
    db.add(AllowedStudent(student_no=no, name=name, grade=1, class_no=3))
    await db.commit()


def _err(r):
    return r.json()["error"]["code"]


async def test_check_student_no_masks_name(client, db):
    await _allow(db)
    r = await client.get(f"{API}/auth/check-student-no", params={"student_no": "10312"})
    assert r.status_code == 200
    assert r.json() == {
        "student_no": "10312",
        "name": "김*수",
        "grade": 1,
        "class_no": 3,
        "available": True,
    }
    r = await client.get(f"{API}/auth/check-student-no", params={"student_no": "99999"})
    assert (r.status_code, _err(r)) == (404, "STUDENT_NOT_ALLOWED")


async def test_signup_flow_and_errors(client, db):
    await _allow(db)
    body = {"student_no": "10312", "name": "김철수", "password": PASSWORD, "privacy_agreed": True}

    r = await client.post(f"{API}/auth/signup", json={**body, "privacy_agreed": False})
    assert (r.status_code, _err(r)) == (400, "PRIVACY_NOT_AGREED")
    r = await client.post(f"{API}/auth/signup", json={**body, "name": "김영수"})
    assert (r.status_code, _err(r)) == (400, "STUDENT_NAME_MISMATCH")
    r = await client.post(f"{API}/auth/signup", json={**body, "password": "short1"})
    assert (r.status_code, _err(r)) == (422, "WEAK_PASSWORD")
    r = await client.post(f"{API}/auth/signup", json={**body, "password": "onlyletters"})
    assert _err(r) == "WEAK_PASSWORD"
    r = await client.post(f"{API}/auth/signup", json={**body, "student_no": "99999"})
    assert (r.status_code, _err(r)) == (404, "STUDENT_NOT_ALLOWED")

    r = await client.post(f"{API}/auth/signup", json={**body, "grade": 3, "class_no": 9})
    assert r.status_code == 201, r.text
    data = r.json()
    assert (data["grade"], data["class_no"], data["role"]) == (1, 3, "student")  # from whitelist
    assert "password_hash" not in data and "password" not in data
    assert data["created_at"].endswith("Z")

    r = await client.post(f"{API}/auth/signup", json=body)
    assert (r.status_code, _err(r)) == (409, "STUDENT_ALREADY_REGISTERED")
    r = await client.get(f"{API}/auth/check-student-no", params={"student_no": "10312"})
    assert (r.status_code, _err(r)) == (409, "STUDENT_ALREADY_REGISTERED")


async def test_login_me_refresh(client, db):
    await make_student(db, "10312")
    r = await client.post(f"{API}/auth/login", json={"student_no": "10312", "password": PASSWORD})
    assert r.status_code == 200
    tokens = r.json()
    assert tokens["token_type"] == "bearer" and tokens["expires_in"] > 0

    me = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert me.status_code == 200 and me.json()["student_no"] == "10312"
    assert "password_hash" not in me.json()

    # refresh token can't be used as access token and vice versa
    r = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert (r.status_code, _err(r)) == (401, "INVALID_TOKEN")
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert _err(r) == "INVALID_TOKEN"
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200


async def test_access_token_expires(client, db, fake_clock, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "access_token_expire_minutes", 30)
    await make_student(db, "10312")
    headers = await login(client, "10312")
    fake_clock.current += timedelta(minutes=31)
    r = await client.get(f"{API}/auth/me", headers=headers)
    assert (r.status_code, _err(r)) == (401, "INVALID_TOKEN")


async def test_unknown_and_wrong_password_look_identical(client, db):
    await make_student(db, "10312")
    a = await client.post(
        f"{API}/auth/login", json={"student_no": "10312", "password": "Wrong1234"}
    )
    b = await client.post(
        f"{API}/auth/login", json={"student_no": "77777", "password": "Wrong1234"}
    )
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()


async def test_lockout_after_five_failures(client, db, fake_clock):
    await make_student(db, "10312")
    bad = {"student_no": "10312", "password": "Wrong1234"}
    for _ in range(5):
        assert (await client.post(f"{API}/auth/login", json=bad)).status_code == 401
    good = {"student_no": "10312", "password": PASSWORD}
    r = await client.post(f"{API}/auth/login", json=good)
    assert (r.status_code, _err(r)) == (429, "TOO_MANY_ATTEMPTS")
    fake_clock.current += timedelta(minutes=10, seconds=1)
    assert (await client.post(f"{API}/auth/login", json=good)).status_code == 200


async def test_disabled_account(client, db):
    s = await make_student(db, "10312")
    headers = await login(client, "10312")
    s.is_active = False
    await db.commit()
    r = await client.post(f"{API}/auth/login", json={"student_no": "10312", "password": PASSWORD})
    assert (r.status_code, _err(r)) == (403, "ACCOUNT_DISABLED")
    r = await client.get(f"{API}/auth/me", headers=headers)
    assert (r.status_code, _err(r)) == (403, "ACCOUNT_DISABLED")


async def test_change_password(client, student_headers):
    old = (
        await client.post(f"{API}/auth/login", json={"student_no": "10312", "password": PASSWORD})
    ).json()
    r = await client.patch(
        f"{API}/auth/password",
        headers=student_headers,
        json={"current_password": "nope", "new_password": "NewSecure5678!"},
    )
    assert (r.status_code, _err(r)) == (401, "INVALID_CREDENTIALS")
    r = await client.patch(
        f"{API}/auth/password",
        headers=student_headers,
        json={"current_password": PASSWORD, "new_password": "weak"},
    )
    assert (r.status_code, _err(r)) == (422, "WEAK_PASSWORD")
    r = await client.patch(
        f"{API}/auth/password",
        headers=student_headers,
        json={"current_password": PASSWORD, "new_password": "NewSecure5678!"},
    )
    assert r.status_code == 204

    # Tokens issued before the change are revoked (access and refresh).
    r = await client.get(f"{API}/auth/me", headers=student_headers)
    assert (r.status_code, _err(r)) == (401, "INVALID_TOKEN")
    r = await client.post(f"{API}/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert (r.status_code, _err(r)) == (401, "INVALID_TOKEN")

    r = await client.post(
        f"{API}/auth/login", json={"student_no": "10312", "password": "NewSecure5678!"}
    )
    assert r.status_code == 200
    new_headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert (await client.get(f"{API}/auth/me", headers=new_headers)).status_code == 200


async def test_missing_token_and_validation_format(client):
    r = await client.get(f"{API}/auth/me")
    assert r.status_code == 401
    assert r.json() == {
        "error": {
            "code": "INVALID_TOKEN",
            "message": "로그인이 만료되었습니다. 다시 로그인해 주세요.",
            "detail": None,
        }
    }
    r = await client.post(f"{API}/auth/login", json={"student_no": "10312"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "password" in r.json()["error"]["detail"]["fields"]
