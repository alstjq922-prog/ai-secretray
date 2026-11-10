"""SNS 모니터링 비서.
페이스북은 외부 수집이 막혀 있어 '언론이 인용한 SNS 발언'(네이버 뉴스)과 네이버 블로그로 파악한다.
- name이 있으면 이름으로, 없으면 직책(key 또는 role)으로 검색한다. 직책 검색은 개각·선거로 사람이 바뀌어도 그대로 동작한다.
- 중요도(tier)별로 검색 주기가 다르다(config의 sns.tier_minutes). 인원이 많아도 네이버 하루 한도를 넘지 않게 하기 위함."""
from datetime import datetime, timedelta

from .common import (COMMON_RULES, COVERAGE_RULES, FOLLOWUP_SHAPE, apply_coverage, ask_claude, dedupe,
                     drop_keywords, items_for_prompt, now, prev_for_prompt, search_many, within)

SHAPE = {
    "reports": [{
        "idx": int,
        "person": str,
        "priority": ("상", "중", "하"),
        "region": ("화성", "경기", "전국"),
        "stance": ("민주당 입장", "민주당 비판", "중립"),
        "summary": str,
        "why": str,
        "related": [int],
    }],
    "followups": FOLLOWUP_SHAPE,
}
JITTER_MIN = 3


def label(p):
    """기사에서 찾을 말: 이름이 있으면 이름, 없으면 검색용 직책."""
    return p.get("name") or p.get("key") or p["role"]


def due_tiers(c, state):
    """검색 주기가 된 등급 목록. 등급별 마지막 검색 시각은 state에 있다."""
    tiers = []
    for tier, minutes in c["tier_minutes"].items():
        last = state.get(str(tier))
        if not last or now() - datetime.fromisoformat(last) >= timedelta(minutes=minutes - JITTER_MIN):
            tiers.append(int(tier))
    return tiers


def run(cfg, seen, state, prev):
    c = cfg["sns"]
    tiers = due_tiers(c, state)
    people = [p for p in c["people"] if p.get("tier") in tiers and (p.get("name") or p.get("key") or p.get("role"))]
    reports = _run(c, people, seen, prev) if people else []
    state.update({str(t): now().isoformat() for t in tiers})  # 성공했을 때만 기록(실패하면 다음 실행 때 다시 검색)
    return reports


def _run(c, people, seen, prev):
    queries = []
    for p in people:
        queries += [(f"{label(p)} {w}", {"who": label(p)}) for w in c["news_words"]]
    raw = search_many("news", queries, display=20)
    blogs = [p for p in people if p.get("blog_id") and p.get("name")]
    if blogs:
        for it in search_many("blog", [(p["name"], {"who": p["name"], "blog_id": p["blog_id"]}) for p in blogs], display=30):
            if it["blog_id"] in it["blog"]:
                it["source"] = "본인 블로그"
                raw.append(it)

    items = [it for it in raw if within(it, c["hours"]) and it["who"] in it["title"] + it["desc"]]
    items = dedupe(drop_keywords(items, c["exclude_words"]), seen)
    if not items:
        return []

    roster = "\n".join(f"- {label(p)}: {p['role']} (중요도 {p['tier']})" for p in c["people"])
    system = COMMON_RULES + (
        "\n[SNS 모니터링 비서] 정치인 SNS 발언 보도·블로그 글 중 '쟁점이 되거나 반드시 알아야 할 것'만 고른다. "
        "단순 행사 참석·축하·인사·홍보성 글은 제외한다. 같은 발언을 다룬 여러 기사는 하나만 고른다. "
        "직책으로만 적힌 대상은 기사 속 현직자의 발언만 해당하며, person에는 기사에 나온 이름과 직책을 적는다. "
        "priority: 인물 중요도와 사안 민감도(정쟁, 화성·경기 영향, 언론 확산 가능성)를 함께 판단. "
        "stance: 민주당 입장 대변이면 '민주당 입장', 민주당·민주당 소속 인사를 비판하면 '민주당 비판'. "
        "summary는 누가 무엇을 말했는지 1~2문장, why는 내가 알아야 하는 이유 1문장. 고를 것이 없으면 빈 배열."
        + COVERAGE_RULES
    )
    user = (f"[모니터링 대상]\n{roster}\n\n[이미 보고한 사안]\n{prev_for_prompt(prev)}"
            f"\n\n[수집 목록]\n{items_for_prompt(items)}")
    out = ask_claude(system, user, SHAPE)

    reports = []
    for r in apply_coverage(out, items, prev):
        src = r.pop("src")
        reports.append({**r, "title": src["title"], "link": src["link"], "date": src["date"], "source": src["source"]})
    seen.update(it["link"] for it in items[:150])
    return reports
