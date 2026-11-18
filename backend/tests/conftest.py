"""テストの土台。**本物の PostgreSQL** に繋ぐ（RLS は本物でしか確かめられない）。

手元では `docker compose up -d` しておけば、そのまま flash_test DB を使う。
別の場所を使うなら FLASH_TEST_DATABASE_URL / FLASH_TEST_SYSTEM_DATABASE_URL を指定する。
テストのたびに flash_test の中身を全部作り直すので、**本番の DB を指定しないこと。**
"""

import os

from cryptography.fernet import Fernet

APP_URL = os.getenv("FLASH_TEST_DATABASE_URL",
                    "postgresql+psycopg://flash_app:flash_app@localhost:5432/flash_test")
SYS_URL = os.getenv("FLASH_TEST_SYSTEM_DATABASE_URL",
                    "postgresql+psycopg://flash_owner:flash_owner@localhost:5432/flash_test")

# app.config を読む前に差し替える
os.environ.update({
    "FLASH_ENV": "test",
    "FLASH_DATABASE_URL": APP_URL,
    "FLASH_SYSTEM_DATABASE_URL": SYS_URL,
    "FLASH_SECRET_KEY": "test-secret",
    "FLASH_ENCRYPTION_KEY": Fernet.generate_key().decode(),
    "FLASH_DEV_LOGIN": "1",
    "FLASH_ALLOWED_DOMAIN": "",
    "FLASH_SYNC_MINUTES": "0",
    "FLASH_SYNC_COOLDOWN": "0",
    "FLASH_FRONTEND_DIST": "/nonexistent",
})

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app import db, migrate  # noqa: E402

assert "flash_test" in SYS_URL, "テストは flash_test 以外の DB では動かさない"


@pytest.fixture(autouse=True)
def fresh_db():
    eng = create_engine(SYS_URL)
    with eng.begin() as c:
        c.execute(text("DROP SCHEMA public CASCADE"))
        c.execute(text("CREATE SCHEMA public"))
        c.execute(text("GRANT USAGE ON SCHEMA public TO flash_app"))
    eng.dispose()
    db.reset_engines()
    migrate.run(SYS_URL)
    yield
    db.reset_engines()


FEED_URL = "https://nu.instructure.com/feeds/calendars/user_AbCdEf123456.ics"


def make_ics(events: list[dict]) -> bytes:
    """Canvas のフィードと同じ形の ICS を作る。"""
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Instructure//Canvas//EN",
             "X-WR-CALNAME:テスト カレンダー (Canvas)"]
    for e in events:
        lines += ["BEGIN:VEVENT", f"UID:{e['uid']}", f"SUMMARY:{e['summary']}"]
        if e.get("date"):
            lines += [f"DTSTART;VALUE=DATE:{e['date']}", f"DTEND;VALUE=DATE:{e['date']}"]
        else:
            lines += [f"DTSTART:{e['start']}", f"DTEND:{e['start']}"]
        if e.get("url"):
            lines.append(f"URL;VALUE=URI:{e['url']}")
        if e.get("desc"):
            lines.append(f"DESCRIPTION:{e['desc']}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return ("\r\n".join(lines) + "\r\n").encode()
