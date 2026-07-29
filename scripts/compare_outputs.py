"""두 어댑터의 홀드아웃 출력 비교 (Day 5 비교 평가 2단계).

자동 지표(쇼츠 JSON 파싱률, 환각 검사, 생성 속도)를 집계하고,
팀 블라인드 평가용 문서(모델명을 A/B로 가린 나란히 비교)를 만든다.

사용:
    python scripts/compare_outputs.py
    → data/eval/metrics.md            (자동 지표 표)
    → data/eval/blind_review.md       (블라인드 평가지 — 팀 공유용)
    → data/eval/answer_key.json       (A/B 정답 — 평가 끝나기 전엔 열지 말 것)
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
EVAL_DIR = ROOT / "data" / "eval"

REP_WORDS = ["후기", "리뷰", "입소문", "평이 많", "평판", "재주문율", "재구매율", "사랑받", "소문난", "인기 있는", "인기가 많"]
TRANSPORT_WORDS = ["지하철", "버스", "역에서", "도보", "주차"]


def check(rec: dict) -> dict:
    """출력 1건의 자동 검사 결과."""
    inp, out = rec["input"], rec["model_output"]
    res = {"json_ok": None, "price_halluc": False, "rep_halluc": False, "transport_halluc": False}
    if rec["task"] == "쇼츠":
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", out.strip())
        try:
            obj = json.loads(cleaned)
            res["json_ok"] = all(k in obj for k in ("script", "caption", "hashtags"))
        except json.JSONDecodeError:
            res["json_ok"] = False
    res["price_halluc"] = any(p not in inp for p in re.findall(r"[\d,]+원", out))
    if "리뷰 요약: 없음" in inp:
        res["rep_halluc"] = any(w in out for w in REP_WORDS)
    res["transport_halluc"] = any(w in out and w not in inp for w in TRANSPORT_WORDS)
    return res


def main() -> None:
    outputs = {}
    for key in ("qwen", "eeve"):
        path = EVAL_DIR / f"outputs_{key}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} 없음 — evaluate_adapters.py --model {key} 를 먼저 실행하세요.")
        outputs[key] = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()]

    # ── 자동 지표 집계
    lines = ["# 자동 지표 비교\n", "| 지표 | qwen | eeve |", "|---|---|---|"]
    stats = {}
    for key, recs in outputs.items():
        checks = [check(r) for r in recs]
        shorts = [c for c in checks if c["json_ok"] is not None]
        stats[key] = {
            "쇼츠 JSON 파싱 성공": f"{sum(c['json_ok'] for c in shorts)}/{len(shorts)}",
            "가격 환각 건수": sum(c["price_halluc"] for c in checks),
            "평판 환각 건수": sum(c["rep_halluc"] for c in checks),
            "교통 환각 건수": sum(c["transport_halluc"] for c in checks),
            "평균 생성 시간(s)": round(sum(r["gen_seconds"] for r in recs) / len(recs), 1),
        }
    for metric in next(iter(stats.values())):
        lines.append(f"| {metric} | {stats['qwen'][metric]} | {stats['eeve'][metric]} |")
    (EVAL_DIR / "metrics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))

    # ── 블라인드 평가지 (항목별로 A/B 순서 랜덤)
    rng = random.Random(2026)
    key_map = []
    doc = ["# 블라인드 평가지\n",
           "각 항목에서 A/B 중 더 나은 쪽에 ✓ 하세요. 기준: ①사실 준수 ②형식 준수 ③문체 자연스러움.",
           "어느 쪽이 어떤 모델인지는 answer_key.json에 있습니다 (평가 후 확인).\n"]
    for i, (q, e) in enumerate(zip(outputs["qwen"], outputs["eeve"])):
        pair = [("qwen", q), ("eeve", e)]
        rng.shuffle(pair)
        key_map.append({"idx": i, "A": pair[0][0], "B": pair[1][0]})
        doc += [f"\n---\n\n## 항목 {i + 1} · {q['task']}\n",
                f"### 입력\n```\n{q['input']}\n```\n",
                f"### A\n\n{pair[0][1]['model_output']}\n",
                f"### B\n\n{pair[1][1]['model_output']}\n",
                "**선택: [ ] A  [ ] B  — 이유:**\n"]
    (EVAL_DIR / "blind_review.md").write_text("\n".join(doc), encoding="utf-8")
    (EVAL_DIR / "answer_key.json").write_text(json.dumps(key_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n블라인드 평가지 → {EVAL_DIR / 'blind_review.md'}")
    print(f"정답지(평가 후 열기) → {EVAL_DIR / 'answer_key.json'}")


if __name__ == "__main__":
    main()
