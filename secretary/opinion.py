"""여론·민원 비서 — 하루 3번(기본 06·13·20시) 깊게 정리한다.
- 정치 여론: 성향별 커뮤니티 인기글 제목을 모아 진영별 핵심 쟁점·분위기·전망을 정리
- 지역 여론: 네이버 카페(맘카페 등) 검색으로 화성 지역 민원·불만을 조기 포착
- 지난 정리와 비교해 새로 떠오르거나 커진 쟁점을 따로 알려 줌"""
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .common import COMMON_RULES, ask_claude, dedupe, search_many

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}

SHAPE = {
    "brief": str,
    "changes": [str],
    "camps": [{
        "camp": str,
        "mood": str,
        "issues": [{"issue": str, "detail": str, "outlook": str, "examples": [int]}],
    }],
    "local": [{
        "issue": str,
        "priority": ("상", "중", "하"),
        "area": str,
        "detail": str,
        "action": str,
        "examples": [int],
    }],
}


def fetch_board(board, limit):
    """게시판 목록 페이지에서 글 제목·링크를 뽑는다. 사이트가 차단하면 빈 목록."""
    try:
        r = requests.get(board["url"], headers=UA, timeout=15)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"  ! {board['name']} 수집 실패: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    pat = re.compile(board["link_pattern"])
    out, links = [], set()
    for a in soup.find_all("a", href=True):
        title = a.get_text(" ", strip=True)
        if len(title) < 6 or not pat.search(a["href"]):
            continue
        link = urljoin(board["url"], a["href"])
        if link in links:
            continue
        links.add(link)
        out.append({"title": title, "link": link, "source": board["name"]})
    print(f"  {board['name']}: {len(out)}건")
    return out[:board.get("limit", limit)]


def _previous(prev):
    """지난 정리의 쟁점 목록(비교용)."""
    lines = []
    for camp in prev.get("camps", []):
        lines += [f"- ({camp['camp']}) {i['issue']}" for i in camp.get("issues", [])]
    lines += [f"- (화성 민원) {l['issue']}" for l in prev.get("local", [])]
    return "\n".join(lines) or "(첫 정리)"


def run(cfg, prev):
    c = cfg["opinion"]
    posts = []  # (진영, 글)
    for camp, boards in c["communities"].items():
        for b in boards:
            posts += [(camp, p) for p in fetch_board(b, c.get("posts_per_board", 60))]

    local = search_many("cafearticle", c["local_queries"], display=c.get("cafe_display", 50))
    for it in local:
        it["source"] = it["source"] or "네이버카페"
    local = dedupe(local)[:c.get("max_local_posts", 200)]

    if not posts and not local:
        return {"brief": "", "changes": [], "camps": [], "local": []}

    camp_lines = "\n".join(f"[{i}] ({camp}/{p['source']}) {p['title']}" for i, (camp, p) in enumerate(posts))
    local_lines = "\n".join(f"[{i}] ({it['source']}) {it['title']} | {it['desc'][:160]}" for i, it in enumerate(local))
    system = COMMON_RULES + (
        "\n[여론·민원 비서] 하루 3번 하는 정리이므로 빠짐없이 깊게 분석한다. "
        "brief: 지금 여론 전체를 4~6문장으로 종합(진영 간 온도차, 화성시에 미칠 영향 포함). "
        "changes: [지난 정리]와 비교해 새로 떠오르거나 커지거나 잦아든 쟁점을 최대 5개, 각 1문장. 첫 정리면 빈 배열. "
        "camps: 진영(입력에 표시된 진영명 그대로)별로 많이 회자되는 정치 쟁점 5~8개. "
        "detail은 무엇이 왜 회자되는지 2~3문장, outlook은 앞으로의 전개·우리 쪽 대응 포인트 1문장, "
        "mood는 진영 전반 분위기 2문장. examples에는 근거가 된 글 번호를 최대 4개. "
        "욕설·혐오 표현은 옮기지 말고 순화해 요약. "
        "local: 화성시 관련 카페글에서 민원·불만·안전·갈등 등 시가 대응해야 할 사안을 최대 15건. "
        "area는 지역(동탄·봉담·향남·남양 등, 모르면 '화성 전역'), detail은 상황 2~3문장(글이 몇 건인지 포함), "
        "action은 권고 대응 1~2문장. 단순 맛집·육아 질문·중고거래는 제외. 해당 없으면 빈 배열."
    )
    user = (f"[지난 정리]\n{_previous(prev)}\n\n[커뮤니티 인기글]\n{camp_lines or '(없음)'}"
            f"\n\n[화성 지역 카페글]\n{local_lines or '(없음)'}")
    out = ask_claude(system, user, SHAPE, max_tokens=32000, effort=c.get("effort"))

    def links(idxs, pool, get):
        return [get(pool[i]) for i in idxs if isinstance(i, int) and 0 <= i < len(pool)]

    for camp in out["camps"]:
        for iss in camp["issues"]:
            iss["examples"] = links(iss["examples"], posts, lambda x: {"title": x[1]["title"], "link": x[1]["link"], "source": x[1]["source"]})
    for l in out["local"]:
        l["examples"] = links(l["examples"], local, lambda x: {"title": x["title"], "link": x["link"], "source": x["source"]})
    out["counts"] = {"posts": len(posts), "local": len(local)}
    return out
