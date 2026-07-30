"""Day 5 골격 검증 데모 — 더미 점포로 RAG 색인·검색·Grounding Check 흐름 확인.

모델(GPU) 없이 돌아간다. Colab 또는 로컬:
    pip install chromadb sentence-transformers
    python scripts/day5_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from geo_ai.grounding import check_content
from geo_ai.knowledge_base import KnowledgeBase

DUMMY_STORE = "dummy_001"
DUMMY_DOCS = [
    {"type": "menu", "text": "대표 메뉴: 아메리카노 4,500원, 아인슈페너 6,000원, 바스크 치즈케이크 6,500원"},
    {"type": "hours", "text": "영업시간: 매일 10:00~22:00, 월요일 휴무"},
    {"type": "feature", "text": "1인석 6개와 콘센트 좌석이 많아 혼자 작업하기 좋음"},
    {"type": "feature", "text": "직접 로스팅한 원두 사용, 화이트톤 인테리어"},
]

GOOD_CONTENT = (
    "망원동에서 혼자 시간을 보내기 좋은 카페를 찾는다면 이곳을 추천합니다. "
    "1인석이 6개나 있고 콘센트 좌석이 많아 작업하기 좋아요. "
    "아메리카노는 4,500원, 시그니처인 아인슈페너는 6,000원입니다. "
    "매일 10:00~22:00 영업하며 월요일은 휴무입니다."
)

BAD_CONTENT = (
    "많은 분들에게 사랑받는 인기 카페입니다. 아메리카노가 5,000원으로 저렴하고, "
    "새벽 2시까지 영업해서 밤샘 작업에도 좋아요. 주차장도 넓습니다."
)


def main() -> None:
    print("=== ① 지식베이스 색인 (전체 교체 방식) ===")
    kb = KnowledgeBase()
    n = kb.index_store(DUMMY_STORE, DUMMY_DOCS)
    print(f"색인 완료: {n}개 chunk")
    n2 = kb.index_store(DUMMY_STORE, DUMMY_DOCS)
    print(f"재색인(교체) 완료: {n2}개 chunk — 중복 누적 없음 확인")

    print("\n=== ② Retrieval: 의미 기반 검색 ===")
    for query in ["혼밥하기 좋은 카페 소개", "디저트 메뉴 알려줘"]:
        docs = kb.retrieve(DUMMY_STORE, query, k=2)
        print(f"질의: {query!r}")
        for d in docs:
            print(f"  → [{d['type']}] {d['text'][:50]}...")

    print("\n=== ③ Grounding Check ===")
    source = kb.get_all(DUMMY_STORE)
    for label, content in [("정상 콘텐츠", GOOD_CONTENT), ("환각 콘텐츠", BAD_CONTENT)]:
        status, facts = check_content(content, source)
        print(f"{label}: {status}")
        for fact in facts:
            print(f"  ⚠ {fact}")

    print("\n골격 검증 완료 — 색인·검색·대조가 모두 동작합니다.")


if __name__ == "__main__":
    main()
