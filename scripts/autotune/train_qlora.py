"""QLoRA fine-tune of the student model for plan_autotune S3.

Runs ONLY on a Linux GPU box — primary target: **Kaggle free tier** (T4x2 or
P100, 30 GPU-h/week, sessions <=12h; see scripts/autotune/kaggle/), fallback:
rented RunPod/Vast 4090. Never on the Windows dev machine. Heavy imports
(torch/unsloth/trl/datasets) are lazy, inside `train()`, so repo gates
(ruff/mypy/pytest) stay green without them; `--help` works anywhere.

Precision is auto-detected: bf16 on Ampere+ (4090), fp16 on T4/P100 (Turing
and older have no bfloat16). Checkpoints are saved every --save-steps so a
Kaggle 12h session cut mid-epoch resumes with --resume (attach the previous
run's output and copy its checkpoints into --out first — the Kaggle notebook
does this automatically).

Kaggle T4 preset (fits 16GB, ~6-12h for 1 epoch):
    python train_qlora.py --epochs 1 --max-seq-len 4096 \\
        --batch-size 1 --grad-accum 16 --no-merge --resume

Node setup (see scripts/autotune/requirements_gpu.txt for install order):
    pip install unsloth && pip install -r scripts/autotune/requirements_gpu.txt

Train (defaults follow plan_autotune S3: r=16, alpha=32, lr 2e-4, 2 epochs):
    python scripts/autotune/train_qlora.py \\
        --train data/autotune/train.jsonl --val data/autotune/val.jsonl \\
        --out /workspace/qlora_out

Serve the result for the eval harness (merged dir is the simplest path):
    vllm serve /workspace/qlora_out/merged --port 8000 \\
        --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct-sqltuned
    # Windows side: NL_SQL_LOCAL_LLM_BASE_URL=http://<host>:8000/v1 in .env,
    # then eval_baseline.py --provider local_vllm \\
    #   --sql-model Qwen/Qwen2.5-Coder-7B-Instruct-sqltuned --fewshot-top-k 0
    # (--sql-model MUST equal --served-model-name or vLLM 404s the request).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

# Qwen2/2.5 chat-template markers used to mask loss onto assistant tokens only.
QWEN_USER_MARK = "<|im_start|>user\n"
QWEN_ASSISTANT_MARK = "<|im_start|>assistant\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    parser.add_argument("--train", default="data/autotune/train.jsonl")
    parser.add_argument("--val", default="data/autotune/val.jsonl")
    parser.add_argument("--out", default="qlora_out")
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--alpha", type=int, default=32)
    parser.add_argument("--max-seq-len", type=int, default=8192)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--seed", type=int, default=0)
    # ~138 s/step measured on a Kaggle T4 (seq 4096, batch 1, grad-accum 16),
    # so 50 steps is roughly a two-hour checkpoint interval -- small enough that
    # a 12h session cut off mid-epoch loses little.
    parser.add_argument("--save-steps", type=int, default=50)
    parser.add_argument(
        "--val-rows",
        type=int,
        default=64,
        help="cap eval rows (0 = all); eval loss is a smoke signal, not the verdict",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="stop after N optimizer steps (0 = full run); smoke-tests the whole path",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="resume from the last checkpoint in <out>/checkpoints, if any",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="skip the merged-16bit export (adapter only)",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def accepted_kwargs(cls: Any) -> set[str] | None:
    """Keyword names `cls(...)` really takes, or None when undiscoverable.

    trl renames config fields between releases and raises TypeError on a stale
    name — `max_seq_length` -> `max_length` is exactly what killed the first
    Kaggle run. Probing beats guessing per-key. None means "opaque **kwargs
    signature, pass everything through and let the callee decide".
    """
    import dataclasses
    import inspect

    names: set[str] = set()
    if dataclasses.is_dataclass(cls):
        names |= {f.name for f in dataclasses.fields(cls)}
    try:
        params = inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return names or None
    if not names and any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return None
    names |= {n for n, p in params.items() if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)}
    names.discard("self")
    return names or None


def train(args: argparse.Namespace) -> None:
    # Lazy heavy imports — GPU box only (see module docstring). unsloth MUST be
    # imported before trl/transformers: it patches them for the fast path.
    # isort: off
    from unsloth import FastLanguageModel, is_bfloat16_supported
    from unsloth.chat_templates import train_on_responses_only

    from datasets import Dataset
    from trl import SFTConfig, SFTTrainer

    # isort: on

    bf16_ok = is_bfloat16_supported()

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.model,
        max_seq_length=args.max_seq_len,
        load_in_4bit=True,
        dtype=None,  # unsloth picks bf16 on Ampere+
    )
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.rank,
        lora_alpha=args.alpha,
        lora_dropout=0.0,
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
        random_state=args.seed,
    )

    def to_text(rows: list[dict[str, str]]) -> Dataset:
        def render(row: dict[str, str]) -> dict[str, Any]:
            text = tokenizer.apply_chat_template(
                [
                    {"role": "user", "content": row["prompt"]},
                    {"role": "assistant", "content": row["completion"]},
                ],
                tokenize=False,
                add_generation_prompt=False,
            )
            return {"text": text}

        return Dataset.from_list([render(r) for r in rows])

    train_ds = to_text(load_jsonl(Path(args.train)))
    val_ds = to_text(load_jsonl(Path(args.val)))
    print(f"train={len(train_ds)} val={len(val_ds)}")
    # Eval here is a smoke signal, not the verdict (that is BIRD EA from the
    # harness). On a T4 a forward pass costs ~9 s, so evaluating all 500 val
    # rows would burn over an hour of a 12h session for a number we do not
    # judge by. A smoke run needs even less.
    val_cap = 8 if args.max_steps > 0 else args.val_rows
    if val_cap:
        val_ds = val_ds.select(range(min(val_cap, len(val_ds))))
        print(f"val capped to {len(val_ds)}")

    out_dir = Path(args.out)
    cfg_kwargs: dict[str, Any] = {
        "output_dir": str(out_dir / "checkpoints"),
        "dataset_text_field": "text",
        "per_device_train_batch_size": args.batch_size,
        "gradient_accumulation_steps": args.grad_accum,
        "num_train_epochs": args.epochs,
        "learning_rate": args.lr,
        "lr_scheduler_type": "linear",
        "warmup_ratio": 0.03,
        "optim": "adamw_8bit",
        "bf16": bf16_ok,
        "fp16": not bf16_ok,
        "logging_steps": 20,
        # Eval must return the loss and nothing else. Without this the Trainer
        # gathers full logits (batch x seq x 152k vocab) and upcasts them to
        # fp32 -- a 6 GiB allocation that OOMs a 16GB T4 *after* training has
        # already succeeded. The verdict for this track is BIRD EA from the
        # harness anyway; eval loss is only a smoke signal.
        "prediction_loss_only": True,
        "per_device_eval_batch_size": 1,
        "eval_strategy": "epoch",
        "save_strategy": "steps",
        "save_steps": args.save_steps,
        "save_total_limit": 2,
        "seed": args.seed,
        "report_to": "none",
    }
    if args.max_steps > 0:
        cfg_kwargs["max_steps"] = args.max_steps
    # Reconcile with whatever this trl release actually accepts (see
    # accepted_kwargs). Unknown options are dropped LOUDLY — a silently
    # swallowed fp16 would train the T4 run in the wrong dtype and we would
    # only notice hours later.
    sft_keys = accepted_kwargs(SFTConfig)
    # Prefer the modern name; fall back to the legacy one only when the release
    # explicitly lacks it (old RunPod images).
    seq_key = "max_seq_length" if sft_keys and "max_length" not in sft_keys else "max_length"
    cfg_kwargs[seq_key] = args.max_seq_len
    if sft_keys:
        dropped = sorted(set(cfg_kwargs) - sft_keys)
        must_keep = [k for k in dropped if k in {"bf16", "fp16", "max_steps", seq_key}]
        if must_keep:
            raise SystemExit(f"SFTConfig rejects required options {must_keep}; update this script")
        for key in dropped:
            print(f"SFTConfig: dropping unsupported option {key!r}", flush=True)
            cfg_kwargs.pop(key)
    print(f"SFTConfig kwargs: {sorted(cfg_kwargs)}", flush=True)
    trainer_kwargs: dict[str, Any] = {
        "model": model,
        "train_dataset": train_ds,
        "eval_dataset": val_ds,
        "args": SFTConfig(**cfg_kwargs),
    }
    trainer_keys = accepted_kwargs(SFTTrainer)
    tok_key = (
        "tokenizer"
        if trainer_keys and "processing_class" not in trainer_keys
        else "processing_class"
    )
    trainer_kwargs[tok_key] = tokenizer
    trainer = SFTTrainer(**trainer_kwargs)
    # Mask loss to assistant tokens only — the huge schema prompt must not
    # dominate the gradient signal.
    trainer = train_on_responses_only(
        trainer,
        instruction_part=QWEN_USER_MARK,
        response_part=QWEN_ASSISTANT_MARK,
    )
    has_checkpoint = any((out_dir / "checkpoints").glob("checkpoint-*"))
    trainer.train(resume_from_checkpoint=True if (args.resume and has_checkpoint) else None)
    print("final eval:", trainer.evaluate())

    adapter_dir = out_dir / "adapter"
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    print(f"adapter saved: {adapter_dir}")
    if not args.no_merge:
        merged_dir = out_dir / "merged"
        model.save_pretrained_merged(str(merged_dir), tokenizer, save_method="merged_16bit")
        print(f"merged model saved: {merged_dir}")


if __name__ == "__main__":
    train(parse_args())
