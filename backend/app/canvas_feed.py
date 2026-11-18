"""Canvas のカレンダーフィード（ICS）を読む。

### なぜトークンではなくフィードなのか

JARVIS は自分で発行したアクセストークンで Canvas API を叩いている。
自分の鍵を自分で使うのは問題ない。でも **他人にトークンを発行させて
アプリに入れてもらうのは Canvas の API ポリシー違反**で、複数人で使うアプリは
OAuth（大学の管理者が出す開発者キー）を使うことになっている。

カレンダーフィードは、Canvas が「Google カレンダーなどに貼ってください」と
学生向けに用意している正規の出口。中身は課題（締切）と予定。

### フィードで取れないもの（＝JARVIS より弱いところ）

- 提出したか・点数 → 本人が「出した」を押す（items.done_at）
- お知らせ・資料・To Do
- 30日より前の過去（フィードは「未来全部と過去30日」だけ）

### URL を何でも受け付けない理由（SSRF）

利用者が貼った URL をサーバーが取りに行く、という仕組みは、放っておくと
「サーバーに好きな場所を見に行かせる」穴になる。例えば社内向けの管理画面や、
クラウドの設定情報が置いてある内部アドレスを、FLASH のサーバーに覗かせることができてしまう。
郵便局に「この住所に行って中身を持ってきて」と頼めるなら、局の金庫室の住所を書く人が出る。
だから **Canvas のフィードの形をした URL 以外は、取りに行く前に断る。**
転送（リダイレクト）にもついていかない。転送先が別の場所かもしれないから。
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import httpx
from icalendar import Calendar

from . import config

JST = timezone(timedelta(hours=9))
DAYS = "月火水木金土日"

MAX_BYTES = 5 * 1024 * 1024      # 学生1人のフィードはふつう数百KB。これを超えたら何かおかしい
TIMEOUT = 20.0
FEED_PATH = re.compile(r"^/feeds/calendars/user_[A-Za-z0-9]+\.ics$")


class FeedError(Exception):
    """利用者に見せてよい言葉で理由を持つ例外。"""


# ---- URL の検査 -----------------------------------------------------------

def normalize_feed_url(raw: str) -> str:
    """貼られた URL を検査して、取りに行ってよい形に直して返す。だめなら FeedError。

    - webcal:// は https:// に直す（カレンダーアプリ向けに webcal で出てくることがある）
    - ホストは FLASH_CANVAS_HOST（既定 nu.instructure.com）だけ
    - パスは /feeds/calendars/user_….ics の形だけ
    - ユーザー名・パスワード入り、ポート指定、# 以降は受け付けない
    """
    s = (raw or "").strip()
    if not s:
        raise FeedError("URL が空です")
    if s.lower().startswith("webcal://"):
        s = "https://" + s[len("webcal://"):]

    try:
        u = urlsplit(s)
        port = u.port
    except ValueError:
        raise FeedError("URL の形になっていません")

    if u.scheme != "https":
        raise FeedError("https:// で始まる URL を貼ってください")
    if u.username or u.password:
        raise FeedError("この形の URL は受け付けられません")
    if (u.hostname or "").lower() != config.CANVAS_HOST:
        raise FeedError(f"{config.CANVAS_HOST} のカレンダーフィードの URL を貼ってください")
    if port not in (None, 443):
        raise FeedError("この形の URL は受け付けられません")
    if not FEED_PATH.match(u.path):
        raise FeedError("カレンダーフィードの URL ではないようです"
                        "（Canvas のカレンダー →「カレンダーフィード」から出る URL です）")
    return urlunsplit(("https", config.CANVAS_HOST, u.path, u.query, ""))


def url_hint(url: str) -> str:
    """画面に出す目印。秘密の部分は出さない。"""
    path = urlsplit(url).path
    tail = path.rsplit("_", 1)[-1].removesuffix(".ics")
    return f"…{tail[-4:]}" if len(tail) >= 4 else "…"


# ---- 取りに行く -------------------------------------------------------------

def fetch(url: str, client: httpx.Client | None = None) -> bytes:
    """フィードを取ってくる。URL は normalize_feed_url を通したものだけ渡すこと。"""
    url = normalize_feed_url(url)  # 念のためもう一度（DB から出てきた値も信用しすぎない）
    own = client is None
    client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=False,
                                    headers={"User-Agent": "FLASH (student calendar reader)"})
    try:
        with client.stream("GET", url) as r:
            if r.status_code in (401, 403, 404):
                raise FeedError("Canvas がこのフィードを返しませんでした"
                                "（URL が古いか、間違っている可能性があります）")
            if 300 <= r.status_code < 400:
                raise FeedError("Canvas が別の場所へ転送しようとしました。URL を貼り直してください")
            if r.status_code != 200:
                raise FeedError(f"Canvas が応答しませんでした（{r.status_code}）。時間をおいて試してください")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > MAX_BYTES:
                    raise FeedError("フィードが大きすぎます")
            return bytes(buf)
    except httpx.TimeoutException:
        raise FeedError("Canvas の応答が遅すぎました。時間をおいて試してください")
    except httpx.HTTPError:
        raise FeedError("Canvas につながりませんでした")
    finally:
        if own:
            client.close()


# ---- 読む -----------------------------------------------------------------

@dataclass
class FeedItem:
    uid: str
    kind: str              # assignment / event
    title: str
    course_key: str | None  # [ ] の中身。無ければ None（個人の予定など）
    due_at: datetime | None
    all_day: bool
    url: str | None
    description: str | None


_SUMMARY = re.compile(r"^(?P<title>.*?)\s*\[(?P<course>[^\[\]]+)\]\s*$")


def split_summary(summary: str) -> tuple[str, str | None]:
    """「レポート1 [2026情報科学実習３（宮田 章裕・前・火5）]」→ (題, コース名)。

    コース名は最後の [ ] だけ見る。題に [ ] が入っていても壊れないように。
    """
    s = (summary or "").strip()
    m = _SUMMARY.match(s)
    if not m or not m.group("title").strip():
        return s, None
    return m.group("title").strip(), m.group("course").strip()


def _to_dt(v) -> tuple[datetime | None, bool]:
    """ICS の日時を timezone 付き datetime に。日付だけなら JST の 0:00 として all_day。"""
    if v is None:
        return None, False
    if isinstance(v, datetime):
        if v.tzinfo is None:          # 浮動時刻は JST とみなす（日本の大学の Canvas なので）
            v = v.replace(tzinfo=JST)
        return v.astimezone(timezone.utc), False
    if isinstance(v, date):
        return datetime.combine(v, time(0, 0), tzinfo=JST).astimezone(timezone.utc), True
    return None, False


def parse(raw: bytes) -> list[FeedItem]:
    try:
        cal = Calendar.from_ical(raw)
    except Exception:
        raise FeedError("フィードの中身を読めませんでした（カレンダーの形式ではないようです）")

    out: list[FeedItem] = []
    seen: set[str] = set()
    for ev in cal.walk("VEVENT"):
        uid = str(ev.get("UID") or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        title, course = split_summary(str(ev.get("SUMMARY") or ""))
        start = ev.get("DTSTART")
        due_at, all_day = _to_dt(start.dt if start is not None else None)
        url = ev.get("URL")
        desc = str(ev.get("DESCRIPTION") or "").strip() or None
        out.append(FeedItem(
            uid=uid,
            kind="assignment" if "assignment" in uid.lower() else "event",
            title=title or "（題なし）",
            course_key=course,
            due_at=due_at,
            all_day=all_day,
            url=str(url) if url else None,
            description=desc[:4000] if desc else None,
        ))
    return out


# ---- コース名を分解する（JARVIS の adapters/canvas.py から移植） -------------------

def parse_course_name(raw: str) -> dict:
    """Canvas のコース名から科目名・担当者・学期・曜日・時限を取り出す。

    日大のコース名はこの形になっている:
        2026情報科学実習３（宮田 章裕・前・火5）
        ^年度^科目名        ^担当者    ^学期^曜日時限

    **科目名自体に括弧が入ることがある**ので、最後の括弧だけを情報として扱う:
        2026英語１（再）（セコ マイケル・前・土3）
        2026ビッグデータサイエンス（地球科・情報科・物理）（前・金7）
    科目名に「・」が入るもの（情報倫理・情報セキュリティ）もあるため、
    区切りの判定は括弧の中だけで行う。

    形が想定と違えば何も埋めずに返す。
    """
    out = {"name": raw, "teacher": None, "term": None,
           "day_of_week": None, "period": None, "slot": None}
    if not raw:
        return out

    s = raw.strip()
    m = re.match(r"^(20\d{2})\s*", s)
    if m:
        s = s[m.end():]

    last = None
    for m in re.finditer(r"[（(]([^（()）]*)[）)]\s*$", s):
        last = m
    if not last:
        out["name"] = s.strip()
        return out

    parts = [p.strip() for p in re.split(r"[・･]", last.group(1)) if p.strip()]
    slots, rest = [], []
    for part in parts:
        mm = re.fullmatch(rf"([{DAYS}])\s*(\d+)", part)
        if mm:
            slots.append((DAYS.index(mm.group(1)), int(mm.group(2))))
        else:
            rest.append(part)

    if not slots:
        out["name"] = s.strip()  # 曜日時限が無い括弧は科目名の一部
        return out

    out["day_of_week"], out["period"] = slots[0]
    out["slot"] = "・".join(f"{DAYS[d]}{p}" for d, p in slots)
    out["name"] = s[:last.start()].strip()

    if rest and rest[-1] in ("前", "後", "前期", "後期", "通年"):
        out["term"] = rest.pop()
    if rest:
        out["teacher"] = rest[-1]
    return out
