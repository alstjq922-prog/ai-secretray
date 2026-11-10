"""공통 도구: 설정, 네이버 검색, Claude 호출."""
import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import anthropic
import requests
import yaml

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent


def now():
    return datetime.now(KST)


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean(text):
    """네이버 결과의 <b> 태그와 HTML 엔티티 제거."""
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


# ---------- 네이버 검색 API ----------

def naver_search(kind, query, display=50, sort="date"):
    """kind: news | blog | cafearticle. 일시 오류(429·5xx·시간 초과)는 한 번 더 시도한다."""
    for attempt in range(2):
        try:
            r = requests.get(
                f"https://naverapihub.apigw.ntruss.com/search/v1/{kind}",
                params={"query": query, "display": display, "sort": sort, "format": "json"},
                headers={
                    "X-NCP-APIGW-API-KEY-ID": os.environ["NAVER_CLIENT_ID"].strip(),
                    "X-NCP-APIGW-API-KEY": os.environ["NAVER_CLIENT_SECRET"].strip(),
                },
                timeout=15,
            )
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} 일시 오류", response=r)
            r.raise_for_status()
            break
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            retry = attempt == 0 and (e.response is None or e.response.status_code == 429 or e.response.status_code >= 500)
            if not retry:
                raise
            time.sleep(2)
    items = []
    for it in r.json().get("items", []):
        d = None
        if it.get("pubDate"):
            d = parsedate_to_datetime(it["pubDate"]).astimezone(KST)
        elif it.get("postdate"):
            d = datetime.strptime(it["postdate"], "%Y%m%d").replace(tzinfo=KST)
        items.append({
            "title": clean(it.get("title")),
            "desc": clean(it.get("description")),
            "link": it.get("originallink") or it.get("link"),
            "date": d.isoformat() if d else None,
            "source": it.get("bloggername") or it.get("cafename") or "",
            "blog": it.get("bloggerlink", ""),
        })
    return items


def search_many(kind, queries, display=50):
    """여러 검색어를 차례로 검색. 일부가 실패해도 나머지 결과로 계속하고, 전부 실패할 때만 오류를 낸다.
    queries: 검색어 문자열 또는 (검색어, 붙일 정보 dict) 목록"""
    items, failed, last_err = [], 0, None
    for q in queries:
        q, extra = (q, {}) if isinstance(q, str) else q
        try:
            items += [{**it, **extra} for it in naver_search(kind, q, display=display)]
        except Exception as e:
            failed, last_err = failed + 1, e
            print(f"  ! 검색 실패({type(e).__name__}): {q}")
    if queries and failed == len(queries):
        raise RuntimeError(f"네이버 검색 {failed}건 모두 실패: {last_err}")
    if failed:
        print(f"  검색 {len(queries)}건 중 {failed}건 실패 → 나머지로 진행")
    return items


def within(item, hours):
    if not item.get("date"):
        return True
    return datetime.fromisoformat(item["date"]) >= now() - timedelta(hours=hours)


def dedupe(items, seen=None):
    """링크·제목 기준 중복 제거. seen 집합에 있는 링크(이미 분석함)도 제외."""
    out, keys = [], set()
    for it in items:
        k1, k2 = it["link"], re.sub(r"\W", "", it["title"])[:30]
        if k1 in keys or k2 in keys or (seen is not None and k1 in seen):
            continue
        keys.update([k1, k2])
        out.append(it)
    return out


class Seen:
    """이미 분석한 링크 기록. 링크마다 처음 본 시각을 남겨, 정리할 때 오래된 것부터 지운다."""

    def __init__(self, raw):
        if isinstance(raw, list):  # 예전 형식(시각 없는 목록)은 지금 시각으로 옮겨 담음
            raw = dict.fromkeys(raw, now().isoformat())
        self.d = dict(raw or {})

    def __contains__(self, k):
        return k in self.d

    def update(self, keys):
        t = now().isoformat()
        for k in keys:
            self.d.setdefault(k, t)

    def dump(self, days=14, limit=20000):
        cutoff = (now() - timedelta(days=days)).isoformat()
        kept = sorted(((t, k) for k, t in self.d.items() if t >= cutoff), reverse=True)[:limit]
        return {k: t for t, k in kept}


