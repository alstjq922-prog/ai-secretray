"""공통 도구: 설정, 네이버 검색, Claude 호출."""
import html
import json
import os
import re
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
    """kind: news | blog | cafearticle"""
    r = requests.get(
        f"https://openapi.naver.com/v1/search/{kind}.json",
        params={"query": query, "display": display, "sort": sort},
        headers={
            "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
            "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
        },
        timeout=15,
    )
    r.raise_for_status()
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


def ask_claude(system, user, shape, max_tokens=16000):
    """구조화된 JSON 응답을 받아 dict로 반환."""
    global _client
    cfg = load_config()["claude"]
    _client = _client or anthropic.Anthropic()
    resp = _client.messages.create(
        model=cfg["model"],
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": cfg["effort"], "format": {"type": "json_schema", "schema": _schema(shape)}},
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude가 요청을 거절했습니다")
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
