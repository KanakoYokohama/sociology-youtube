"""データ暗号化（AES-256-GCM / PBKDF2-SHA256）.

ブラウザの Web Crypto API で同じパスワードから復号できる形式で保存する。
リポジトリを公開しても、パスワードを知らない人は Studio のデータを読めない。
"""
from __future__ import annotations

import base64
import json
import os

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ITERATIONS = 310_000


def _key(password: str, salt: bytes, iterations: int) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations)
    return kdf.derive(password.encode())


def encrypt_json(obj, password: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    plain = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    ct = AESGCM(_key(password, salt, ITERATIONS)).encrypt(iv, plain, None)
    b64 = lambda b: base64.b64encode(b).decode()
    return json.dumps({"v": 1, "iter": ITERATIONS, "salt": b64(salt), "iv": b64(iv), "ct": b64(ct)})


def decrypt_json(text: str, password: str):
    d = json.loads(text)
    b = base64.b64decode
    key = _key(password, b(d["salt"]), d["iter"])
    return json.loads(AESGCM(key).decrypt(b(d["iv"]), b(d["ct"]), None))
