"""학습된 어댑터로 홀드아웃 10개 추론 (Day 5 비교 평가 1단계).

홀드아웃의 instruction+input을 학습 때와 동일한 형식으로 넣고
샘플링 생성한 결과를 저장한다. 두 모델 각각 실행.

사용 (Colab, 학습 직후 같은 세션 권장 — 베이스 모델 캐시 재사용):
    python scripts/evaluate_adapters.py --model qwen
    python scripts/evaluate_adapters.py --model eeve
    # 어댑터를 Drive에서 복원한 경우: --adapter /content/drive/MyDrive/.../geo-lora-adapter-v0-qwen
    → data/eval/outputs_{model}.jsonl
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

ROOT = Path(__file__).parent.parent
MODELS = json.loads((ROOT / "configs" / "models.json").read_text(encoding="utf-8"))
HOLDOUT_DEFAULT = ROOT / "data" / "synthetic" / "holdout.jsonl"

# train_qlora.py 와 반드시 동일해야 함
SYSTEM_PROMPT = (
    "너는 소상공인 점포 전용 마케팅 콘텐츠 생성기다. "
    "제공된 점포 정보에 있는 사실만 사용해 요청된 형식의 콘텐츠를 작성한다."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(MODELS["candidates"]), required=True)
    parser.add_argument("--adapter", type=Path, default=None,
                        help="어댑터 경로 (기본: outputs/adapters/geo-lora-adapter-v0-{model})")
    parser.add_argument("--holdout", type=Path, default=HOLDOUT_DEFAULT)
    args = parser.parse_args()

    cand = MODELS["candidates"][args.model]
    adapter = args.adapter or ROOT / "outputs" / "adapters" / f"{MODELS['qlora']['adapter_name_prefix']}-{args.model}"
    out_path = ROOT / "data" / "eval" / f"outputs_{args.model}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    records = [json.loads(l) for l in args.holdout.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"홀드아웃 {len(records)}개 / 베이스 {cand['model_id']} / 어댑터 {adapter}")

    use_bf16 = torch.cuda.is_bf16_supported()
    bnb = BitsAndBytesConfig(
        load_in_4bit=True, bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if use_bf16 else torch.float16,
    )
    base = AutoModelForCausalLM.from_pretrained(cand["model_id"], quantization_config=bnb, device_map="auto")
    model = PeftModel.from_pretrained(base, str(adapter))
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(cand["model_id"])

    with out_path.open("w", encoding="utf-8") as f:
        for i, r in enumerate(records):
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{r['instruction']}\n\n{r['input']}"},
            ]
            inputs = tokenizer.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
            ).to(model.device)
            t0 = time.time()
            with torch.no_grad():
                out = model.generate(
                    **inputs, max_new_tokens=1024,
                    do_sample=True, temperature=0.7, top_p=0.9,
                    pad_token_id=tokenizer.eos_token_id,
                )
            gen = tokenizer.decode(out[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
            elapsed = time.time() - t0
            f.write(json.dumps({
                "idx": i, "task": r["task"], "input": r["input"],
                "teacher_output": r["output"], "model_output": gen.strip(),
                "gen_seconds": round(elapsed, 1),
            }, ensure_ascii=False) + "\n")
            print(f"  [{i + 1}/{len(records)}] {r['task']} ({elapsed:.1f}s) ✓")

    print(f"저장 완료 → {out_path}")


if __name__ == "__main__":
    main()
