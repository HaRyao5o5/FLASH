"""取り込み。1人ぶんのフィードを読んで、科目と課題を最新にする。

### 3段に分けている理由

    1. 接続を読む（短い取引）
    2. Canvas に取りに行く（取引の外。数秒〜20秒かかりうる）
    3. 結果を書き込む（短い取引）

2 を取引の中でやると、Canvas が遅い間ずっと DB をつかんだままになる。
1人なら気にならないが、人数が増えると全員が待たされる。

### 消えた課題の扱い

フィードは「未来の全部と過去30日」しか出さない。窓の外に出ただけのものまで
「消えた」と扱うと、先月の課題が全部消える。だから gone を付けるのは
**窓の中にあるはずなのに無いもの**だけ。

さらに、**1件も返ってこなかったとき**は gone を付けない。
Canvas 側の一時的な不調で空のフィードが返ると、全部の課題に
「消えた」が付いてしまう。0件のときは記録だけ残して、何も消さない。
"""

import threading
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text

from . import canvas_feed, config, crypto, db
from .canvas_feed import FeedError, FeedItem

WINDOW_PAST = timedelta(days=30)
WINDOW_MARGIN = timedelta(days=1)   # 窓の端ちょうどのものを「消えた」と誤判定しない余白

# 同じ人の取り込みが重ならないように（ボタンと定期取り込みが同時に来ることがある）。
# 1台で動かす前提なのでプロセス内の鍵で足りる。台数を増やすなら DB の advisory lock に替える。
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _lock_for(user_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(user_id, threading.Lock())


class Busy(Exception):
    pass


class TooSoon(Exception):
    def __init__(self, wait: int):
        self.wait = wait


def sync_user(user_id: UUID | str, *, manual: bool = False, fetcher=None) -> dict:
    """1人ぶん取り込む。結果の件数を返す。失敗も接続の状態に書いてから例外で返す。

    fetcher はテスト用（URL → bytes）。
    """
    uid = str(user_id)
    lock = _lock_for(uid)
    if not lock.acquire(blocking=False):
        raise Busy()
    try:
        # ---- 1. 接続を読む ----
        with db.user_conn(uid) as conn:
            row = conn.execute(text(
                "SELECT secret_enc, last_try_at FROM connections WHERE kind = 'canvas_feed'"
            )).mappings().first()
            if row is None:
                raise FeedError("Canvas がまだつながっていません")
            now = datetime.now(timezone.utc)
            if manual and row["last_try_at"] and config.SYNC_COOLDOWN:
                passed = (now - row["last_try_at"]).total_seconds()
                if passed < config.SYNC_COOLDOWN:
                    raise TooSoon(int(config.SYNC_COOLDOWN - passed) + 1)
            conn.execute(text("UPDATE connections SET last_try_at = now() WHERE kind = 'canvas_feed'"))
        url = crypto.decrypt(row["secret_enc"])

        # ---- 2. 取りに行く ----
        try:
            raw = (fetcher or canvas_feed.fetch)(url)
            items = canvas_feed.parse(raw)
        except FeedError as e:
            _record_error(uid, str(e))
            raise

        # ---- 3. 書き込む ----
        with db.user_conn(uid) as conn:
            counts = apply(conn, uid, items)
            conn.execute(text("""
                UPDATE connections
                   SET status = 'ok', last_ok_at = now(), last_error = NULL,
                       last_counts = CAST(:c AS jsonb)
                 WHERE kind = 'canvas_feed'"""), {"c": _json(counts)})
        return counts
    finally:
        lock.release()


def _record_error(uid: str, message: str) -> None:
    with db.user_conn(uid) as conn:
        conn.execute(text("""
            UPDATE connections SET status = 'error', last_error = :m
             WHERE kind = 'canvas_feed'"""), {"m": message[:500]})


def _json(d: dict) -> str:
    import json
    return json.dumps(d, ensure_ascii=False)


def apply(conn, uid: str, items: list[FeedItem], now: datetime | None = None) -> dict:
    """読んだ結果を DB に反映する。conn は本人として開いた接続。"""
    now = now or datetime.now(timezone.utc)
    counts = {"total": len(items), "new": 0, "due_changed": 0, "gone": 0,
              "back": 0, "courses_new": 0, "skipped_gone_check": False}

    # ---- 科目 ----
    course_ids: dict[str, str] = {}
    for key in sorted({it.course_key for it in items if it.course_key}):
        p = canvas_feed.parse_course_name(key)
        r = conn.execute(text("""
            INSERT INTO courses (user_id, ext_key, name, teacher, term, day_of_week, period, slot)
            VALUES (:u, :k, :name, :teacher, :term, :dow, :period, :slot)
            ON CONFLICT (user_id, source, ext_key) DO UPDATE
               SET name = EXCLUDED.name, teacher = EXCLUDED.teacher, term = EXCLUDED.term,
                   day_of_week = EXCLUDED.day_of_week, period = EXCLUDED.period,
                   slot = EXCLUDED.slot, last_seen_at = now()
            RETURNING id, (xmax = 0) AS inserted"""),
            {"u": uid, "k": key, "name": p["name"] or key, "teacher": p["teacher"],
             "term": p["term"], "dow": p["day_of_week"], "period": p["period"], "slot": p["slot"]},
        ).first()
        course_ids[key] = str(r.id)
        if r.inserted:
            counts["courses_new"] += 1
        # display_name / hidden は本人の値なので、上の UPDATE で触っていない

    # ---- 課題・予定 ----
    existing = {r.ext_uid: r for r in conn.execute(text(
        "SELECT ext_uid, due_at, gone_at FROM items WHERE source = 'canvas'"))}

    for it in items:
        cid = course_ids.get(it.course_key) if it.course_key else None
        old = existing.get(it.uid)
        params = {"u": uid, "x": it.uid, "kind": it.kind, "title": it.title, "c": cid,
                  "due": it.due_at, "ad": it.all_day, "url": it.url, "desc": it.description}
        if old is None:
            conn.execute(text("""
                INSERT INTO items (user_id, ext_uid, kind, title, course_id, due_at, all_day, url, description)
                VALUES (:u, :x, :kind, :title, :c, :due, :ad, :url, :desc)"""), params)
            counts["new"] += 1
            continue

        changed = old.due_at != it.due_at and old.due_at is not None
        if changed:
            counts["due_changed"] += 1
        if old.gone_at is not None:
            counts["back"] += 1
        conn.execute(text("""
            UPDATE items
               SET kind = :kind, title = :title, course_id = :c, due_at = :due, all_day = :ad,
                   url = :url, description = :desc, last_seen_at = now(), gone_at = NULL,
                   prev_due_at    = CASE WHEN :changed THEN due_at ELSE prev_due_at END,
                   due_changed_at = CASE WHEN :changed THEN now()  ELSE due_changed_at END
             WHERE source = 'canvas' AND ext_uid = :x"""), {**params, "changed": changed})
        # done_at（本人の「出した」）はここで触らない

    # ---- 消えたもの ----
    if not items:
        counts["skipped_gone_check"] = True
        return counts
    edge = now - WINDOW_PAST + WINDOW_MARGIN
    seen = [it.uid for it in items]
    res = conn.execute(text("""
        UPDATE items SET gone_at = now()
         WHERE source = 'canvas' AND gone_at IS NULL
           AND due_at >= :edge
           AND NOT (ext_uid = ANY(:seen))"""), {"edge": edge, "seen": seen})
    counts["gone"] = res.rowcount or 0
    return counts


def users_to_sync() -> list[str]:
    """定期取り込みの対象。RLS の外で一覧だけ引く（中身は見ない）。"""
    with db.system_conn() as conn:
        return [str(r[0]) for r in conn.execute(text(
            "SELECT user_id FROM connections WHERE kind = 'canvas_feed'"))]


def sync_all() -> dict:
    done = {"ok": 0, "error": 0, "busy": 0}
    for uid in users_to_sync():
        try:
            sync_user(uid)
            done["ok"] += 1
        except Busy:
            done["busy"] += 1
        except Exception:
            done["error"] += 1   # 中身は接続の last_error に残っている
    return done
