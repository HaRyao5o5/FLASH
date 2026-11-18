"""鍵を2本作る。`python -m app.tools.make_key`（表示だけ）/ `--write`（.env に書き込む）

--write は、.env が無ければ .env.example から作り、**空の鍵だけ**埋める。
すでに値が入っている鍵は絶対に上書きしない（FLASH_ENCRYPTION_KEY を変えると、
保存済みの接続が全部読めなくなるため）。
"""

import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parent.parent.parent


def new_keys() -> dict[str, str]:
    return {"FLASH_SECRET_KEY": secrets.token_urlsafe(48),
            "FLASH_ENCRYPTION_KEY": Fernet.generate_key().decode()}


def write_env(env: Path, example: Path) -> list[str]:
    if not env.exists():
        env.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    lines = env.read_text(encoding="utf-8").splitlines()
    keys, filled = new_keys(), []
    for i, line in enumerate(lines):
        name, sep, value = line.partition("=")
        if sep and name.strip() in keys and not value.strip():
            lines[i] = f"{name.strip()}={keys[name.strip()]}"
            filled.append(name.strip())
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return filled


if __name__ == "__main__":
    if "--write" in sys.argv:
        filled = write_env(BACKEND / ".env", BACKEND / ".env.example")
        print("書き込みました: " + ", ".join(filled) if filled else "鍵はもう入っています（何も変えていません）")
    else:
        for k, v in new_keys().items():
            print(f"{k}={v}")
