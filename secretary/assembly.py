"""국회·의회 비서.
국회: 열린국회정보 API에서 '소관 상임위 통과' 이상 단계에 도달한 법안만 추린다.
의회: 경기도의회·화성시의회는 뉴스 검색으로 가볍게 본다."""
import os
from datetime import timedelta

import requests

from .common import COMMON_RULES, ask_claude, dedupe, items_for_prompt, naver_search, now, pick, within

API = "https://open.assembly.go.kr/portal/openapi/nzmimeepazxkubdpn"
PASSED = ("원안가결", "수정가결", "대안반영폐기", "수정안반영폐기")

SHAPE = {
    "bills": [{
        "idx": int,
        "priority": ("상", "중", "하"),
        "summary": str,
        "impact": str,
    }],
    "council": [{"idx": int, "summary": str}],
}


def fetch_bills(age, days):
    """22대 법안 전체를 훑어 최근 N일 내 상임위 또는 본회의를 통과한 것만 반환."""
    since = (now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out, page = [], 1
    while True:
        r = requests.get(API, params={
            "KEY": os.environ["ASSEMBLY_API_KEY"], "Type": "json",
            "pIndex": page, "pSize": 1000, "AGE": age,
        }, timeout=60)
        body = r.json().get("nzmimeepazxkubdpn")
        if not body:
            break
        rows = body[1]["row"]
        for b in rows:
            cmt = b.get("CMT_PROC_DT") or ""
            final = b.get("PROC_DT") or ""
            if final >= since and b.get("PROC_RESULT") in ("원안가결", "수정가결"):
                stage = "본회의 통과"
            elif cmt >= since and b.get("CMT_PROC_RESULT_CD") in PASSED:
                stage = "상임위 통과" if "폐기" not in b["CMT_PROC_RESULT_CD"] else "상임위 대안 반영"
            else:
                continue
            out.append({
                "title": b["BILL_NAME"], "committee": b.get("COMMITTEE") or "",
                "proposer": b.get("PROPOSER") or "", "stage": stage,
                "date": final if stage == "본회의 통과" else cmt,
                "link": b.get("DETAIL_LINK") or b["BILL_ID"],
            })
        if len(rows) < 1000:
            break
        page += 1
    # '대안반영폐기'는 같은 대안에 여러 건이 묶이므로 법률명 기준으로 하나만 남김
    uniq = {}
    for b in sorted(out, key=lambda x: x["stage"] != "본회의 통과"):
        uniq.setdefault((b["title"], b["stage"]), b)
    return list(uniq.values())


def run(cfg, seen):
    c = cfg["assembly"]
    bills = [b for b in fetch_bills(c["age"], c["days"]) if b["link"] + b["stage"] not in seen]

    council = []
    for q in c["council_queries"]:
        council += naver_search("news", q, display=30)
    council = dedupe([it for it in council if within(it, 48)], seen)

    if not bills and not council:
        return {"bills": [], "council": []}

    bill_lines = "\n".join(
        f"[{i}] ({b['stage']}/{b['committee']}) {b['title']} - {b['proposer']}" for i, b in enumerate(bills[:300])
    )
    system = COMMON_RULES + (
        "\n[국회·의회 비서] bills: 상임위·본회의를 통과한 법안 중 지자체 행정, 경기도·화성시, 주요 정쟁, "
        f"국민생활에 영향이 큰 것만 최대 {c['max_bills']}건 고른다. 단순 자구수정·기술적 개정은 제외. "
        "summary는 무엇이 바뀌는지 1문장(법안명만 보고 추정한 경우 '추정' 표기), impact는 화성시·지자체 영향 1문장. "
        "council: 경기도의회·화성시의회 뉴스 중 화성시정에 영향 있는 것만 최대 3건. 없으면 빈 배열."
    )
    user = f"[통과 법안]\n{bill_lines or '(없음)'}\n\n[의회 뉴스]\n{items_for_prompt(council, 60) or '(없음)'}"
    out = ask_claude(system, user, SHAPE)

    res = {"bills": [], "council": []}
    for r in out["bills"]:
        b = pick(bills, r["idx"])
        if b:
            res["bills"].append({**b, **r})
    for r in out["council"]:
        n = pick(council, r["idx"])
        if n:
            res["council"].append({**r, "title": n["title"], "link": n["link"], "date": n["date"]})
    seen.update(b["link"] + b["stage"] for b in bills)
    seen.update(it["link"] for it in council)
    return res
