"""AI 콘텐츠 생성 모듈 — 스텁(Stub) 서버.

docs/api_spec.md 의 AI 모듈 API를 요청/응답 형식 그대로 구현하되,
모델 없이 준비된 샘플 콘텐츠를 즉시 반환한다. 백엔드 연동 개발용이며
Day 5 이후 실제 모델 서빙 서버로 교체된다 (백엔드 코드 변경 없음).

실행:
    pip install fastapi uvicorn
    uvicorn server.app:app --port 8000 --reload

테스트 팁: query에 "flagged"라는 단어를 넣으면 grounding_status=flagged
응답이 내려간다 (검수 큐 흐름 개발용).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

app = FastAPI(title="geo-ai-module (stub)", version="0.1.0")

VALID_TASKS = {"blog_new", "blog_revise", "shorts"}
VALID_DOC_TYPES = {"menu", "review", "hours", "feature"}


def err(status: int, code: str, message: str) -> JSONResponse:
    """docs/api_spec.md 1.3 공통 오류 포맷."""
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


# --- 샘플 콘텐츠 (실제 파이프라인 산출물과 동일한 형태) ---

SAMPLE_BLOG = (
    "**연신내 치킨 맛집, '치킨하우스 동네'를 소개합니다**\n\n"
    "서울 은평구 연신내에 자리한 치킨하우스 동네는 국내산 냉장육만 사용하는 동네 치킨·호프집입니다.\n\n"
    "**대표 메뉴는 무엇인가요?**\n\n"
    "후라이드 치킨(19,000원)과 마늘간장치킨(21,000원)이 대표 메뉴입니다. 무뼈 옵션도 선택할 수 있습니다.\n\n"
    "**언제 방문하면 좋나요?**\n\n"
    "매일 오후 4시부터 새벽 1시까지 영업하며, 화요일은 휴무입니다. "
    "2층 단체석이 있어 모임 장소로도 좋습니다."
)

SAMPLE_SHORTS = {
    "script": "(도입) 연신내에서 치킨 어디로 갈지 고민된다면? (본문) 치킨하우스 동네는 국내산 냉장육만 씁니다. "
              "대표 메뉴는 후라이드 19,000원, 마늘간장 21,000원. 2층 단체석에 대형 TV로 경기 보면서 먹기 좋아요. "
              "(CTA) 매일 오후 4시 오픈, 화요일 휴무! 오늘 저녁은 여기 어때요?",
    "caption": "연신내 치킨은 여기 🍗 국내산 냉장육 치킨하우스 동네",
    "hashtags": ["#연신내치킨", "#연신내맛집", "#치킨하우스동네", "#은평구맛집"],
}


# --- 요청 스키마 ---

class GenerateRequest(BaseModel):
    store_id: str
    requested_by_role: str
    task: str
    query: str
    existing_content: Optional[str] = None
    diagnosis_issues: Optional[List[str]] = None
    owner_feedback: Optional[List[str]] = None


class KBDocument(BaseModel):
    type: str
    text: str


class KBUpdateRequest(BaseModel):
    store_id: str
    documents: List[KBDocument]


# --- 엔드포인트 ---

@app.get("/api/v1/health")
def health():
    return {"status": "ok", "model_loaded": True}


@app.post("/api/v1/generate")
def generate(req: GenerateRequest):
    if req.requested_by_role != "admin":
        return err(403, "FORBIDDEN_ROLE", "콘텐츠 생성은 admin만 호출할 수 있습니다.")
    if req.task not in VALID_TASKS:
        return err(400, "INVALID_TASK", f"task는 {sorted(VALID_TASKS)} 중 하나여야 합니다.")
    if req.task == "blog_revise" and (not req.existing_content or not req.diagnosis_issues):
        return err(400, "MISSING_FIELD", "blog_revise에는 existing_content와 diagnosis_issues가 필요합니다.")

    # 테스트 편의: query에 'flagged'가 있으면 검수 필요 응답을 시뮬레이션
    flagged = "flagged" in req.query.lower()
    grounding = {
        "grounding_status": "flagged" if flagged else "pass",
        "flagged_facts": (["영업시간 '24시간'이 등록 정보(16:00~01:00)와 불일치"] if flagged else []),
    }

    if req.task == "shorts":
        return {"task": "shorts", "content": SAMPLE_SHORTS, **grounding}
    return {"task": req.task, "content": SAMPLE_BLOG, **grounding}


@app.post("/api/v1/knowledge-base/update")
def kb_update(req: KBUpdateRequest):
    for doc in req.documents:
        if doc.type not in VALID_DOC_TYPES:
            return err(400, "INVALID_TASK", f"document type은 {sorted(VALID_DOC_TYPES)} 중 하나여야 합니다.")
    if not req.documents:
        return err(400, "MISSING_FIELD", "documents가 비어 있습니다.")
    return {"status": "success", "chunks_indexed": len(req.documents)}
