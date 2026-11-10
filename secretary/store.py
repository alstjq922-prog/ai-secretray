"""보고서 저장소. 공개 저장소에 올라가도 내용이 보이지 않도록 비밀번호로 암호화한다.
브라우저(index.html)는 같은 방식(PBKDF2-SHA256 → AES-GCM)으로 복호화한다."""
import base64
import json
import os
import time

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from .common import ROOT

DATA_FILE = ROOT / "docs" / "data.enc"
ITERATIONS = 200_000


def _key(password, salt):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=ITERATIONS)
    return kdf.derive(password.encode())


def save(data):
    salt, iv = os.urandom(16), os.urandom(12)
    ct = AESGCM(_key(os.environ["DASHBOARD_PASSWORD"], salt)).encrypt(
        iv, json.dumps(data, ensure_ascii=False).encode(), None
    )
    b64 = lambda b: base64.b64encode(b).decode()
    DATA_FILE.parent.mkdir(exist_ok=True)
    DATA_FILE.write_text(json.dumps({"salt": b64(salt), "iv": b64(iv), "ct": b64(ct), "iter": ITERATIONS}))


def _read_previous():
    """이전 보고서를 읽는다. 보통은 Actions 캐시가 복원해 둔 파일을 쓰고,
    캐시가 없을 때만 게시된 웹페이지에서 가져온다(웹페이지는 몇 분간 이전 내용이 보일 수 있음).
    ※ data.enc를 저장소에 커밋하면 매번 그 옛날 파일부터 시작하게 되므로 커밋하지 않는다(.gitignore)."""
    if DATA_FILE.exists():
        return DATA_FILE.read_text()
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    owner, name = repo.split("/")
    r = requests.get(
        f"https://{owner.lower()}.github.io/{name}/data.enc",
        params={"t": int(time.time())}, headers={"Cache-Control": "no-cache"}, timeout=30,
    )
    if r.status_code == 404:  # 첫 실행
        return None
    r.raise_for_status()  # 일시 장애 때 빈 상태로 덮어쓰지 않도록 실패 처리
    return r.text


def load():
    text = _read_previous()
    if text is None:
        return {}
    env = json.loads(text)
    d = lambda k: base64.b64decode(env[k])
    try:
        pt = AESGCM(_key(os.environ["DASHBOARD_PASSWORD"], d("salt"))).decrypt(d("iv"), d("ct"), None)
    except Exception:
        print("기존 데이터 복호화 실패(비밀번호 변경?) → 새로 시작")
        return {}
    return json.loads(pt)
