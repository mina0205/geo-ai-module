"""Grounding Check 초안 (FR-07) — 생성 콘텐츠를 원본 가게 데이터와 대조.

규칙 기반 1차 검사: 통과하면 "pass", 하나라도 걸리면 "flagged"와
사람이 읽을 수 있는 불일치 목록을 반환한다. flagged 콘텐츠의 게시 차단은
백엔드 책임 (docs/api_spec.md 1.5).

Day 3 데이터 정제에서 검증된 것과 같은 계열의 검사를 서비스용으로 재사용한다.
"""

from __future__ import annotations

import json
import re

REP_WORDS = ["후기", "리뷰", "입소문", "평이 많", "평판", "재주문율", "재구매율",
             "사랑받", "소문난", "인기 있는", "인기가 많"]
TRANSPORT_WORDS = ["지하철", "버스", "역에서", "도보", "주차"]
TIME_PATTERN = re.compile(r"\d{1,2}:\d{2}")
PRICE_PATTERN = re.compile(r"[\d,]+원")


def _flatten(content) -> str:
    """블로그(str) / 쇼츠(dict 또는 JSON 문자열) → 검사용 텍스트."""
    if isinstance(content, dict):
        return " ".join([content.get("script", ""), content.get("caption", ""),
                         " ".join(content.get("hashtags", []))])
    text = str(content).strip()
    if text.startswith("{"):
        try:
            return _flatten(json.loads(text))
        except json.JSONDecodeError:
            pass
    return text


def check_content(content, source_docs: list[dict]) -> tuple[str, list[str]]:
    """생성 콘텐츠를 가게 원본 문서 전체와 대조.

    Args:
        content: 블로그 텍스트 또는 쇼츠 dict/JSON 문자열
        source_docs: [{"type": ..., "text": ...}] — KnowledgeBase.get_all() 결과
    Returns:
        ("pass" | "flagged", flagged_facts 리스트)
    """
    text = _flatten(content)
    source = "\n".join(d["text"] for d in source_docs)
    flagged: list[str] = []

    # 부분 문자열 오탐 방지: '5,000원' ⊂ '45,000원', '2:00' ⊂ '22:00'
    # → 원본에서도 같은 패턴으로 추출한 토큰 집합과 정확히 비교
    source_prices = set(PRICE_PATTERN.findall(source))
    source_times = set(TIME_PATTERN.findall(source))

    # 1) 가격: 생성문의 'N원'이 원본에 없으면 불일치
    for price in dict.fromkeys(PRICE_PATTERN.findall(text)):
        if price not in source_prices:
            flagged.append(f"가격 '{price}'이(가) 등록된 가게 정보에 없음")

    # 2) 시각: 생성문의 'HH:MM'이 원본에 없으면 불일치
    for t in dict.fromkeys(TIME_PATTERN.findall(text)):
        if t not in source_times:
            flagged.append(f"시간 '{t}'이(가) 등록된 영업시간 정보에 없음")

    # 3) 리뷰가 없는 가게인데 후기·평판·인기 표현 사용
    has_review = any(d["type"] == "review" for d in source_docs)
    if not has_review:
        hits = [w for w in REP_WORDS if w in text]
        if hits:
            flagged.append(f"리뷰 정보가 없는데 평판 표현 사용: {', '.join(hits)}")

    # 4) 원본에 없는 교통·주차 정보
    for w in TRANSPORT_WORDS:
        if w in text and w not in source:
            flagged.append(f"등록 정보에 없는 '{w}' 관련 내용 언급")

    return ("flagged" if flagged else "pass", flagged)
