"""Day1 GPU 환경 점검 스크립트.

Colab/RunPod에서 실행:
    python scripts/check_gpu.py            # 환경 점검만
    python scripts/check_gpu.py --load qwen  # Qwen2.5-7B 4bit 로드 테스트
    python scripts/check_gpu.py --load eeve  # EEVE-10.8B 4bit 로드 테스트
"""

import argparse
import json
import sys
from pathlib import Path

MODELS = json.loads((Path(__file__).parent.parent / "configs" / "models.json").read_text(encoding="utf-8"))


def check_env() -> bool:
    ok = True
    print(f"python      : {sys.version.split()[0]}")

    try:
        import torch
        print(f"torch       : {torch.__version__}")
        if not torch.cuda.is_available():
            print("CUDA        : ✗ 사용 불가 — GPU 런타임인지 확인하세요 (Colab: 런타임 > 런타임 유형 변경)")
            return False
        name = torch.cuda.get_device_name(0)
        total_gb = torch.cuda.get_device_properties(0).total_memory / 1024**3
        print(f"CUDA        : ✓ {torch.version.cuda}")
        print(f"GPU         : {name} ({total_gb:.1f} GB)")
        print(f"bf16 지원    : {'✓' if torch.cuda.is_bf16_supported() else '✗ (fp16으로 대체 필요)'}")
        if total_gb < 15:
            print("경고         : VRAM 15GB 미만 — EEVE-10.8B QLoRA는 빠듯할 수 있음 (L4/A100 권장)")
    except ImportError:
        print("torch       : ✗ 미설치 (pip install -r requirements.txt)")
        return False

    for pkg in ["transformers", "peft", "trl", "bitsandbytes", "datasets", "accelerate"]:
        try:
            mod = __import__(pkg)
            print(f"{pkg:<12}: {getattr(mod, '__version__', '?')}")
        except ImportError:
            print(f"{pkg:<12}: ✗ 미설치")
            ok = False
    return ok


def load_test(key: str) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    model_id = MODELS["candidates"][key]["model_id"]
    print(f"\n4bit 로드 테스트: {model_id}")
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
    )
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=bnb, device_map="auto")

    messages = [{"role": "user", "content": "경기도 수원의 김치찌개 맛집을 한 문장으로 소개해줘."}]
    inputs = tokenizer.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(model.device)
    out = model.generate(inputs, max_new_tokens=64, do_sample=False)
    print("샘플 출력    :", tokenizer.decode(out[0][inputs.shape[1]:], skip_special_tokens=True))
    print(f"VRAM 사용    : {torch.cuda.max_memory_allocated() / 1024**3:.1f} GB")
    print("로드 테스트  : ✓ 통과")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--load", choices=list(MODELS["candidates"]), help="4bit 모델 로드+생성 테스트")
    args = parser.parse_args()

    if not check_env():
        sys.exit(1)
    if args.load:
        load_test(args.load)
