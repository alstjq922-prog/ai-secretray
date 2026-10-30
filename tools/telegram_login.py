"""텔레그램 최초 로그인(내 PC에서 1회만 실행).
출력되는 세션 문자열을 GitHub 비밀값 TELEGRAM_SESSION에 넣는다.
세션 문자열은 내 계정 로그인과 같으므로 다른 곳에 저장·공유하지 않는다.

    pip install telethon
    python tools/telegram_login.py
"""
from telethon.sessions import StringSession
from telethon.sync import TelegramClient

api_id = int(input("api_id: "))
api_hash = input("api_hash: ").strip()

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("\n[내 단체방 이름] 아래 이름을 그대로 TELEGRAM_CHATS에 쉼표로 이어 넣으세요.")
    for d in client.iter_dialogs():
        if d.is_group or d.is_channel:
            print(" -", d.name)
    print("\n[TELEGRAM_SESSION 값]\n" + client.session.save())
