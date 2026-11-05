from .conftest import API, make_student


def _err(r):
    return r.json()["error"]["code"]


async def test_csv_import_and_list(client, db, admin_headers):
    csv_bytes = (
        "student_no,name,grade,class_no\n"
        "10312,김철수,1,3\n"
        "10313,이영희,1,3\n"
        "1O312,오타,1,3\n"
        "20101,박민수,2,1\n"
    ).encode("utf-8-sig")
    r = await client.post(
        f"{API}/admin/allowed-students",
        headers=admin_headers,
        files={"file": ("s.csv", csv_bytes, "text/csv")},
        data={"mode": "append"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "inserted": 3,
        "skipped": 0,
        "errors": [{"row": 4, "reason": "학번 형식 오류: '1O312'"}],
    }

    # cp949 (Excel on Korean Windows) also accepted; existing rows skipped
    r = await client.post(
        f"{API}/admin/allowed-students",
        headers=admin_headers,
        files={
            "file": (
                "s.csv",
                "student_no,name,grade,class_no\n10312,김철수,1,3\n".encode("cp949"),
                "text/csv",
            )
        },
    )
    assert r.json()["skipped"] == 1

    r = await client.get(
        f"{API}/admin/allowed-students", params={"grade": 1}, headers=admin_headers
    )
    body = r.json()
    assert (body["total"], body["pages"]) == (2, 1)

    r = await client.post(
        f"{API}/admin/allowed-students",
        headers=admin_headers,
        files={"file": ("s.csv", b"no,name\n1,2\n", "text/csv")},
    )
    assert (r.status_code, _err(r)) == (422, "VALIDATION_ERROR")


async def test_disable_and_reset_password(client, db, admin_headers):
    s = await make_student(db, "10312")
    r = await client.patch(
        f"{API}/admin/students/{s.id}/status", json={"is_active": False}, headers=admin_headers
    )
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert "password_hash" not in r.json()

    r = await client.post(f"{API}/admin/students/{s.id}/reset-password", headers=admin_headers)
    body = r.json()
    assert body["must_change"] is True and len(body["temporary_password"]) == 8

    await client.patch(
        f"{API}/admin/students/{s.id}/status", json={"is_active": True}, headers=admin_headers
    )
    r = await client.post(
        f"{API}/auth/login", json={"student_no": "10312", "password": body["temporary_password"]}
    )
    assert r.status_code == 200
    me = await client.get(
        f"{API}/auth/me", headers={"Authorization": f"Bearer {r.json()['access_token']}"}
    )
    assert me.json()["must_change_password"] is True

    r = await client.get(f"{API}/admin/students", headers=admin_headers)
    assert r.json()["total"] == 1  # admins excluded by default
