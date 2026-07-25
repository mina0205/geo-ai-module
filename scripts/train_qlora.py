"""QLoRA 학습 스크립트 (Day 4).

dataset.jsonl(500개)로 베이스 모델 후보를 각각 학습해 어댑터를 저장한다.
Colab L4/A100에서 실행 (모델당 약 1~2시간).

사용 (Colab):
    python scripts/train_qlora.py --model qwen
    python scripts/train_qlora.py --model eeve
    → outputs/adapters/geo-lora-adapter-v0-{qwen|eeve}/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

ROOT = Path(__file__).parent.parent
MODELS = json.loads((ROOT / "configs" / "models.json").read_text(encoding="utf-8"))
DATA_DEFAULT = ROOT / "data" / "synthetic" / "dataset.jsonl"

SYSTEM_PROMPT = (
    "너는 소상공인 점포 전용 마케팅 콘텐츠 생성기다. "
    "제공된 점포 정보에 있는 사실만 사용해 요청된 형식의 콘텐츠를 작성한다."
)


def load_as_messages(path: Path) -> Dataset:
    """학습 JSONL → chat messages 포맷 (SFTTrainer가 모델별 챗 템플릿을 자동 적용)."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{r['instruction']}\n\n{r['input']}"},
                {"role": "assistant", "content": r["output"]},
            ]
        })
    return Dataset.from_list(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(MODELS["candidates"]), required=True)
    parser.add_argument("--data", type=Path, default=DATA_DEFAULT)
    parser.add_argument("--epochs", type=int, default=MODELS["qlora"]["epochs"])
    args = parser.parse_args()

    cand = MODELS["candidates"][args.model]
    q = MODELS["qlora"]
    out_dir = ROOT / "outputs" / "adapters" / f"{q['adapter_name_prefix']}-{args.model}"

    dataset = load_as_messages(args.data)
    print(f"학습 데이터 {len(dataset)}개 / 모델 {cand['model_id']} / {args.epochs} epoch → {out_dir}")

    bnb = BitsAndBytesConfig(
        load_in_4bit=q["load_in_4bit"],
        bnb_4bit_quant_type=q["bnb_4bit_quant_type"],
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        cand["model_id"], quantization_config=bnb, device_map="auto"
    )
    tokenizer = AutoTokenizer.from_pretrained(cand["model_id"])

    lora = LoraConfig(
        r=q["lora_r"],
        lora_alpha=q["lora_alpha"],
        lora_dropout=q["lora_dropout"],
        target_modules=q["target_modules"],
        task_type="CAUSAL_LM",
    )

    sft_config = SFTConfig(
        output_dir=str(out_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        save_strategy="epoch",
        bf16=True,
        max_length=2048,
        gradient_checkpointing=True,
        optim="paged_adamw_8bit",
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=dataset,
        peft_config=lora,
        args=sft_config,
    )
    trainer.train()
    trainer.save_model(str(out_dir))
    print(f"어댑터 저장 완료: {out_dir}")


if __name__ == "__main__":
    main()
