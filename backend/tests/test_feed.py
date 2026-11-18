from datetime import datetime, timezone

import pytest

from app.canvas_feed import (FeedError, normalize_feed_url, parse, parse_course_name,
                             split_summary, url_hint)
from conftest import FEED_URL, make_ics


def test_good_urls():
    assert normalize_feed_url(FEED_URL) == FEED_URL
    assert normalize_feed_url("  " + FEED_URL + "  ") == FEED_URL
    assert normalize_feed_url(FEED_URL.replace("https://", "webcal://")) == FEED_URL
    assert normalize_feed_url(FEED_URL + "#x") == FEED_URL


@pytest.mark.parametrize("bad", [
    "",
    "http://nu.instructure.com/feeds/calendars/user_abc.ics",          # https じゃない
    "https://evil.example.com/feeds/calendars/user_abc.ics",           # 別のホスト
    "https://nu.instructure.com.evil.com/feeds/calendars/user_abc.ics",  # 似せたホスト
    "https://169.254.169.254/latest/meta-data",                        # クラウドの内部
    "https://nu.instructure.com/api/v1/courses",                       # フィードではない
    "https://nu.instructure.com/feeds/calendars/user_abc.ics/../../x",  # 道をずらす
    "https://user:pw@nu.instructure.com/feeds/calendars/user_abc.ics",  # 認証情報入り
    "https://nu.instructure.com:8443/feeds/calendars/user_abc.ics",    # ポート指定
    "file:///etc/passwd",
])
def test_bad_urls(bad):
    with pytest.raises(FeedError):
        normalize_feed_url(bad)


def test_hint_does_not_leak():
    assert url_hint(FEED_URL) == "…3456"
    assert "AbCdEf" not in url_hint(FEED_URL)


def test_split_summary():
    assert split_summary("レポート1 [2026情報科学実習３（宮田 章裕・前・火5）]") == (
        "レポート1", "2026情報科学実習３（宮田 章裕・前・火5）")
    assert split_summary("[重要] 小テスト [英語１]") == ("[重要] 小テスト", "英語１")
    assert split_summary("歯医者") == ("歯医者", None)


def test_parse_course_name():
    p = parse_course_name("2026情報科学実習３（宮田 章裕・前・火5）")
    assert (p["name"], p["teacher"], p["term"], p["slot"], p["day_of_week"], p["period"]) == (
        "情報科学実習３", "宮田 章裕", "前", "火5", 1, 5)
    p = parse_course_name("2026英語１（再）（セコ マイケル・前・土3）")
    assert p["name"] == "英語１（再）" and p["slot"] == "土3"
    p = parse_course_name("2026ビッグデータサイエンス（地球科・情報科・物理）（前・金7）")
    assert p["name"] == "ビッグデータサイエンス（地球科・情報科・物理）" and p["teacher"] is None
    p = parse_course_name("2026情報倫理・情報セキュリティ")
    assert p["name"] == "情報倫理・情報セキュリティ" and p["slot"] is None


def test_parse_feed():
    raw = make_ics([
        {"uid": "event-assignment-1", "summary": "レポート1 [2026情報科学実習３（宮田 章裕・前・火5）]",
         "start": "20261120T145900Z", "url": "https://nu.instructure.com/courses/1/assignments/1"},
        {"uid": "event-calendar-event-9", "summary": "補講 [2026英語１（セコ マイケル・前・土3）]",
         "date": "20261125"},
        {"uid": "event-assignment-1", "summary": "重複は1件に", "start": "20261120T145900Z"},
    ])
    items = parse(raw)
    assert len(items) == 2
    a, e = items
    assert a.kind == "assignment" and a.title == "レポート1"
    assert a.due_at == datetime(2026, 11, 20, 14, 59, tzinfo=timezone.utc) and not a.all_day
    assert a.url.endswith("/assignments/1")
    assert e.kind == "event" and e.all_day
    assert e.due_at == datetime(2026, 11, 24, 15, 0, tzinfo=timezone.utc)  # JST 11/25 0:00


def test_parse_garbage():
    with pytest.raises(FeedError):
        parse(b"<html>not a calendar</html>")
