# API 명세서 & 공통 규칙 (v0.1)

AI 콘텐츠 생성 모듈(RAG+LoRA)과 백엔드 간 연동 명세.
기능명세서 v0.2의 5장(API 인터페이스)·7장(권한/데이터 모델)을 기반으로 정리했으며, 백/프론트 개발 시작 시 이 문서를 기준으로 한다.

> **연동 구조**: 프론트 → 백엔드(인증·권한·DB) → AI 모듈(생성·검증).
> 프론트와 사장님 계정은 AI 모듈을 직접 호출하지 않는다. AI 모듈은 백엔드만 호출하는 내부 서비스다.

---

## 1. 공통 규칙

### 1.1 기본

| 항목 | 규칙 |
|---|---|
| 프로토콜 | HTTP/JSON, `Content-Type: application/json; charset=utf-8` |
| 버저닝 | URL prefix `/api/v1` (breaking change 시 v2) |
| 필드 네이밍 | `snake_case` (예: `store_id`, `grounding_status`) |
| 날짜/시간 | ISO 8601, KST 오프셋 포함 (예: `2026-07-21T14:30:00+09:00`) |
| ID | 문자열로 주고받음 (내부 구현이 숫자여도 API 상에서는 string) |
| 인코딩 | 요청·응답 모두 UTF-8, 한국어 원문 그대로 (이스케이프 불필요) |

### 1.2 공통 Enum (철자 고정 — 프론트·백·AI 공통 사용)

| Enum | 값 | 비고 |
|---|---|---|
| `task` | `blog_new` \| `blog_revise` \| `shorts` | 학습 데이터의 한글 태그(블로그_신규작성 등)와 1:1 매핑, API에서는 영문만 사용 |
| `grounding_status` | `pass` \| `flagged` | `flagged`면 자동 게시 금지, 사람 검수 큐로 (비기능 요구사항 '안전장치') |
| `role` | `admin` \| `owner` | 인증·권한 판정은 백엔드 책임 |
| `document type` | `menu` \| `review` \| `hours` \| `feature` | 지식베이스 문서 유형 |

### 1.3 오류 응답 (공통 포맷)

모든 4xx/5xx는 아래 형태로 통일한다.

```json
{
  "error": {
    "code": "STORE_NOT_FOUND",
    "message": "해당 store_id의 점포 정보가 없습니다."
  }
}
```

| HTTP | code 예시 | 상황 |
|---|---|---|
| 400 | `INVALID_TASK`, `MISSING_FIELD` | enum 외의 task 값, 필수 필드 누락 (예: `blog_revise`인데 `existing_content` 없음) |
| 403 | `FORBIDDEN_ROLE` | owner가 생성 API 호출 시도 등 권한 위반 |
| 404 | `STORE_NOT_FOUND`, `CONTENT_NOT_FOUND` | 없는 리소스 |
| 422 | `GENERATION_FAILED` | 모델이 유효한 출력 생성 실패 (쇼츠 JSON 파싱 불가 등, 재시도 후에도 실패 시) |
| 500 | `INTERNAL_ERROR` | 그 외 서버 오류 |

### 1.4 권한 요약 (기능명세서 7장)

| API | admin | owner |
|---|---|---|
| 콘텐츠 생성 `/generate` | ✅ | ❌ (403) |
| 콘텐츠 조회 `/contents` | ✅ | ✅ (조회 전용, 재생성 파라미터 등 수정 관련 필드 미노출 — FR-13) |
| 피드백 등록 `/contents/{id}/feedback` | 조회만 | ✅ 작성 |
| 지식베이스 갱신 `/knowledge-base/update` | ✅ (백엔드 경유) | ❌ |

### 1.5 AI 모듈 관련 공통 사항

- **응답 시간**: 생성 1건 10초 이내 목표(GPU 기준). 백엔드는 타임아웃을 30초로 잡고, 초과 시 504 처리 권장
- **리뷰 처리**: 리뷰가 없는 점포도 정상 케이스. 지식베이스에 리뷰 문서가 없으면 AI 모듈이 알아서 가게 데이터만으로 생성 (FR-11) — 백엔드가 빈 리뷰를 막거나 채울 필요 없음
- **`flagged` 처리 흐름**: `grounding_status: flagged` 응답을 받으면 백엔드는 해당 콘텐츠를 게시 불가 상태로 저장하고 관리자 검수 큐에 표시한다. AI 모듈이 게시를 막아주지 않는다 (저장·게시 제어는 백엔드 책임)

---

## 2. AI 모듈 제공 API (백엔드 → AI 모듈)

