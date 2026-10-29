"""일정 비서: 구글 캘린더 비공개 iCal 주소로 일정을 읽고 할 일·준비사항을 브리핑."""
import os
from datetime import datetime, timedelta

import icalendar
import recurring_ical_events
import requests

from .common import KST, COMMON_RULES, ask_claude, now

SHAPE = {
    "headline": str,
    "events": [{"idx": int, "prep": [str], "note": str}],
    "todos": [str],
}


def fetch_events(days):
    urls = [u.strip() for u in os.environ.get("CALENDAR_ICS_URLS", "").split(",") if u.strip()]
    start = now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=days)
    events = []
    for url in urls:
        cal = icalendar.Calendar.from_ical(requests.get(url, timeout=30).content)
        for ev in recurring_ical_events.of(cal).between(start, end):
            s = ev.get("DTSTART").dt
            all_day = not isinstance(s, datetime)
            if all_day:
                s = datetime.combine(s, datetime.min.time(), KST)
            events.append({
                "title": str(ev.get("SUMMARY", "(제목 없음)")),
                "start": s.astimezone(KST).isoformat(),
                "all_day": all_day,
                "location": str(ev.get("LOCATION", "")),
                "memo": str(ev.get("DESCRIPTION", ""))[:200],
            })
    return sorted(events, key=lambda e: e["start"])


def run(cfg):
    c = cfg["schedule"]
    events = fetch_events(c["days"])
    if not events:
        return {"headline": "향후 일정 없음", "events": [], "todos": []}

    lines = "\n".join(
        f"[{i}] {e['start'][:16].replace('T', ' ')}{' (종일)' if e['all_day'] else ''} {e['title']}"
        f" @{e['location']} {e['memo']}" for i, e in enumerate(events)
    )
    system = COMMON_RULES + (
        "\n[일정 비서] 오늘 날짜 기준으로 일정을 보고 브리핑한다. headline은 오늘·내일 핵심 1문장. "
        "events에는 준비가 필요한 일정만 넣고 prep에 준비물·사전 확인사항(자료, 의전, 동선, 참석자 파악 등)을 최대 3개. "
        "note는 주의사항(겹치는 일정, 이동 시간 등) 없으면 빈 문자열. todos는 오늘 꼭 할 일 최대 5개."
    )
    user = f"오늘: {now():%Y-%m-%d (%a) %H:%M}\n{c.get('my_role', '')}\n\n[일정]\n{lines}"
    out = ask_claude(system, user, SHAPE)
    preps = {r["idx"]: r for r in out["events"]}
    return {
        "headline": out["headline"],
        "todos": out["todos"],
        "events": [{**e, "prep": preps.get(i, {}).get("prep", []), "note": preps.get(i, {}).get("note", "")}
                   for i, e in enumerate(events)],
    }
