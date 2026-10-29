"""언론 비서: 전국 지자체의 '최초'·우수 정책 기사 중 꼭 볼 것만 선별."""
from .common import (COMMON_RULES, ask_claude, dedupe, drop_keywords, items_for_prompt,
                     naver_search, pick, within)

SHAPE = {"reports": [{
    "idx": int,
    "org": str,
    "priority": ("상", "중", "하"),
    "category": str,
    "summary": str,
    "hwaseong_point": str,
}]}


def run(cfg, seen):
    c = cfg["press"]
    raw = []
    for q in c["queries"]:
        raw += naver_search("news", q, display=100)
    items = [it for it in raw if within(it, c["hours"])]
    items = dedupe(drop_keywords(items, c["exclude_words"]), seen)
    if not items:
        return []

    system = COMMON_RULES + (
        f"\n[언론 비서] 전국 지자체 정책 기사 중 화성시 공무원이 꼭 봐야 할 기사를 최대 {c['max_reports']}건 고른다. "
        "우선순위: ①'전국 최초' 등 선도 정책 ②수도권·대도시(인구 100만 내외, 신도시·산업도시)에 적용 가능한 정책 "
        "③화성시와 경쟁·비교되는 도시(수원·용인·고양·성남 등) 동향 ④경기도·중앙정부 공모·예산 관련. "
        "단순 행사·수상·인사 기사는 제외. org는 지자체명, category는 분야(복지/교통/산업/환경/행정/청년 등). "
        "summary는 정책 내용 1~2문장, hwaseong_point는 화성시 적용 아이디어 1문장."
    )
    out = ask_claude(system, f"[기사 목록]\n{items_for_prompt(items)}", SHAPE)

    reports = []
    for r in out["reports"]:
        src = pick(items, r["idx"])
        if src:
            reports.append({**r, "title": src["title"], "link": src["link"], "date": src["date"]})
    seen.update(it["link"] for it in items)
    return reports
