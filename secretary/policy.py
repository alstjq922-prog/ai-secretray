"""정책 비서: 언론 비서가 한 주간 모은 사례를 바탕으로 화성시 적용 정책안을 만든다(주 1회)."""
from .common import COMMON_RULES, ask_claude

SHAPE = {"proposals": [{
    "title": str,
    "category": str,
    "background": str,
    "idea": str,
    "reference": str,
    "steps": [str],
    "difficulty": ("낮음", "보통", "높음"),
}]}


def run(cfg, press_history):
    c = cfg["policy"]
    if not press_history:
        return []
    cases = "\n".join(
        f"- [{p.get('org')}] {p.get('title')} | {p.get('summary')} | 적용점: {p.get('hwaseong_point')}"
        for p in press_history[-120:]
    )
    system = COMMON_RULES + (
        f"\n[정책 비서] 아래 화성시 현황과 최근 타 지자체 사례를 근거로 화성시에 적용할 정책안 {c['count']}건을 만든다. "
        "단순 베끼기가 아니라 화성시 특성에 맞게 변형한다. reference에는 근거가 된 지자체 사례를 적는다. "
        "background는 왜 화성에 필요한지, idea는 핵심 내용, steps는 추진 단계 3개 이내."
    )
    user = f"[화성시 현황]\n{c['hwaseong_profile']}\n\n[최근 타 지자체 사례]\n{cases}"
    return ask_claude(system, user, SHAPE)["proposals"]
