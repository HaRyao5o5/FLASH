"""ログイン。

JARVIS はパスワード1本だった（自分しか使わないので）。FLASH は人ごとに入口が要る。
**FLASH 自身はパスワードを持たない。** 「この人は日大の学生で、招待リストに入っている」
ことを Google に確かめてもらうだけにする。

例えるなら、寮の入口で学生証を見せてもらう方式。FLASH は合鍵を作らないし、
学生証のコピーも取らない。見るのは「名前・メール・日大の人か」だけ。

### Google に求める権限は最小

`openid email profile` だけ。カレンダーや Gmail の権限を足すと、
Google の審査（と、通るまでの 100人の上限・警告画面）が必要になる。

### 開発用ログイン

手元で Google の設定をせずに動かすための入口。メールを打つだけで入れる。
**FLASH_ENV=production では、設定に何を書いても開かない**（config.DEV_LOGIN）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import text

from . import config, db

router = APIRouter()

_oauth = None


def _google():
    """Authlib の Google クライアント。設定が無ければ None。"""
    global _oauth
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        return None
    if _oauth is None:
        from authlib.integrations.starlette_client import OAuth
        _oauth = OAuth()
        _oauth.register(
            name="google",
            client_id=config.GOOGLE_CLIENT_ID,
            client_secret=config.GOOGLE_CLIENT_SECRET,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
    return _oauth.google


# ---- 入れてよい人か ---------------------------------------------------------

def is_allowed(email: str) -> tuple[bool, str]:
    e = (email or "").strip().lower()
    if not e or "@" not in e:
        return False, "メールアドレスが取れませんでした"
    if config.ALLOWED_DOMAIN and e.rsplit("@", 1)[1] != config.ALLOWED_DOMAIN:
        return False, f"{config.ALLOWED_DOMAIN} のアカウントでログインしてください"
    if config.ALLOWED_EMAILS and e not in config.ALLOWED_EMAILS:
        return False, "まだ招待されていないアカウントです。管理者に伝えてください"
    return True, ""


def _upsert_user(email: str, name: str | None, google_sub: str | None) -> str:
    """利用者を作る／更新して id を返す。**まだ誰か分からない段階**なので SYSTEM 接続。"""
    email = email.strip().lower()
    with db.system_conn() as conn:
        row = None
        if google_sub:
            row = conn.execute(text("SELECT id FROM users WHERE google_sub = :s"),
                               {"s": google_sub}).first()
        if row is None:
            row = conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": email}).first()
        if row is None:
            row = conn.execute(text("""
                INSERT INTO users (email, name, google_sub, last_login_at)
                VALUES (:e, :n, :s, now()) RETURNING id"""),
                {"e": email, "n": name, "s": google_sub}).first()
        else:
            conn.execute(text("""
                UPDATE users SET email = :e, name = COALESCE(:n, name),
                       google_sub = COALESCE(:s, google_sub), last_login_at = now()
                 WHERE id = :id"""), {"e": email, "n": name, "s": google_sub, "id": row.id})
        return str(row.id)


# ---- 今ログインしている人 ------------------------------------------------------

def current_user(request: Request) -> dict:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401, "ログインしてください")
    with db.user_conn(uid) as conn:
        row = conn.execute(text("SELECT id, email, name FROM users")).mappings().first()
    if row is None:  # 消された・別のDBに切り替わった
        request.session.clear()
        raise HTTPException(401, "ログインしてください")
    return {"id": str(row["id"]), "email": row["email"], "name": row["name"],
            "is_admin": row["email"] in config.ADMIN_EMAILS}


CurrentUser = Depends(current_user)


# ---- 入口 ----------------------------------------------------------------

@router.get("/api/auth/options")
def options():
    return {"google": _google() is not None, "dev": config.DEV_LOGIN}


@router.get("/auth/google")
async def google_login(request: Request):
    g = _google()
    if g is None:
        raise HTTPException(404, "Google ログインは設定されていません")
    return await g.authorize_redirect(request, f"{config.BASE_URL}/auth/google/callback")


@router.get("/auth/google/callback")
async def google_callback(request: Request):
    g = _google()
    if g is None:
        raise HTTPException(404)
    try:
        token = await g.authorize_access_token(request)
    except Exception:
        return RedirectResponse("/login?error=google")
    info = token.get("userinfo") or {}
    if not info.get("email_verified"):
        return RedirectResponse("/login?error=unverified")
    ok, why = is_allowed(info.get("email", ""))
    if not ok:
        request.session.clear()
        return RedirectResponse(f"/login?error=denied&why={why}")
    uid = _upsert_user(info["email"], info.get("name"), info.get("sub"))
    request.session.clear()
    request.session["uid"] = uid
    return RedirectResponse("/")


class DevLogin(BaseModel):
    email: str


@router.post("/api/auth/dev-login")
def dev_login(body: DevLogin, request: Request):
    if not config.DEV_LOGIN:
        raise HTTPException(404)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(400, "メールアドレスを入れてください")
    uid = _upsert_user(email, email.split("@")[0], None)
    request.session.clear()
    request.session["uid"] = uid
    return {"ok": True}


@router.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@router.get("/api/me")
def me(user: dict = CurrentUser):
    return user
