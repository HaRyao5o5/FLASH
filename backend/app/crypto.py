"""利用者がつないだ URL を暗号化して持つ。

Canvas のカレンダーフィードの URL は **それ自体が鍵**（知っている人は誰でも予定を読める）。
DB がまるごと漏れても URL が読めないように、鍵（FLASH_ENCRYPTION_KEY）で包んでから入れる。
鍵は DB とは別の場所（環境変数・fly secrets）に置く。金庫と金庫の鍵を同じ引き出しに入れない。
"""

from cryptography.fernet import Fernet, InvalidToken

from . import config


def _fernet() -> Fernet:
    if not config.ENCRYPTION_KEY:
        raise RuntimeError("FLASH_ENCRYPTION_KEY が設定されていません")
    return Fernet(config.ENCRYPTION_KEY.encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        # 鍵を作り直した・別の環境の DB を持ってきた、のどちらか
        raise RuntimeError("保存した接続を復号できません（暗号の鍵が変わった可能性）") from e
