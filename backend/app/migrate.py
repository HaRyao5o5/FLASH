"""DB の形を最新にする。`python -m app.migrate`

migrations/ の SQL を番号順に、まだ流していないものだけ流す。
Alembic のような道具も使えるが、今の規模なら「SQL を順に流すだけ」のほうが
中身が全部見えて分かりやすい（JARVIS の schema.sql と同じ考え方）。

**一度流した SQL は書き換えない。** 直したいときは 002_… を足す。
書き換えても、もう流れたDBには反映されないので、手元と本番がずれる。
"""

from pathlib import Path

from sqlalchemy import create_engine, text

from . import config

MIGRATIONS = Path(__file__).resolve().parent.parent / "migrations"


def run(url: str | None = None) -> list[str]:
    engine = create_engine(url or config.SYSTEM_DATABASE_URL)
    applied_now = []
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
              name       text PRIMARY KEY,
              applied_at timestamptz NOT NULL DEFAULT now()
            )"""))
        done = {r[0] for r in conn.execute(text("SELECT name FROM schema_migrations"))}
        for f in sorted(MIGRATIONS.glob("*.sql")):
            if f.name in done:
                continue
            # 1ファイルに複数の文が入っているので、ドライバ直で丸ごと流す
            conn.exec_driver_sql(f.read_text(encoding="utf-8"))
            conn.execute(text("INSERT INTO schema_migrations (name) VALUES (:n)"), {"n": f.name})
            applied_now.append(f.name)
    engine.dispose()
    return applied_now


if __name__ == "__main__":
    names = run()
    print("流したもの: " + (", ".join(names) if names else "なし（最新です）"))