### 2.1 콘텐츠 생성

```
POST /api/v1/generate
```

**Request**

```json
{
  "store_id": "store_001",
  "requested_by_role": "admin",
  "task": "blog_new",
  "query": "혼밥하기 좋은 카페 소개",
  "existing_content": "(blog_revise만) 기존 블로그 전문",
  "diagnosis_issues": ["(blog_revise만) 지역 키워드 부족", "영업시간 누락"],
  "owner_feedback": ["(선택) 사장님 피드백 텍스트"]
}
```

- `existing_content`, `diagnosis_issues`: `task=blog_revise`일 때 필수, 그 외 태스크에서는 보내지 않음
- `owner_feedback`: 있을 때만 포함 (없으면 필드 생략)

**Response 200 (블로그)**

```json
{
  "task": "blog_new",
  "content": "생성된 블로그 텍스트...",
  "grounding_status": "pass",
  "flagged_facts": []
}
```

**Response 200 (쇼츠)**

```json
{
  "task": "shorts",
  "content": {
    "script": "15~60초 대본 (도입-본문-CTA)",
    "caption": "캡션 텍스트",
    "hashtags": ["#수원카페", "#혼밥"]
  },
  "grounding_status": "flagged",
  "flagged_facts": ["영업시간 '24시간'이 등록 정보(09:00~21:00)와 불일치"]
}
```

- `flagged_facts`: `pass`면 빈 배열, `flagged`면 불일치 항목을 사람이 읽을 수 있는 문장으로 나열

### 2.2 지식베이스 갱신 (매칭 후 실데이터 교체용, FR-10)

```
POST /api/v1/knowledge-base/update
```

**Request**

```json
{
  "store_id": "store_001",
  "documents": [
    { "type": "menu", "text": "아메리카노 4,500원 / 카페라떼 5,000원" },
    { "type": "hours", "text": "매일 09:00~21:00, 월요일 휴무" },
    { "type": "feature", "text": "1인석 6개, 콘센트 좌석 다수, 주차 2대 가능" }
  ]
}
```

- 동일 `store_id`로 재호출 시 **전체 교체(replace)** 로 동작한다 (기존 문서 삭제 후 재색인). 부분 추가가 필요해지면 v2에서 논의
- `review` 타입 문서는 있는 경우에만 포함 (없어도 정상)

**Response 200**

```json
{ "status": "success", "chunks_indexed": 12 }
```

### 2.3 헬스체크

```
GET /api/v1/health
```

**Response 200**: `{ "status": "ok", "model_loaded": true }`
백엔드가 AI 서버 기동 여부 확인용으로 사용 (모델 로딩 중이면 `model_loaded: false`).

---

## 3. 백엔드 제공 API (프론트 → 백엔드)

> 아래는 백엔드 구현 영역이며, AI 모듈 응답 필드와 어긋나지 않도록 계약만 여기 고정한다.
> 인증 방식(JWT 등)·회원가입·온보딩 API의 세부는 백엔드가 정의하되, `role`·`store_id` 개념은 본 문서의 공통 규칙을 따른다.

### 3.1 콘텐츠 목록 조회 (owner/admin 공용)

```
GET /api/v1/contents/{store_id}
```

**Response 200**

```json
{
  "contents": [
    {
      "content_id": "c_001",
      "task": "blog_new",
      "content": "...",
      "created_at": "2026-07-21T14:30:00+09:00"
    }
  ]
}
```

- **owner 응답에는 위 4개 필드만 노출** (FR-13). `grounding_status`, 재생성 파라미터, 생성자 정보 등은 admin 응답에만 포함 가능
- `content`는 블로그면 string, 쇼츠면 2.1의 쇼츠 객체

### 3.2 사장님 피드백 등록

```
POST /api/v1/contents/{content_id}/feedback
```

**Request**: `{ "store_id": "store_001", "role": "owner", "feedback_text": "가격이 옛날 정보예요" }`
**Response 201**: `{ "status": "received", "feedback_id": "f_001" }`

- 백엔드는 `owner_feedbacks` 테이블에 저장하고, 관리자가 재생성 시 2.1의 `owner_feedback` 파라미터로 AI 모듈에 전달한다 (FR-12)

---

## 4. 변경 이력

| 버전 | 날짜 | 내용 |
|---|---|---|
| v0.1 | 2026-07-21 | 기능명세서 v0.2 기반 초안. 공통 규칙(오류 포맷·enum·권한)과 헬스체크 신설, 지식베이스 갱신을 전체 교체 방식으로 명시 |
