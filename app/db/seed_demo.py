"""Local/dev demo data so the frontend has something to show.

uv run python -m app.cli seed-demo     (refuses unless DEBUG=true)

Idempotent: existing rows are kept; only missing ones are added.
Accounts: student 10312 / demo1234, admin teacher01 / teacher1234
"""

from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.clock import KST
from app.core.security import hash_password
from app.models import AllowedStudent, MealCalendar, MealPoll, PollOption, Student, Wish
from app.models.enums import Role

DEMO_PASSWORD = "demo1234"
ADMIN_LOGIN, ADMIN_PASSWORD = "teacher01", "teacher1234"

STUDENTS = [  # (학번, 이름, 학년, 반, 계정 생성 여부)
    ("10312", "김하늘", 1, 3, True),
    ("20105", "이서준", 2, 1, True),
    ("30220", "박지우", 3, 2, True),
    ("10101", "최민준", 1, 1, False),  # 회원가입 화면 테스트용 (명단에만 있음)
    ("10102", "정예린", 1, 1, False),
]

BREAKFAST = [
    ("소고기 미역국, 계란말이, 배추김치, 흰쌀밥", ["달걀", "쇠고기", "대두"]),
    ("누룽지, 메추리알 장조림, 오이무침", ["달걀", "대두"]),
    ("프렌치토스트, 바나나, 시리얼, 우유", ["밀", "달걀", "우유"]),
    ("전복죽, 두부조림, 나박김치", ["조개류", "대두"]),
]
DINNER = [
    ("치킨마요 덮밥, 유부장국, 단무지, 방울토마토", ["닭고기", "달걀", "대두", "토마토"]),
    ("바질 크림 파스타, 마늘빵, 양상추 샐러드", ["밀", "우유"]),
    ("제육볶음, 콩나물국, 상추쌈, 흰쌀밥", ["돼지고기", "대두"]),
    ("마파두부 덮밥, 계란국, 짜사이", ["대두", "달걀", "돼지고기"]),
]
WISHES = [
    ("20105", "마라탕", "친구들과 함께 먹으면 더 맛있어요!", "🌶️"),
    ("10312", "떡볶이 & 튀김", "시험 끝난 날에 분식 데이 어때요?", "🍢"),
    ("30220", "연어 포케", "가볍지만 든든한 메뉴도 있었으면 해요.", "🥗"),
]


def _utc(day, hh: int) -> datetime:
    return datetime.combine(day, time(hh, 0), tzinfo=KST).astimezone(clock.now().tzinfo)


async def seed_demo(db: AsyncSession) -> dict[str, int]:
    now = clock.now()
    added = {"students": 0, "calendar": 0, "polls": 0, "wishes": 0}

    accounts: dict[str, Student] = {}
    for no, name, grade, class_no, has_account in STUDENTS:
        if await db.get(AllowedStudent, no) is None:
            db.add(
                AllowedStudent(
                    student_no=no, name=name, grade=grade, class_no=class_no, is_used=has_account
                )
            )
        s = await db.scalar(select(Student).where(Student.student_no == no))
        if s is None and has_account:
            s = Student(
                student_no=no,
                name=name,
                password_hash=hash_password(DEMO_PASSWORD),
                grade=grade,
                class_no=class_no,
                role=Role.student,
                privacy_agreed_at=now,
                created_at=now,
            )
            db.add(s)
            added["students"] += 1
        if s is not None:
            accounts[no] = s
    if await db.scalar(select(Student).where(Student.student_no == ADMIN_LOGIN)) is None:
        db.add(
            Student(
                student_no=ADMIN_LOGIN,
                name="영양 선생님",
                password_hash=hash_password(ADMIN_PASSWORD),
                role=Role.admin,
                created_at=now,
            )
        )
    await db.flush()

    today = clock.today_kst()
    for offset in range(-3, 15):
        day = today + timedelta(days=offset)
        if day.weekday() >= 5 or await db.get(MealCalendar, day) is not None:
            continue
        b_menu, b_all = BREAKFAST[day.toordinal() % len(BREAKFAST)]
        d_menu, d_all = DINNER[day.toordinal() % len(DINNER)]
        db.add(
            MealCalendar(
                service_date=day,
                breakfast_available=True,
                breakfast_menu=b_menu,
                breakfast_allergens=b_all,
                breakfast_deadline=_utc(day - timedelta(days=1), 18),  # 전날 18:00 KST
                dinner_available=True,
                dinner_menu=d_menu,
                dinner_allergens=d_all,
                dinner_deadline=_utc(day, 12),  # 당일 12:00 KST
            )
        )
        added["calendar"] += 1

    if await db.scalar(select(MealPoll.id).limit(1)) is None:
        db.add(
            MealPoll(
                title="다음 주 금요일, 딱 하나만 고른다면?",
                description="가장 먹고 싶은 메뉴 하나를 골라주세요. 결과는 마감 후 공개돼요.",
                target_date=today + timedelta(days=10),
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=3),
                is_published=True,
                created_at=now,
                options=[
                    PollOption(
                        menu_name="경양식 돈까스",
                        description="바삭한 돈까스 · 크림스프 · 양배추 샐러드",
                    ),
                    PollOption(
                        menu_name="불향 제육볶음", description="제육볶음 · 계란국 · 콩나물무침"
                    ),
                    PollOption(menu_name="마라샹궈", description="맵기 조절 마라샹궈 · 달걀볶음밥"),
                    PollOption(menu_name="치킨 타코", description="치킨 타코 · 나초 · 망고 샐러드"),
                ],
            )
        )
        added["polls"] += 1

    if await db.scalar(select(Wish.id).limit(1)) is None:
        for no, menu, reason, emoji in WISHES:
            if no in accounts:
                db.add(
                    Wish(
                        student_id=accounts[no].id,
                        menu_name=menu,
                        reason=reason,
                        emoji=emoji,
                        created_at=now,
                    )
                )
                added["wishes"] += 1

    await db.commit()
    return added
