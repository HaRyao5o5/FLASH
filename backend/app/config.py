"""設定。全部 環境変数（.env）から読む。

JARVIS と違って **秘密は利用者ごとに DB に入る**（暗号化して）。
ここに置くのはサイト全体で1つだけのもの: DB の場所、暗号の鍵、Google ログインの鍵。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def _bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _list(name: str) -> list[str]:
    return [x.strip().lower() for x in os.getenv(name, "").split(",") if x.strip()]


# production 以外は「手元で動かしている」とみなす。
# 開発用ログインはこれが production だと絶対に開かない。
ENV = os.getenv("FLASH_ENV", "development").strip().lower()
IS_PROD = ENV == "production"

# ---- DB ------------------------------------------------------------------
#
# **接続は2本。** ここが FLASH の安全の土台。
#
#   APP    = 利用者の操作を通す接続。行レベルセキュリティ（RLS）が効く役割で繋ぐ。
#            「今だれの操作か」を毎回 DB に伝え、DB 自身が他人の行を隠す。
#   SYSTEM = ログイン（まだ誰か分からない段階）と、定期取り込みで
#            「接続している人の一覧」を引くときだけ使う。RLS をすり抜ける。
#
# SYSTEM を使う場所は auth.py と sync.py の一覧だけに絞る。
# 画面からの要求で SYSTEM を使い始めたら、それは設計が崩れている合図。
DATABASE_URL = os.getenv(
    "FLASH_DATABASE_URL", "postgresql+psycopg://flash_app:flash_app@localhost:5432/flash")
SYSTEM_DATABASE_URL = os.getenv(
    "FLASH_SYSTEM_DATABASE_URL", "postgresql+psycopg://flash_owner:flash_owner@localhost:5432/flash")

# ---- 鍵 ------------------------------------------------------------------
# セッション（ログイン状態の cookie）に署名する鍵
SECRET_KEY = os.getenv("FLASH_SECRET_KEY", "")
# 利用者がつないだ URL などを暗号化する鍵（Fernet）。python -m app.tools.make_key で作る。
# **作り直すと、保存済みの接続が全部読めなくなる。**
ENCRYPTION_KEY = os.getenv("FLASH_ENCRYPTION_KEY", "")

# ---- 誰を入れるか ---------------------------------------------------------
#
# いまは友達2人向けなので、招待リストは環境変数で持つ。
# 人数が増えたら DB に移して、管理画面から足せるようにする。
#
# 大学の Google アカウントだけ通す。空にするとドメインで絞らない（手元の確認用）。
ALLOWED_DOMAIN = os.getenv("FLASH_ALLOWED_DOMAIN", "g.nihon-u.ac.jp").strip().lower()
# 入ってよいメールアドレス（カンマ区切り）。空なら「ドメインが合えば誰でも」。
ALLOWED_EMAILS = _list("FLASH_ALLOWED_EMAILS")
# サイトの管理者（あなた）。いまは表示を変えるだけで、他人のデータは見られない。
ADMIN_EMAILS = _list("FLASH_ADMIN_EMAILS")

# ---- Google ログイン -------------------------------------------------------
# 求めるのは「名前とメール」だけ（openid email profile）。
# カレンダーや Gmail の権限は求めない。求めた瞬間に Google の審査と 100人の壁が来る。
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
BASE_URL = os.getenv("FLASH_BASE_URL", "http://localhost:8000").rstrip("/")

# 開発用ログイン（メールを打つだけで入れる）。production では何を書いても無効。
DEV_LOGIN = _bool("FLASH_DEV_LOGIN", default=not IS_PROD) and not IS_PROD

# ---- Canvas --------------------------------------------------------------
# カレンダーフィードの取り先として許すホスト。**ここ以外の URL は受け付けない。**
CANVAS_HOST = os.getenv("FLASH_CANVAS_HOST", "nu.instructure.com").strip().lower()
# 何分おきに全員のフィードを読み直すか。0 で止まる（ボタンだけ）。
SYNC_MINUTES = int(os.getenv("FLASH_SYNC_MINUTES", "30") or 0)
# 起動してから最初の定期取り込みまでの待ち（秒）
SYNC_DELAY = int(os.getenv("FLASH_SYNC_DELAY", "30") or 0)
# 「今すぐ取り込む」を連打されても Canvas に迷惑をかけない間隔（秒）
SYNC_COOLDOWN = int(os.getenv("FLASH_SYNC_COOLDOWN", "60") or 0)

# 組み立て済みの画面（frontend/dist）。あれば / で配る。
FRONTEND_DIST = Path(os.getenv(
    "FLASH_FRONTEND_DIST",
    str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")))


def check() -> list[str]:
    """起動してよいか。問題があれば理由を返す（空なら OK）。"""
    problems = []
    if not SECRET_KEY:
        problems.append("FLASH_SECRET_KEY が空です（python -m app.tools.make_key で作れます）")
    if not ENCRYPTION_KEY:
        problems.append("FLASH_ENCRYPTION_KEY が空です（python -m app.tools.make_key で作れます）")
    if IS_PROD:
        if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
            problems.append("production では Google ログインの設定が必須です")
        if not BASE_URL.startswith("https://"):
            problems.append("production では FLASH_BASE_URL を https:// にしてください")
    return problems
