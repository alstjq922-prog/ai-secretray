"""AI 비서실 실행기. GitHub Actions가 15분마다 실행하고, 주기가 된 비서만 일한다.
사용: python -m secretary.main [비서이름 ...]   (이름을 주면 주기와 상관없이 그 비서만 실행)"""
import sys
import traceback
from datetime import datetime, timedelta

from . import assembly, briefing, opinion, policy, press, sns, store, telegram
from .common import Seen, load_config, now

ORDER = {"상": 0, "중": 1, "하": 2}
JITTER_MIN = 3  # GitHub 실행 시각이 조금씩 밀리는 것을 감안


def _dt(s):
    return datetime.fromisoformat(s) if s else now() - timedelta(days=3650)


def _alive(r):
    """마지막으로 보도된 시각(후속 보도가 붙으면 늦춰짐)."""
    return max(_dt(r.get("reported")), _dt(r.get("last_covered")))


def keep_recent(new, old, days, key="link", limit=None):
    """새 보고 + 최근 N일 내 이전 보고를 합친다.
    수시로 보지 않으므로, 볼 때 중요한 것이 위에 오게 정렬한다: 우선순위 → 보도량·반응(heat) → 최신순.
    limit이 있으면 그만큼만 남겨 덜 중요한 보고부터 정리한다."""
    cutoff = now() - timedelta(days=days)
    keys = {r.get(key) for r in new}
    kept = [r for r in old if r.get(key) not in keys and _alive(r) >= cutoff]
    out = sorted(new + kept, key=lambda r: (ORDER.get(r.get("priority"), 3), -r.get("heat", 1), -_alive(r).timestamp()))
    return out[:limit] if limit else out


def stamp(items):
    t = now().isoformat()
    for r in items:
        r.setdefault("reported", t)
    return items


def latest_slot(times):
    """정해진 정리 시각(예: 06:00, 13:00, 20:00) 중 지금 기준 가장 최근 것."""
    t = now()
    slots = []
    for day in (t - timedelta(days=1), t):
        for hm in times:
            h, m = map(int, str(hm).split(":"))
            slots.append(day.replace(hour=h, minute=m, second=0, microsecond=0))
    return max(s for s in slots if s <= t)


def main(only):
    cfg = load_config()
    data = store.load()
    sec = data.setdefault("secretaries", {})
    sec.pop("schedule", None)  # 없어진 일정 비서의 이전 데이터 삭제
    seen = Seen(data.get("seen"))
    errors = {}

    def due(name):
        if only:
            return name in only
        last = sec.get(name, {}).get("updated")
        if name == "opinion":  # 여론 비서는 정해진 시각에만
            return not last or _dt(last) < latest_slot(cfg["opinion"]["times"])
        minutes = cfg["intervals"].get(name, 0)
        return not last or now() - _dt(last) >= timedelta(minutes=minutes - JITTER_MIN)

    def section(name, fn):
        if not due(name):
            return
        print(f"▶ {name}")
        try:
            fn()
            sec.setdefault(name, {})["updated"] = now().isoformat()
            sec[name].pop("error", None)
        except Exception as e:
            traceback.print_exc()
            sec.setdefault(name, {})["error"] = f"{type(e).__name__}: {e}"[:300]
            errors[name] = e

    keep, limit = cfg["keep_days"], cfg.get("max_keep", 30)

    def do_sns():
        s = sec.setdefault("sns", {})
        old = s.get("items", [])
        new = sns.run(cfg, seen, data.setdefault("sns_state", {}), old)
        s["items"] = keep_recent(stamp(new), old, keep, limit=limit)

    def do_telegram():
        s = sec.setdefault("telegram", {})
        tg_state = data.setdefault("telegram_state", {})
        new = telegram.run(cfg, tg_state, seen)
        for r in new:  # 텔레그램은 반응·답글·전달 수가 곧 독자 반응
            r["heat"] = r.get("reactions", 0) + r.get("replies", 0) + r.get("forwards", 0)
        s["items"] = keep_recent(stamp(new), s.get("items", []), keep, limit=limit)

    def do_press():
        s = sec.setdefault("press", {})
        old = s.get("items", [])
        s["items"] = keep_recent(stamp(press.run(cfg, seen, old)), old, keep, limit=limit)

    def do_policy():
        s = sec.setdefault("policy", {})
        last = s.get("generated")
        if last and now() - _dt(last) < timedelta(days=cfg["policy"]["every_days"]) and "policy" not in only:
            return
        week_ago = now() - timedelta(days=7)
        history = [p for p in sec.get("press", {}).get("items", []) if _dt(p.get("reported")) >= week_ago]
        proposals = policy.run(cfg, history)
        if proposals:
            s["items"], s["generated"] = proposals, now().isoformat()

    def do_assembly():
        s = sec.setdefault("assembly", {})
        res = assembly.run(cfg, seen)
        s["bills"] = keep_recent(stamp(res["bills"]), s.get("bills", []), cfg["assembly"]["days"] + 3)
        s["council"] = keep_recent(stamp(res["council"]), s.get("council", []), keep)

    def do_opinion():
        s = sec.setdefault("opinion", {})
        out = opinion.run(cfg, s)
        out["slot"] = latest_slot(cfg["opinion"]["times"]).isoformat()
        s.update(out)

    section("sns", do_sns)
    if telegram.enabled():
        section("telegram", do_telegram)
    section("press", do_press)
    section("policy", do_policy)
    section("assembly", do_assembly)
    section("opinion", do_opinion)

    # 텔레그램 브리핑은 모든 비서가 일한 뒤에(보낼 차례일 때만). 'briefing'으로 직접 실행하면 지금 바로 시험 전송
    if briefing.enabled() and (not only or "briefing" in only):
        print("▶ briefing")
        try:
            briefing.run(cfg, data, force="briefing" in only)
            data.get("briefing", {}).pop("error", None)
        except Exception as e:
            traceback.print_exc()
            data.setdefault("briefing", {})["error"] = f"{type(e).__name__}: {e}"[:300]
            errors["briefing"] = e

    data["seen"] = seen.dump()
    data["updated"] = now().isoformat()
    store.save(data)
    print("저장 완료" + (f" (실패: {', '.join(errors)})" if errors else ""))


if __name__ == "__main__":
    main(set(sys.argv[1:]))
