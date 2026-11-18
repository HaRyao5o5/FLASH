"""Canvas まわりの API。接続の管理・取り込み・課題・科目。

### 「管理するのは本人」

ここにある操作は全部、本人が自分のぶんにだけできる。
サイトの管理者（あなた）でも、他人の接続や課題には触れない（RLS がそれを保証する）。
本人ができること:

- つなぐ／貼り直す／**切る**（切ると暗号化した URL も消える。取り込んだ課題は残すか消すか選べる）
- 今すぐ取り込む
- 課題に「出した」を付ける・外す
- 科目に呼び名をつける・一覧から隠す
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from . import canvas_feed, crypto, db, sync
from .auth import CurrentUser
from .canvas_feed import FeedError

router = APIRouter(prefix="/api")


def _connection(conn) -> dict | None:
    row = conn.execute(text("""
        SELECT hint, status, last_try_at, last_ok_at, last_error, last_counts, created_at
          FROM connections WHERE kind = 'canvas_feed'""")).mappings().first()
    return dict(row) if row else None


@router.get("/canvas")
def canvas_status(user: dict = CurrentUser):
    with db.user_conn(user["id"]) as conn:
        c = _connection(conn)
    return {"connected": c is not None, "connection": c}


class FeedIn(BaseModel):
    feed_url: str


@router.put("/canvas")
def canvas_connect(body: FeedIn, user: dict = CurrentUser):
    """つなぐ（貼り直しも同じ）。保存する前に一度取りに行って、本当に読めるか確かめる。"""
    try:
        url = canvas_feed.normalize_feed_url(body.feed_url)
        items = canvas_feed.parse(canvas_feed.fetch(url))
    except FeedError as e:
        raise HTTPException(400, str(e))

    with db.user_conn(user["id"]) as conn:
        conn.execute(text("""
            INSERT INTO connections (user_id, kind, secret_enc, hint, status)
            VALUES (:u, 'canvas_feed', :s, :h, 'new')
            ON CONFLICT (user_id, kind) DO UPDATE
               SET secret_enc = EXCLUDED.secret_enc, hint = EXCLUDED.hint,
                   status = 'new', last_error = NULL"""),
            {"u": user["id"], "s": crypto.encrypt(url), "h": canvas_feed.url_hint(url)})
        counts = sync.apply(conn, user["id"], items)
        conn.execute(text("""
            UPDATE connections SET status = 'ok', last_try_at = now(), last_ok_at = now(),
                   last_counts = CAST(:c AS jsonb)
             WHERE kind = 'canvas_feed'"""), {"c": sync._json(counts)})
        c = _connection(conn)
    return {"connected": True, "connection": c, "counts": counts}


@router.delete("/canvas")
def canvas_disconnect(purge: bool = False, user: dict = CurrentUser):
    """切る。purge=true なら取り込んだ課題と科目も消す（「出した」の印も消える）。"""
    with db.user_conn(user["id"]) as conn:
        conn.execute(text("DELETE FROM connections WHERE kind = 'canvas_feed'"))
        if purge:
            conn.execute(text("DELETE FROM items WHERE source = 'canvas'"))
            conn.execute(text("DELETE FROM courses WHERE source = 'canvas'"))
    return {"connected": False}


@router.post("/canvas/sync")
def canvas_sync(user: dict = CurrentUser):
    try:
        counts = sync.sync_user(user["id"], manual=True)
    except sync.Busy:
        raise HTTPException(409, "いま取り込み中です。少し待ってください")
    except sync.TooSoon as e:
        raise HTTPException(429, f"さっき取り込んだばかりです。{e.wait}秒後にもう一度どうぞ")
    except FeedError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:   # 復号できない等
        raise HTTPException(500, str(e))
    with db.user_conn(user["id"]) as conn:
        c = _connection(conn)
    return {"connected": True, "connection": c, "counts": counts}


# ---- 課題・予定 ------------------------------------------------------------

@router.get("/items")
def list_items(days_past: int = 14, include_done: bool = True, include_hidden: bool = False,
               user: dict = CurrentUser):
    """締切の一覧。既定は「2週間前から先ぜんぶ」。隠した科目のものは出さない。"""
    since = datetime.now(timezone.utc) - timedelta(days=max(0, min(days_past, 365)))
    with db.user_conn(user["id"]) as conn:
        rows = conn.execute(text("""
            SELECT i.id, i.kind, i.title, i.due_at, i.all_day, i.url, i.description,
                   i.prev_due_at, i.due_changed_at, i.first_seen_at, i.gone_at, i.done_at,
                   c.id AS course_id, COALESCE(c.display_name, c.name) AS course_name,
                   c.slot AS course_slot
              FROM items i LEFT JOIN courses c ON c.id = i.course_id
             WHERE (i.due_at IS NULL OR i.due_at >= :since)
               AND (:inc_done OR i.done_at IS NULL)
               AND (:inc_hidden OR c.hidden IS NOT TRUE)
             ORDER BY i.due_at NULLS LAST, i.title"""),
            {"since": since, "inc_done": include_done, "inc_hidden": include_hidden}).mappings()
        return [dict(r) for r in rows]


class ItemPatch(BaseModel):
    done: bool


@router.patch("/items/{item_id}")
def patch_item(item_id: UUID, body: ItemPatch, user: dict = CurrentUser):
    with db.user_conn(user["id"]) as conn:
        r = conn.execute(text("""
            UPDATE items SET done_at = CASE WHEN :d THEN COALESCE(done_at, now()) ELSE NULL END
             WHERE id = CAST(:id AS uuid) RETURNING id, done_at"""),
            {"d": body.done, "id": str(item_id)}).mappings().first()
    if r is None:   # 無い、または他人のもの（RLS で見えない）。どちらも同じ返事にする
        raise HTTPException(404, "見つかりません")
    return dict(r)


# ---- 科目 ---------------------------------------------------------------

@router.get("/courses")
def list_courses(user: dict = CurrentUser):
    with db.user_conn(user["id"]) as conn:
        rows = conn.execute(text("""
            SELECT c.id, c.ext_key, c.name, c.display_name, c.teacher, c.term,
                   c.day_of_week, c.period, c.slot, c.hidden, c.last_seen_at,
                   count(i.id) FILTER (WHERE i.gone_at IS NULL) AS item_count
              FROM courses c LEFT JOIN items i ON i.course_id = c.id
             GROUP BY c.id
             ORDER BY c.hidden, c.day_of_week NULLS LAST, c.period NULLS LAST, c.name""")).mappings()
        return [dict(r) for r in rows]


class CoursePatch(BaseModel):
    hidden: bool | None = None
    display_name: str | None = None   # 空文字で「元の名前に戻す」


@router.patch("/courses/{course_id}")
def patch_course(course_id: UUID, body: CoursePatch, user: dict = CurrentUser):
    sets, params = [], {"id": str(course_id)}
    if body.hidden is not None:
        sets.append("hidden = :hidden")
        params["hidden"] = body.hidden
    if body.display_name is not None:
        sets.append("display_name = :dn")
        params["dn"] = body.display_name.strip()[:80] or None
    if not sets:
        raise HTTPException(400, "変更がありません")
    with db.user_conn(user["id"]) as conn:
        r = conn.execute(text(
            f"UPDATE courses SET {', '.join(sets)} WHERE id = CAST(:id AS uuid) RETURNING id"),
            params).first()
    if r is None:
        raise HTTPException(404, "見つかりません")
    return {"ok": True}
