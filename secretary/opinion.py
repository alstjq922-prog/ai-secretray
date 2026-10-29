"""여론·민원 비서.
- 정치 여론: 성향별 커뮤니티 인기글 제목을 모아 진영별 핵심 쟁점을 요약
- 지역 여론: 네이버 카페(맘카페 등) 검색으로 화성 지역 민원·불만을 조기 포착"""
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .common import COMMON_RULES, ask_claude, dedupe, naver_search

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

SHAPE = {
    "camps": [{
        "camp": str,
        "mood": str,
        "issues": [{"issue": str, "detail": str, "examples": [int]}],
    }],
    "local": [{
        "issue": str,
        "priority": ("상", "중", "하"),
        "detail": str,
        "action": str,
        "examples": [int],
    }],
}


def fetch_board(board):
    """게시판 목록 페이지에서 글 제목·링크를 뽑는다. 사이트가 차단하면 빈 목록."""
    try:
        r = requests.get(board["url"], headers=UA, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! {board['name']} 수집 실패: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    pat = re.compile(board["link_pattern"])
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if len(title) < 6 or not pat.search(a["href"]):
            continue
        link = urljoin(board["url"], a["href"])
        if link in seen:
            continue
        seen.add(link)
        out.append({"title": title, "link": link, "source": board["name"]})
    print(f"  {board['name']}: {len(out)}건")
    return out[:board.get("limit", 40)]


def run(cfg):
    c = cfg["opinion"]
    posts = []  # (진영, 글)
    for camp, boards in c["communities"].items():
        for b in boards:
            posts += [(camp, p) for p in fetch_board(b)]

    local = []
    for q in c["local_queries"]:
        for it in naver_search("cafearticle", q, display=50):
            it["source"] = it["source"] or "네이버카페"
            local.append(it)
    local = dedupe(local)[:120]

    if not posts and not local:
        return {"camps": [], "local": []}

    camp_lines = "\n".join(f"[{i}] ({camp}/{p['source']}) {p['title']}" for i, (camp, p) in enumerate(posts))
    local_lines = "\n".join(f"[{i}] ({it['source']}) {it['title']} | {it['desc'][:120]}" for i, it in enumerate(local))
    system = COMMON_RULES + (
        "\n[여론·민원 비서] "
        "camps: 진영(입력에 표시된 진영명 그대로)별로 지금 가장 많이 회자되는 정치 쟁점 3~5개와 전반적 분위기(mood 1문장)를 정리. "
        "examples에는 근거가 된 글 번호를 최대 3개. 욕설·혐오 표현은 옮기지 말고 순화해 요약. "
        "local: 화성시 관련 카페글에서 민원·불만·안전·갈등 등 시가 대응해야 할 사안만 골라 최대 7건. "
        "단순 맛집·육아 질문·중고거래는 제외. action은 권고 대응 1문장. 해당 없으면 빈 배열."
    )
    user = f"[커뮤니티 인기글]\n{camp_lines or '(없음)'}\n\n[화성 지역 카페글]\n{local_lines or '(없음)'}"
    out = ask_claude(system, user, SHAPE)

    def links(idxs, pool, get):
        return [get(pool[i]) for i in idxs if 0 <= i < len(pool)]

    for camp in out["camps"]:
        for iss in camp["issues"]:
            iss["examples"] = links(iss["examples"], posts, lambda x: {"title": x[1]["title"], "link": x[1]["link"], "source": x[1]["source"]})
    for l in out["local"]:
        l["examples"] = links(l["examples"], local, lambda x: {"title": x["title"], "link": x["link"], "source": x["source"]})
    return out
