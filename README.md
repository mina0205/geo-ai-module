# geo-ai-module

소상공인 매출 증대 프로젝트 — **RAG+LoRA 콘텐츠 생성 모듈** (우리 가게 전용 AI 콘텐츠 생성기).
점포 매칭 전까지 가짜(합성) 점포 데이터로 **파이프라인이 끝까지 도는 베이스라인**을 만드는 것이 1차 목표.

## 베이스라인 일정

| Day | 작업 | 상태 |
|---|---|---|
| Day 1 | GPU 환경 확인, 베이스 모델 후보 정리, 리뷰 필드 처리 확정, `task_templates.json` 확정 | ✅ |
| Day 2 | 가상 점포 생성기 + 교사 모델 API 연동, 태스크당 10개 테스트 생성 | ✅ |
| Day 3 | 합성 데이터 500개 생성 (블로그 280 + 쇼츠 220), 중복 제거·품질 검수 | ✅ |
| Day 4 | QLoRA 1차 학습 (3 epoch) → `geo-lora-adapter-v0` 저장 | ✅ (qwen·eeve 각각, Drive 백업 완료) |
| Day 5 | 더미 점포 추론 테스트, RAG 벡터DB 골격, Grounding Check 초안 | ✅ |

## Day 1 확정 사항

- **GPU 환경**: Colab L4(22GB, bf16 지원)에서 검증 완료 (2026-07-21) — 4bit 로드+생성 테스트 통과: Qwen2.5-7B 5.6GB / EEVE-10.8B 6.3GB VRAM. 두 모델 모두 QLoRA 학습 가능
- **베이스 모델**: 미확정 — `Qwen2.5-7B-Instruct` vs `EEVE-Korean-Instruct-10.8B` **두 모델 모두 QLoRA 학습 후 비교 선택** ([configs/models.json](configs/models.json)의 comparison_plan 참조)
- **리뷰 필드 처리**: 리뷰 없는 점포는 필드 생략이 아니라 **명시적 `리뷰 요약: 없음` 표기** — 입력 포맷 고정으로 리뷰 환각 억제 (학습 데이터의 60% 이상은 리뷰 없음 케이스)
- **태스크 템플릿**: [configs/task_templates.json](configs/task_templates.json) — 블로그_신규작성(200) / 블로그_진단반영재작성(80) / 쇼츠(220)

## 구조

```
configs/
  task_templates.json    # 태스크별 instruction·입출력 포맷 (FR-03)
  models.json            # 베이스 모델 후보 + QLoRA 하이퍼파라미터 (r=16, alpha=32)
src/geo_ai/
  knowledge_base.py      # RAG 지식베이스 — Chroma 색인·검색 (FR-01, FR-02)
  grounding.py           # Grounding Check — 사실 대조 검증 (FR-07)
scripts/
  check_gpu.py           # GPU 환경 점검 + 4bit 로드 테스트
  generate_stores.py     # 가상 점포 생성기
  generate_dataset.py    # 교사 모델 학습 데이터 생성 (재실행 안전)
  train_qlora.py         # QLoRA 학습 (qwen/eeve 공용)
  evaluate_adapters.py   # 홀드아웃 추론 (모델 비교 1단계)
  compare_outputs.py     # 자동 지표 + 블라인드 평가지 (모델 비교 2단계)
  day5_demo.py           # RAG·Grounding 골격 검증 데모 (GPU 불필요)
server/app.py            # 백엔드 연동용 스텁 서버
data/synthetic/          # 합성 학습 데이터 (dataset/holdout/stores만 커밋)
outputs/adapters/        # LoRA 어댑터 (git 미추적, Drive 백업)
```

## GPU 환경 점검 (Colab/RunPod)

```bash
git clone https://github.com/mina0205/geo-ai-module.git
cd geo-ai-module
pip install -r requirements.txt

python scripts/check_gpu.py              # CUDA·패키지 점검
python scripts/check_gpu.py --load qwen  # Qwen2.5-7B 4bit 로드+생성 테스트
python scripts/check_gpu.py --load eeve  # EEVE-10.8B 4bit 로드+생성 테스트
```

Colab에서는 `런타임 > 런타임 유형 변경`에서 GPU(L4/A100 권장)를 선택한 뒤 실행.

## 학습 데이터 (Day 2~3 산출물)

- [data/synthetic/dataset.jsonl](data/synthetic/dataset.jsonl) — 학습용 490개 (블로그 신규 196 / 재작성 78 / 쇼츠 216)
- [data/synthetic/holdout.jsonl](data/synthetic/holdout.jsonl) — 두 후보 모델 비교평가용 10개 (학습에서 제외)
- 교사 모델: gpt-4o / 리뷰 없음 점포 비율 60% / 자동 검수(없는 가격·평판 표현·교통 정보·쇼츠 스키마) 이슈 0건까지 삭제·재생성 반복
- 재현: `generate_stores.py --count 300 --seed 7` → `generate_dataset.py --per-task 200|80|220`

## 스텁 서버 (백엔드 연동 개발용)

AI 모델 완성 전에 백엔드 개발을 시작할 수 있도록, [docs/api_spec.md](docs/api_spec.md)와 동일한
요청/응답 형식으로 샘플 콘텐츠를 반환하는 가짜 서버를 제공한다.

```bash
pip install fastapi uvicorn
uvicorn server.app:app --port 8000 --reload
```

- `GET /api/v1/health` · `POST /api/v1/generate` · `POST /api/v1/knowledge-base/update`
- 오류 케이스 테스트: owner로 generate 호출 → 403, 잘못된 task → 400 (공통 오류 포맷)
- `query`에 `flagged` 단어를 넣으면 `grounding_status: flagged` 응답 시뮬레이션 (검수 큐 흐름 개발용)
- Day 5 이후 같은 인터페이스의 실제 모델 서빙 서버로 교체 예정 (백엔드 코드 변경 없음)

## 참고 문서

- 기능명세서: `RAG_LoRA_기능명세서.md` (v0.2)
- 학습 환경: Google Colab Pro 또는 RunPod (비기능 요구사항 6장)
