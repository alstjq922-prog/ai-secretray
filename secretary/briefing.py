"""텔레그램 브리핑: 정해진 시각(기본 06:30·13:00·20:00)에 지난 브리핑 이후 새 보고를 모아 봇으로 보낸다.
- 단체방을 읽는 정보 비서(내 계정)와 별개로, 알림이 울리도록 '봇'이 나에게 보낸다.
- GitHub 자동 실행은 늦게 시작되는 일이 많아, 각 시각 몇십 분 전에 미리 실행해 두고 정시까지 기다렸다 보낸다.
- 받는 사람(chat_id): 비밀값 TELEGRAM_BOT_CHAT_ID가 없으면, 봇에게 /start를 보낸 대화를 찾아 암호화 저장소에 기억한다.
- 공개 저장소의 실행 기록에 내용이 남지 않도록 보고 내용·chat_id는 출력하지 않는다."""
import html
import os
import time
from datetime import datetime, timedelta

import requests

from .common import now

ORDER = {"상": 0, "중": 1, "하": 2}
DOT = {"상": "🔴", "중": "🟠", "하": "⚪"}
LIMIT = 3900  # 텔레그램 한 메시지 4096자 제한에 여유


def enabled():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN"))


def _api(method, **params):
    r = requests.post(f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN'].strip()}/{method}",
                      json=params, timeout=30)
    j = r.json()
    if not j.get("ok"):
        raise RuntimeError(f"텔레그램 봇 {method} 실패: {j.get('description')}")
    return j["result"]


def _chat_id(state):
    cid = os.environ.get("TELEGRAM_BOT_CHAT_ID", "").strip() or state.get("chat_id")
    if cid:
        return cid
    for u in _api("getUpdates", limit=100):
        chat = (u.get("message") or {}).get("chat") or {}
        if chat.get("type") == "private":
            state["chat_id"] = chat["id"]
            return chat["id"]
    raise RuntimeError("받을 사람을 찾지 못함: 텔레그램에서 내 봇에게 /start 를 먼저 보내 주세요")


def _slot(times, early):
    """지금 보낼 차례인 시각. 정시 early분 전부터 해당. 오늘·어제 시각 중 가장 최근 것."""
    t = now()
    cands = []
    for day in (t - timedelta(days=1), t):
        for hm in times:
            h, m = map(int, str(hm).split(":"))
            cands.append(day.replace(hour=h, minute=m, second=0, microsecond=0))
    past = [s for s in cands if s - timedelta(minutes=early) <= t]
    return max(past) if past else None


def _dt(s):
    return datetime.fromisoformat(s) if s else None


def _new(items, since):
    out = [r for r in items if _dt(r.get("reported")) and _dt(r["reported"]) > since]
    return sorted(out, key=lambda r: (ORDER.get(r.get("priority"), 3), -r.get("heat", 1)))


def _e(s):
    return html.escape(str(s or ""), quote=False)


def _a(text, url):
    url = url or ""
    return f'<a href="{html.escape(url)}">{_e(text)}</a>' if url.startswith("http") else _e(text)


def _section(title, items, line, n):
    if not items:
        return []
    out = [f"\n<b>{title}</b> 새 {len(items)}건"]
    out += [line(r) for r in items[:n]]
    if len(items) > n:
        out.append(f"  …외 {len(items) - n}건은 대시보드에서")
    return out


def compose(data, since, slot, cfg):
    n = cfg.get("per_section", 5)
    sec = data.get("secretaries", {})
    S = lambda k: sec.get(k, {})
    lines = [f"📋 <b>AI 비서실 {slot:%m/%d %H:%M} 브리핑</b>"]

    op = S("opinion")
    if _dt(op.get("updated")) and _dt(op["updated"]) > since and op.get("brief"):
        lines += ["\n<b>🗣 여론 종합</b>", _e(op["brief"])]
        lines += [f"• {_e(c)}" for c in (op.get("changes") or [])[:3]]
        urgent = [l for l in op.get("local", []) if l.get("priority") in ("상", "중")]
        if urgent:
            lines.append("<b>화성 민원</b>")
            lines += [f"{DOT[l['priority']]} [{_e(l.get('area'))}] {_e(l['issue'])} — {_e(l.get('action'))}" for l in urgent[:3]]

    heat = lambda r: f" (관련 보도 {r['heat']}건)" if r.get("heat", 1) > 1 else ""
    lines += _section("📣 SNS", _new(S("sns").get("items", []), since),
                      lambda r: f"{DOT.get(r.get('priority'), '•')} {_e(r.get('person'))}: {_a(r.get('summary'), r.get('link'))}{heat(r)}", n)
    lines += _section("💬 정보(단체방)", _new(S("telegram").get("items", []), since),
                      lambda r: f"{DOT.get(r.get('priority'), '•')} {_a(r.get('summary'), r.get('link'))}", n)
    lines += _section("📰 언론", _new(S("press").get("items", []), since),
                      lambda r: f"{DOT.get(r.get('priority'), '•')} [{_e(r.get('org'))}] {_a(r.get('summary') or r.get('title'), r.get('link'))}{heat(r)}", n)
    lines += _section("🏛 국회", _new(S("assembly").get("bills", []), since),
                      lambda r: f"{DOT.get(r.get('priority'), '•')} ({_e(r.get('stage'))}) {_a(r.get('title'), r.get('link'))}", n)

    if len(lines) == 1:
        lines.append("\n지난 브리핑 이후 새 보고 없음")
    errors = [k for k, v in sec.items() if isinstance(v, dict) and v.get("error")]
    if errors:
        lines.append(f"\n⚠️ 수집 실패 중: {', '.join(errors)} (대시보드 확인)")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if "/" in repo:
        owner, name = repo.split("/")
        lines.append(f'\n<a href="https://{owner.lower()}.github.io/{name}/">대시보드 열기</a>')
    return lines


def _chunks(lines):
    out, cur = [], ""
    for l in lines:
        if cur and len(cur) + len(l) + 1 > LIMIT:
            out.append(cur)
            cur = ""
        cur += l[:LIMIT] + "\n"
    return out + ([cur] if cur else [])


def run(cfg, data, force=False):
    """보낼 차례면 보내고 True. force=True면 시각과 상관없이 지금 보냄(시험용, 기록은 남기지 않음)."""
    c = cfg["briefing"]
    state = data.setdefault("briefing", {})
    slot = _slot(c["times"], c.get("early_minutes", 25))
    if not force:
        if slot is None or state.get("last_slot") == slot.isoformat():
            return False
        if now() - slot > timedelta(hours=3):  # 너무 늦었으면(실행이 오래 멈췄던 경우) 다음 시각을 기다림
            return False
        wait = (slot - now()).total_seconds()
        if wait > 0:
            print(f"  브리핑 시각까지 {int(wait // 60)}분 대기")
            time.sleep(wait)
    since = _dt(state.get("last_sent")) or now() - timedelta(hours=12)
    cid = _chat_id(state)
    for text in _chunks(compose(data, since, slot or now(), c)):
        _api("sendMessage", chat_id=cid, text=text, parse_mode="HTML", disable_web_page_preview=True)
    if not force:
        state["last_slot"], state["last_sent"] = slot.isoformat(), now().isoformat()
    print("  브리핑 전송 완료")
    return True
