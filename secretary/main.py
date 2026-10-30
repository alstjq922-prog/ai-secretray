"""AI 비서실 실행기. GitHub Actions가 15분마다 실행하고, 주기가 된 비서만 일한다.
사용: python -m secretary.main [비서이름 ...]   (이름을 주면 주기와 상관없이 그 비서만 실행)"""
import sys
import traceback
from datetime import datetime, timedelta

from . import assembly, opinion, policy, press, sns, store, telegram
from .common import load_config, now

ORDER = {"상": 0, "중": 1, "하": 2}
JITTER_MIN = 3  # GitHub 실행 시각이 조금씩 밀리는 것을 감안


def keep_recent(new, old, days, key="link"):
    """새 보고 + 최근 N일 내 이전 보고를 합친다(필요할 때 들어와도 지난 보고가 남아 있도록)."""
    cutoff = now() - timedelta(days=days)
    keys = {r.get(key) for r in new}
    kept = [r for r in old if r.get(key) not in keys and _dt(r.get("reported")) >= cutoff]
    return sorted(new + kept, key=lambda r: (ORDER.get(r.get("priority"), 3), -_dt(r.get("reported")).timestamp()))


def _dt(s):
    return datetime.fromisoformat(s) if s else now() - timedelta(days=3650)


def stamp(items):
    t = now().isoformat()
    for r in items:
        r.setdefault("reported", t)
    return items


def main(only):
    cfg = load_config()
    data = store.load()
    sec = data.setdefault("secretaries", {})
    sec.pop("schedule", None)  # 없어진 일정 비서의 이전 데이터 삭제
    seen = set(data.get("seen", []))
    errors = {}

    def due(name):
        if only:
            return name in only
        minutes = cfg["intervals"].get(name, 0)
        last = sec.get(name, {}).get("updated")
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

    keep = cfg["keep_days"]

    def do_sns():
        s = sec.setdefault("sns", {})
        s["items"] = keep_recent(stamp(sns.run(cfg, seen)), s.get("items", []), keep)

    def do_telegram():
        s = sec.setdefault("telegram", {})
        tg_state = data.setdefault("telegram_state", {})
        s["items"] = keep_recent(stamp(telegram.run(cfg, tg_state, seen)), s.get("items", []), keep)

    def do_press():
        s = sec.setdefault("press", {})
        s["items"] = keep_recent(stamp(press.run(cfg, seen)), s.get("items", []), keep)

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
        sec.setdefault("opinion", {}).update(opinion.run(cfg))

    section("sns", do_sns)
    if telegram.enabled():
        section("telegram", do_telegram)
    section("press", do_press)
    section("policy", do_policy)
    section("assembly", do_assembly)
    section("opinion", do_opinion)

    data["seen"] = list(seen)[-5000:]
    data["updated"] = now().isoformat()
    store.save(data)
    print("저장 완료" + (f" (실패: {', '.join(errors)})" if errors else ""))


if __name__ == "__main__":
    main(set(sys.argv[1:]))
