"""SNS 모니터링 비서.
페이스북은 외부 수집이 막혀 있어 '언론이 인용한 SNS 발언'(네이버 뉴스)과 네이버 블로그로 파악한다."""
from .common import (COMMON_RULES, ask_claude, dedupe, drop_keywords, items_for_prompt,
                     naver_search, pick, within)

SHAPE = {"reports": [{
    "idx": int,
    "person": str,
    "priority": ("상", "중", "하"),
    "region": ("화성", "경기", "전국"),
    "stance": ("민주당 입장", "민주당 비판", "중립"),
    "summary": str,
    "why": str,
}]}


def run(cfg, seen):
    c = cfg["sns"]
    people = [p for p in c["people"] if p.get("name")]
    raw = []
    for p in people:
        for word in c["news_words"]:
            for it in naver_search("news", f"{p['name']} {word}", display=20):
                it["who"] = p["name"]
                raw.append(it)
        if p.get("blog_id"):
            for it in naver_search("blog", p["name"], display=30):
                if p["blog_id"] in it["blog"]:
                    it["who"], it["source"] = p["name"], "본인 블로그"
                    raw.append(it)

    items = [it for it in raw if within(it, c["hours"]) and it["who"] in it["title"] + it["desc"]]
    items = dedupe(drop_keywords(items, c["exclude_words"]), seen)
    if not items:
        return []

    roster = "\n".join(f"- {p['name']}: {p['role']} (중요도 {p['tier']})" for p in people)
    system = COMMON_RULES + (
        "\n[SNS 모니터링 비서] 정치인 SNS 발언 보도·블로그 글 중 '쟁점이 되거나 반드시 알아야 할 것'만 고른다. "
        "단순 행사 참석·축하·인사·홍보성 글은 제외한다. 같은 발언을 다룬 여러 기사는 하나만 고른다. "
        "priority: 인물 중요도와 사안 민감도(정쟁, 화성·경기 영향, 언론 확산 가능성)를 함께 판단. "
        "stance: 민주당 입장 대변이면 '민주당 입장', 민주당·민주당 소속 인사를 비판하면 '민주당 비판'. "
        "summary는 누가 무엇을 말했는지 1~2문장, why는 내가 알아야 하는 이유 1문장. 고를 것이 없으면 빈 배열."
    )
    user = f"[모니터링 대상]\n{roster}\n\n[수집 목록]\n{items_for_prompt(items)}"
    out = ask_claude(system, user, SHAPE)

    reports = []
    for r in out["reports"]:
        src = pick(items, r["idx"])
        if src:
            reports.append({**r, "title": src["title"], "link": src["link"], "date": src["date"], "source": src["source"]})
    seen.update(it["link"] for it in items[:150])
    return reports
