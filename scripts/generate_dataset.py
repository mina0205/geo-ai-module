"""교사 모델(OpenAI API)로 학습 데이터 생성 (Day 2~3).

가상 점포(stores.jsonl) + 태스크 템플릿(task_templates.json)을 조합해
교사 모델에게 모범 답안 콘텐츠를 생성시키고, QLoRA 학습용
{task, instruction, input, output} JSONL로 저장한다.

준비: .env 파일에 OPENAI_API_KEY 설정 (.env.example 참조)

사용:
    python scripts/generate_dataset.py --per-task 10          # Day2 시범 생성 (태스크당 10개)
    python scripts/generate_dataset.py --per-task 10 --tasks shorts
    → data/synthetic/dataset.jsonl (이어쓰기 방식, 중단 후 재실행 가능)
"""

import argparse
import json
import os
import random
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).parent.parent
TEMPLATES = json.loads((ROOT / "configs" / "task_templates.json").read_text(encoding="utf-8"))
STORES_DEFAULT = ROOT / "data" / "synthetic" / "stores.jsonl"
OUT_DEFAULT = ROOT / "data" / "synthetic" / "dataset.jsonl"

load_dotenv(ROOT / ".env")
client = OpenAI()  # OPENAI_API_KEY는 .env에서 로드됨
TEACHER_MODEL = os.getenv("TEACHER_MODEL", "gpt-4o")

SYSTEM_PROMPT = (
    "너는 소상공인 점포의 온라인 마케팅 콘텐츠를 만드는 전문 작가다. "
    "제공된 [점포 정보]에 있는 사실만 사용하고, 없는 사실(가격·메뉴·수상 이력·손님 반응 등)은 절대 지어내지 않는다. "
    "리뷰 요약이 '없음'이면 손님 후기·반응·평판을 일절 언급하지 않는다. "
    "과장 광고 표현('인생 최고', '무조건')보다 구체적 사실 중심으로 쓴다."
)

# blog_revise용: 일부러 약점 있는 초안을 만들 때 주입할 진단 이슈 풀 (모듈① 진단 항목 형식)
DIAGNOSIS_POOL = [
    "지역(동네) 키워드가 본문에 없음",
    "영업시간·휴무일 정보 누락",
    "질문형 소제목이 없어 AEO에 불리함",
    "대표 메뉴와 가격 언급 부족",
    "방문 유도 문구(위치 안내·CTA) 없음",
    "문단 구분 없이 글이 한 덩어리임",
]


def build_store_input(store: dict) -> str:
    return TEMPLATES["store_input_format"]["template"].format(**store)


def call_teacher(user_content: str, system: str = SYSTEM_PROMPT, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            resp = client.chat.completions.create(
                model=TEACHER_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
            )
            return resp.choices[0].message.content.strip()
        except Exception as e:  # rate limit 등 일시 오류 재시도
            if attempt == retries - 1:
                raise
            wait = 5 * (attempt + 1)
            print(f"  API 오류({e.__class__.__name__}), {wait}초 후 재시도...")
            time.sleep(wait)
    raise RuntimeError("unreachable")


def parse_shorts_json(text: str) -> dict | None:
    """코드펜스 제거 후 JSON 파싱 + 스키마 검증. 실패 시 None."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not all(k in obj for k in ("script", "caption", "hashtags")):
        return None
    if not isinstance(obj["hashtags"], list) or not obj["hashtags"]:
        return None
    return obj


def gen_blog_new(store: dict) -> dict:
    spec = TEMPLATES["tasks"]["blog_new"]
    store_input = build_store_input(store)
    output = call_teacher(f"{spec['instruction']}\n\n{store_input}")
    return {"task": spec["task_tag"], "instruction": spec["instruction"], "input": store_input, "output": output}


def gen_shorts(store: dict) -> dict | None:
    spec = TEMPLATES["tasks"]["shorts"]
    store_input = build_store_input(store)
    for _ in range(3):  # JSON 파싱 실패 시 재생성
        raw = call_teacher(f"{spec['instruction']}\n\n{store_input}")
        obj = parse_shorts_json(raw)
        if obj is not None:
            return {
                "task": spec["task_tag"],
                "instruction": spec["instruction"],
                "input": store_input,
                "output": json.dumps(obj, ensure_ascii=False),
            }
        print(f"  [{store['store_id']}] 쇼츠 JSON 파싱 실패, 재생성...")
    return None


def gen_blog_revise(store: dict, rng: random.Random) -> dict:
    """2단계: ① 약점 있는 초안 생성 → ② 진단 반영 개선본 생성."""
    spec = TEMPLATES["tasks"]["blog_revise"]
    store_input = build_store_input(store)
    issues = rng.sample(DIAGNOSIS_POOL, k=rng.randint(2, 3))

    draft_prompt = (
        f"아래 점포의 블로그 소개글 초안을 400~600자로 작성하라. "
        f"단, 일부러 다음 약점을 그대로 가진 평범한 글로 써라(개선하지 말 것): {', '.join(issues)}. "
        f"점포 정보에 없는 사실은 여기서도 지어내지 마라.\n\n{store_input}"
    )
    draft = call_teacher(draft_prompt)

    extra = spec["extra_input_format"].format(
        existing_content=draft,
        diagnosis_issues="\n".join(f"- {i}" for i in issues),
        owner_feedback="없음",
    )
    full_input = f"{store_input}\n\n{extra}"
    output = call_teacher(f"{spec['instruction']}\n\n{full_input}")
    return {"task": spec["task_tag"], "instruction": spec["instruction"], "input": full_input, "output": output}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stores", type=Path, default=STORES_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--per-task", type=int, default=10)
    parser.add_argument("--tasks", default="blog_new,blog_revise,shorts",
                        help="쉼표 구분: blog_new,blog_revise,shorts")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    stores = [json.loads(l) for l in args.stores.read_text(encoding="utf-8").splitlines() if l.strip()]
    rng = random.Random(args.seed)
    rng.shuffle(stores)
    tasks = [t.strip() for t in args.tasks.split(",")]

    generators = {"blog_new": gen_blog_new, "shorts": gen_shorts,
                  "blog_revise": lambda s: gen_blog_revise(s, rng)}

    args.out.parent.mkdir(parents=True, exist_ok=True)
    done, failed = 0, 0
    store_iter = iter(stores * 10)  # 점포 수보다 많이 뽑아야 할 때 재사용

    with args.out.open("a", encoding="utf-8") as f:
        for task in tasks:
            print(f"\n=== {task} × {args.per_task}개 (교사: {TEACHER_MODEL}) ===")
            for i in range(args.per_task):
                store = next(store_iter)
                try:
                    record = generators[task](store)
                except Exception as e:
                    print(f"  [{store['store_id']}] 생성 실패: {e}")
                    failed += 1
                    continue
                if record is None:
                    failed += 1
                    continue
                record["meta"] = {
                    "store_id": store["store_id"],
                    "category": store["category"],
                    "location": store["location"],
                    "has_review": store["review_summary"] != "없음",
                    "teacher_model": TEACHER_MODEL,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                f.flush()
                done += 1
                print(f"  [{i + 1}/{args.per_task}] {store['store_name']} ({store['category']}) ✓")
                time.sleep(0.3)

    print(f"\n완료: {done}개 저장, 실패 {failed}개 → {args.out}")


if __name__ == "__main__":
    main()