def drop_keywords(items, words):
    return [it for it in items if not any(w in it["title"] for w in words)]


# ---------- Claude ----------

_client = None


def _schema(node):
    """간단 스키마 표기 → JSON Schema. dict=object(모든 키 필수), [x]=array, str=string, 그 외 enum 리스트."""
    if isinstance(node, dict):
        return {
            "type": "object",
            "properties": {k: _schema(v) for k, v in node.items()},
            "required": list(node),
            "additionalProperties": False,
        }
    if isinstance(node, list) and len(node) == 1:
        return {"type": "array", "items": _schema(node[0])}
    if isinstance(node, tuple):
        return {"type": "string", "enum": list(node)}
    if node is int:
        return {"type": "integer"}
    return {"type": "string"}


def ask_claude(system, user, shape, max_tokens=16000, effort=None):
    """구조화된 JSON 응답을 받아 dict로 반환. effort를 주면 설정값 대신 사용."""
    global _client
    cfg = load_config()["claude"]
    _client = _client or anthropic.Anthropic()
    resp = _client.messages.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort or cfg["effort"], "format": {"type": "json_schema", "schema": _schema(shape)}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("Claude 응답이 길이 제한에 걸려 잘렸습니다")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text)


def items_for_prompt(items, limit=150):
    """토큰 절약용 압축 표기."""
    lines = []
    for i, it in enumerate(items[:limit]):
        lines.append(f"[{i}] {it['title']} | {it['desc'][:160]} | {it.get('source', '')} | {(it.get('date') or '')[:16]}")
    return "\n".join(lines)


def pick(items, idx):
    return items[idx] if isinstance(idx, int) and 0 <= idx < len(items) else {}


COMMON_RULES = (
    "당신은 경기도 화성시 공무원(정무·비서 업무)을 보좌하는 비서다. "
    "짧고 명확하게, 꼭 필요한 말만 쓴다. 문장은 '~함', '~임' 같은 개조식 보고체로 쓴다. "
    "입력에 없는 사실은 지어내지 않는다."
)


# ---------- 보도량(관련 기사 수) 계산 ----------
# 사용자가 수시로 보지 않으므로, 볼 때 '가장 크게 다뤄진 사안'이 위에 오도록 사안별 관련 보도 수(heat)를 센다.

COVERAGE_RULES = (
    " related에는 같은 사안을 다룬 다른 기사 번호를 모두 적는다(없으면 빈 배열). "
    "[이미 보고한 사안] 목록과 같은 사안의 새 기사는 reports에 다시 넣지 말고 followups에 "
    "prev(이미 보고한 사안 번호)와 items(새 기사 번호)로 적는다."
)

FOLLOWUP_SHAPE = [{"prev": int, "items": [int]}]


def prev_for_prompt(prev, limit=40):
    lines = [f"[P{i}] {p.get('summary') or p.get('title')}" for i, p in enumerate(prev[:limit])]
    return "\n".join(lines) or "(없음)"


def apply_coverage(out, items, prev, limit=40):
    """Claude 결과의 related·followups로 보도량을 반영. 새 보고 목록을 반환하고 prev는 제자리에서 갱신."""
    reports = []
    for r in out["reports"]:
        src = pick(items, r["idx"])
        if not src:
            continue
        related = {i for i in r.pop("related", []) if pick(items, i) and i != r["idx"]}
        reports.append({**r, "src": src, "heat": 1 + len(related)})
    for f in out.get("followups", []):
        if isinstance(f.get("prev"), int) and 0 <= f["prev"] < min(len(prev), limit):
            n = len({i for i in f.get("items", []) if pick(items, i)})
            if n:
                p = prev[f["prev"]]
                p["heat"] = p.get("heat", 1) + n
                p["last_covered"] = now().isoformat()
    return reports
