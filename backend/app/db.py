"""DB への入口。

画面からの要求は必ず `user_conn(user_id)` を通す。これが
「この取引は ◯◯さんの操作です」と DB に名乗る場所で、RLS はその名乗りを見て行を隠す。

例えるなら、ロッカールームの入口で毎回学生証をかざすようなもの。
かざさずに入ると（app.user_id が空のまま）、どのロッカーも開かない。
"""

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import Connection, create_engine, text
from sqlalchemy.engine import Engine

from . import config

_app_engine: Engine | None = None
_system_engine: Engine | None = None


def app_engine() -> Engine:
    global _app_engine
    if _app_engine is None:
        _app_engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
    return _app_engine


def system_engine() -> Engine:
    global _system_engine
    if _system_engine is None:
        _system_engine = create_engine(config.SYSTEM_DATABASE_URL, pool_pre_ping=True)
    return _system_engine


def reset_engines() -> None:
    """テスト用。設定を差し替えたあとで作り直す。"""
    global _app_engine, _system_engine
    for e in (_app_engine, _system_engine):
        if e is not None:
            e.dispose()
    _app_engine = _system_engine = None


@contextmanager
def user_conn(user_id: UUID | str) -> Iterator[Connection]:
    """本人として DB を触る。抜けるときに確定（例外なら取り消し）。

    set_config の第3引数 true は「この取引の間だけ」。
    接続はプールで使い回されるので、取引をまたいで名乗りが残ると
    次の人の要求が前の人として動いてしまう。だから必ず取引単位にする。
    """
    with app_engine().begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user_id)})
        yield conn


@contextmanager
def system_conn() -> Iterator[Connection]:
    """RLS をすり抜ける接続。ログインと定期取り込みの一覧だけで使う。"""
    with system_engine().begin() as conn:
        yield conn
