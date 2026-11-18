"""画面から使う流れを、API ごしに通して確かめる。Canvas への通信だけ差し替える。"""

import pytest
from fastapi.testclient import TestClient

from app import canvas_feed
from app.main import app
from conftest import FEED_URL, make_ics

H = {"X-FLASH": "1"}
COURSE = "2026情報科学実習３（宮田 章裕・前・火5）"


@pytest.fixture
def feed(monkeypatch):
    """Canvas の代わり。state["events"] を書き換えるとフィードの中身が変わる。"""
    state = {"events": [
        {"uid": "event-assignment-1", "summary": f"レポート1 [{COURSE}]", "start": "20991120T145900Z"},
        {"uid": "event-assignment-2", "summary": f"レポート2 [{COURSE}]", "start": "20991127T145900Z"},
    ], "calls": []}

    def fake_fetch(url, client=None):
        state["calls"].append(canvas_feed.normalize_feed_url(url))
        return make_ics(state["events"])

    monkeypatch.setattr(canvas_feed, "fetch", fake_fetch)
    return state


def login(email: str) -> TestClient:
    c = TestClient(app)
    c.__enter__()
    r = c.post("/api/auth/dev-login", json={"email": email}, headers=H)
    assert r.status_code == 200, r.text
    return c


def test_needs_login():
    with TestClient(app) as c:
        assert c.get("/api/items").status_code == 401


def test_write_needs_header(feed):
    a = login("a@example.com")
    assert a.put("/api/canvas", json={"feed_url": FEED_URL}).status_code == 403


def test_connect_rejects_bad_url(feed):
    a = login("a@example.com")
    r = a.put("/api/canvas", json={"feed_url": "https://evil.example.com/x.ics"}, headers=H)
    assert r.status_code == 400
    assert feed["calls"] == []          # 取りに行く前に断っている


def test_full_flow(feed):
    a = login("a@example.com")

    r = a.put("/api/canvas", json={"feed_url": FEED_URL}, headers=H)
    assert r.status_code == 200, r.text
    assert r.json()["counts"]["new"] == 2
    st = a.get("/api/canvas").json()
    assert st["connected"] and st["connection"]["hint"] == "…3456"
    assert "AbCdEf" not in str(st)      # URL そのものは画面に返さない

    items = a.get("/api/items").json()
    assert [i["title"] for i in items] == ["レポート1", "レポート2"]
    assert items[0]["course_name"] == "情報科学実習３" and items[0]["course_slot"] == "火5"

    # 「出した」
    first = items[0]["id"]
    assert a.patch(f"/api/items/{first}", json={"done": True}, headers=H).json()["done_at"]
    assert len(a.get("/api/items?include_done=false").json()) == 1

    # Canvas 側で、レポート1の締切が延び、レポート2が消え、レポート3が増えた
    feed["events"] = [
        {"uid": "event-assignment-1", "summary": f"レポート1 [{COURSE}]", "start": "20991121T145900Z"},
        {"uid": "event-assignment-3", "summary": f"レポート3 [{COURSE}]", "start": "20991204T145900Z"},
    ]
    c = a.post("/api/canvas/sync", headers=H).json()["counts"]
    assert (c["new"], c["due_changed"], c["gone"]) == (1, 1, 1)
    by = {i["title"]: i for i in a.get("/api/items").json()}
    assert by["レポート1"]["prev_due_at"] and by["レポート1"]["done_at"]   # 「出した」は残る
    assert by["レポート2"]["gone_at"]

    # 空のフィードが来ても、全部を「消えた」にはしない
    feed["events"] = []
    c = a.post("/api/canvas/sync", headers=H).json()["counts"]
    assert c["skipped_gone_check"] and c["gone"] == 0

    # 科目を隠すと一覧から消える
    course = a.get("/api/courses").json()[0]
    a.patch(f"/api/courses/{course['id']}", json={"hidden": True}, headers=H)
    assert a.get("/api/items").json() == []
    assert len(a.get("/api/items?include_hidden=true").json()) == 3


def test_other_user_sees_nothing_and_cannot_touch(feed):
    a = login("a@example.com")
    a.put("/api/canvas", json={"feed_url": FEED_URL}, headers=H)
    item_id = a.get("/api/items").json()[0]["id"]
    course_id = a.get("/api/courses").json()[0]["id"]

    b = login("b@example.com")
    assert b.get("/api/items").json() == []
    assert b.get("/api/courses").json() == []
    assert b.get("/api/canvas").json()["connected"] is False
    assert b.patch(f"/api/items/{item_id}", json={"done": True}, headers=H).status_code == 404
    assert b.patch(f"/api/courses/{course_id}", json={"hidden": True}, headers=H).status_code == 404
    b.delete("/api/canvas?purge=true", headers=H)     # B が消しても A のぶんは消えない
    assert len(a.get("/api/items").json()) == 2


def test_disconnect(feed):
    a = login("a@example.com")
    a.put("/api/canvas", json={"feed_url": FEED_URL}, headers=H)
    a.delete("/api/canvas", headers=H)
    assert a.get("/api/canvas").json()["connected"] is False
    assert len(a.get("/api/items").json()) == 2      # 課題は残す（purge なし）
    assert a.post("/api/canvas/sync", headers=H).status_code == 400
    a.put("/api/canvas", json={"feed_url": FEED_URL}, headers=H)
    a.delete("/api/canvas?purge=true", headers=H)
    assert a.get("/api/items").json() == []
