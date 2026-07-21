# geo-ai-module

소상공인 매출 증대 프로젝트 — **RAG+LoRA 콘텐츠 생성 모듈** (우리 가게 전용 AI 콘텐츠 생성기).
점포 매칭 전까지 가짜(합성) 점포 데이터로 **파이프라인이 끝까지 도는 베이스라인**을 만드는 것이 1차 목표.

## 베이스라인 일정

| Day | 작업 | 상태 |
|---|---|---|
| Day 1 | GPU 환경 확인, 베이스 모델 후보 정리, 리뷰 필드 처리 확정, `task_templates.json` 확정 | ✅ |
| Day 2 | 가상 점포 생성기 + 교사 모델 API 연동, 태스크당 10개 테스트 생성 | |
| Day 3 | 합성 데이터 500개 생성 (블로그 280 + 쇼츠 220), 중복 제거·품질 검수 | |
| Day 4 | QLoRA 1차 학습 (3 epoch) → `geo-lora-adapter-v0` 저장 | |
| Day 5 | 더미 점포 추론 테스트, RAG 벡터DB 골격, Grounding Check 초안 | |

## Day 1 확정 사항

- **베이스 모델**: 미확정 — `Qwen2.5-7B-Instruct` vs `EEVE-Korean-Instruct-10.8B` **두 모델 모두 QLoRA 학습 후 비교 선택** ([configs/models.json](configs/models.json)의 comparison_plan 참조)
- **리뷰 필드 처리**: 리뷰 없는 점포는 필드 생략이 아니라 **명시적 `리뷰 요약: 없음` 표기** — 입력 포맷 고정으로 리뷰 환각 억제 (학습 데이터의 60% 이상은 리뷰 없음 케이스)
- **태스크 템플릿**: [configs/task_templates.json](configs/task_templates.json) — 블로그_신규작성(200) / 블로그_진단반영재작성(80) / 쇼츠(220)

## 구조

```
configs/
  task_templates.json   # 태스크별 instruction·입출력 포맷 (FR-03)
  models.json           # 베이스 모델 후보 + QLoRA 하이퍼파라미터 (r=16, alpha=32)
scripts/
  check_gpu.py          # GPU 환경 점검 + 4bit 로드 테스트
data/synthetic/         # 합성 학습 데이터 (git 미추적)
outputs/adapters/       # LoRA 어댑터 (git 미추적)
notebooks/              # Colab 실행용 노트북
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

## 참고 문서

- 기능명세서: `RAG_LoRA_기능명세서.md` (v0.2)
- 학습 환경: Google Colab Pro 또는 RunPod (비기능 요구사항 6장)
