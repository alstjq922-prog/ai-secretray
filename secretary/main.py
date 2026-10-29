"""AI 비서실 실행기. GitHub Actions가 정해진 시간에 실행한다.
사용: python -m secretary.main [비서이름 ...]   (이름 생략 시 전체)"""
import sys
import traceback
from datetime import datetime, timedelta

from . import assembly, opinion, policy, press, schedule, sns, store
from .common import load_config, now

ORDER = {"상": 0, "중": 1, "하": 2}


def keep_recent(new, old, days, key="link"):
    """새 보고 + 최근 N일 내 이전 보고를 합친다(필요할 때 들어와도 지난 보고가 남아 있도록)."""
    cutoff = (now() - timedelta(days=days)).isoformat()
    keys = {r.get(key) for r in new}
    merged = new + [r for r in old if r.get(key) not in keys and (r.get("reported") or "") >= cutoff]
    return sorted(merged, key=lambda r: (ORDER.get(r.get("priority"), 3), -_ts(r.get("reported"))))


def _ts(s):
    return datetime.fromisoformat(s).timestamp() if s else 0


def stamp(items):
    t = now().isoformat()
    for r in items:
        r.setdefault("reported", t)
    return items


def main(only):
    cfg = load_config()
    data = store.load()
    sec = data.setdefault("secretaries", {})
    seen = set(data.get("seen", []))
    errors = {}

    def want(name):
        return not only or name in only

    def section(name, fn):
        if not want(name):
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

    def do_press():
        s = sec.setdefault("press", {})
        s["items"] = keep_recent(stamp(press.run(cfg, seen)), s.get("items", []), keep)

    def do_policy():
        s = sec.setdefault("policy", {})
        last = s.get("generated")
        if last and now() - datetime.fromisoformat(last) < timedelta(days=cfg["policy"]["every_days"]) and "policy" not in only:
            print("  이번 주 정책안 이미 생성 → 건너뜀")
            return
        week_ago = (now() - timedelta(days=7)).isoformat()
        history = [p for p in sec.get("press", {}).get("items", []) if (p.get("reported") or "") >= week_ago]
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

    def do_schedule():
        sec.setdefault("schedule", {}).update(schedule.run(cfg))

    section("schedule", do_schedule)
    section("sns", do_sns)
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
