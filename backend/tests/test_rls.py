"""「他人のロッカーは開かない」ことを、アプリを通さず DB に直接確かめる。

アプリのコードがどれだけ正しくても、ここが破れていたら意味がない。
逆に、ここが守られていれば、アプリに WHERE の書き忘れがあっても他人の行は出ない。
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import db


def _user(email: str) -> str:
    with db.system_conn() as c:
        return str(c.execute(text("INSERT INTO users (email) VALUES (:e) RETURNING id"),
                             {"e": email}).scalar())


def _item(uid: str, title: str) -> None:
    with db.user_conn(uid) as c:
        c.execute(text("INSERT INTO items (user_id, ext_uid, kind, title) VALUES (:u, :x, 'assignment', :t)"),
                  {"u": uid, "x": title, "t": title})


def test_each_user_sees_only_own_rows():
    a, b = _user("a@example.com"), _user("b@example.com")
    _item(a, "Aの課題")
    _item(b, "Bの課題")
    with db.user_conn(a) as c:
        # WHERE を **わざと書かない**。それでも自分のぶんしか返らないことを見る
        assert [r[0] for r in c.execute(text("SELECT title FROM items"))] == ["Aの課題"]
        assert [r[0] for r in c.execute(text("SELECT email FROM users"))] == ["a@example.com"]


def test_without_identity_nothing_is_visible():
    a = _user("a@example.com")
    _item(a, "Aの課題")
    with db.app_engine().begin() as c:   # 名乗らずに入る
        assert c.execute(text("SELECT count(*) FROM items")).scalar() == 0


def test_cannot_write_as_someone_else():
    a, b = _user("a@example.com"), _user("b@example.com")
    with pytest.raises(DBAPIError):
        with db.user_conn(a) as c:
            c.execute(text("INSERT INTO items (user_id, ext_uid, kind, title) VALUES (:u, 'x', 'event', '乗っ取り')"),
                      {"u": b})


def test_cannot_touch_others_rows():
    a, b = _user("a@example.com"), _user("b@example.com")
    _item(b, "Bの課題")
    with db.user_conn(a) as c:
        assert c.execute(text("UPDATE items SET title = '書き換え'")).rowcount == 0
        assert c.execute(text("DELETE FROM items")).rowcount == 0
    with db.user_conn(b) as c:
        assert c.execute(text("SELECT title FROM items")).scalar() == "Bの課題"


def test_identity_does_not_leak_between_transactions():
    """接続はプールで使い回される。前の人の名乗りが次の取引に残っていないこと。"""
    a = _user("a@example.com")
    _item(a, "Aの課題")
    with db.user_conn(a) as c:
        assert c.execute(text("SELECT count(*) FROM items")).scalar() == 1
    with db.app_engine().begin() as c:
        assert c.execute(text("SELECT count(*) FROM items")).scalar() == 0


def test_every_user_table_has_rls():
    """user_id を持つ表は全部 RLS がかかっていること。表を足したときの付け忘れをここで捕まえる。"""
    with db.system_conn() as c:
        missing = [r[0] for r in c.execute(text("""
            SELECT t.relname
              FROM pg_class t
              JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = 'public'
             WHERE t.relkind = 'r'
               AND (EXISTS (SELECT 1 FROM information_schema.columns col
                             WHERE col.table_name = t.relname AND col.column_name = 'user_id')
                    OR t.relname = 'users')
               AND NOT (t.relrowsecurity AND EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = t.oid))
        """))]
    assert missing == [], f"RLS が無い表: {missing}"
