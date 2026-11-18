"""FLASH の入口。`uvicorn app.main:app`（backend/ で）

ここでやるのは、組み立てだけ:
- 起動してよい設定か確かめる（鍵が空なら止まる）
- ログイン状態の cookie、書き換え系の要求への合言葉チェック
- API をつなぐ、組み立て済みの画面を配る
- 定期取り込みを回す
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, routes_canvas, sync

log = logging.getLogger("flash")

SESSION_DAYS = 30   # スマホで毎回ログインさせられると使わなくなる（JARVIS と同じ判断）


async def _sync_loop():
    """FLASH_SYNC_MINUTES ごとに全員のフィードを読み直す。"""
    await asyncio.sleep(config.SYNC_DELAY)
    while True:
        try:
            result = await asyncio.to_thread(sync.sync_all)
            log.info("定期取り込み: %s", result)
        except Exception:
            log.exception("定期取り込みで想定外の失敗")
        await asyncio.sleep(config.SYNC_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    problems = config.check()
    if problems:
        raise RuntimeError("起動できません:\n- " + "\n- ".join(problems))
    task = asyncio.create_task(_sync_loop()) if config.SYNC_MINUTES > 0 else None
    yield
    if task:
        task.cancel()


app = FastAPI(title="FLASH", lifespan=lifespan, docs_url=None if config.IS_PROD else "/api/docs",
              redoc_url=None, openapi_url=None if config.IS_PROD else "/api/openapi.json")


# ---- 書き換え系の要求には合言葉ヘッダを求める（CSRF 対策） ------------------------
#
# 別のサイトに仕込まれたフォームから、ログイン中の人のブラウザ経由で
# 「Canvas を切る」などを勝手に送らせる攻撃がある。
# ブラウザは、別のサイトから独自ヘッダ付きの要求を勝手には送らせない。
# だから「X-FLASH: 1 が付いていない書き換えは断る」だけで、その手が塞がる。
# 画面（frontend/src/api.ts）は全部の要求にこれを付けている。
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def require_flash_header(request: Request, call_next):
    if request.method in UNSAFE and request.url.path.startswith("/api/"):
        if request.headers.get("x-flash") != "1":
            return JSONResponse({"detail": "不正な要求です"}, status_code=403)
    return await call_next(request)


# 中間処理は「後に足したものが外側」。セッションを一番外にして、上の検査からも読めるようにする
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY or "dev-only-not-secret",
    session_cookie="flash_session",
    max_age=SESSION_DAYS * 86400,
    same_site="lax",
    https_only=config.IS_PROD,
)

app.include_router(auth.router)
app.include_router(routes_canvas.router)


@app.get("/api/health")
def health():
    return {"ok": True}


# ---- 画面（React を組み立てた frontend/dist）を配る -----------------------------
#
# /api と /auth 以外は全部 index.html を返す。画面の中の移動（/courses など）は
# React 側が受け持つので、サーバーはどの道でも同じ入口を渡せばいい。
if config.FRONTEND_DIST.is_dir():
    assets = config.FRONTEND_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith(("api/", "auth/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = (config.FRONTEND_DIST / path).resolve()
        if path and f.is_file() and config.FRONTEND_DIST.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(config.FRONTEND_DIST / "index.html")
