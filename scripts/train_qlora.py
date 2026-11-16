"""QLoRA fine-tune of the generator (qwen2.5-coder 1.5B) on the distillation dataset.

    python scripts/train_qlora.py --train data/train.jsonl --out runs/ft-v1 --smoke   # first: 64 ex, 20 steps
    python scripts/train_qlora.py --train data/train.jsonl --out runs/ft-v1           # then the real run

Written for ONE machine: an RTX 3070 with 8 GB, 4-bit base (NF4), bf16 compute. Read
specs/001-qcircuit-agent/training-handoff.md first; every step there says what to check.

UNTESTED ON A GPU. It was written in a sandbox with no GPU; the loop structure (LoRA, loss on the
completion only, accumulation, adapter save) is the one the CPU round-trip exercised, the 4-bit load and
`prepare_model_for_kbit_training` were not. Expect to fix an import or a dtype on the first run, and use
--smoke for that.

Input, one JSON object per line (the exporter must produce exactly this):
    {"id": str, "family": str, "messages": [{"role": "system", ...}, {"role": "user", ...}],
     "completion": "```python\\n...\\n```"}
`messages` must be what the harness sends the generator on attempt 1 (GENERATOR_SYSTEM_PROMPT and
`_build_prompt(...)` from src/qcagent/nodes/generator.py, requirements + retrieved context), rendered by the
real planner and retriever at the pinned build. This script does not build prompts.

The validation split is drawn from THIS file (the training distribution), stratified by family. It never
reads bench/tasks/: the only contact with the 120 is a refusal, below, if a training prompt equals a test prompt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IM_END = "<|im_end|>"


def load_records(path: Path) -> list[dict]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    for r in records:
        for key in ("id", "family", "messages", "completion"):
            if key not in r:
                sys.exit(f"record {r.get('id', '?')} lacks '{key}'")
        if r["messages"][-1]["role"] != "user":
            sys.exit(f"record {r['id']}: the last message must be the user turn")
    if len({r["id"] for r in records}) != len(records):
        sys.exit("duplicate ids in the training file")
    return records


def refuse_test_prompts(records: list[dict]) -> None:
    """Exact-match tripwire only. The leakage gate (lexical, structural, circuit) is what keeps the 120
    out; this catches the one gross failure, a training prompt that IS a test statement."""
    test = set()
    for p in sorted((ROOT / "bench" / "tasks").glob("*/*.json")):
        test.add(json.loads(p.read_text())["prompt"].strip())
    for r in records:
        user = r["messages"][-1]["content"]
        if any(t in user for t in test):
            sys.exit(f"record {r['id']}: its prompt contains a test statement verbatim. Stop; tell the owner.")


def split(records: list[dict], fraction: float, seed: int) -> tuple[list[dict], list[dict]]:
    """Stratified by family, deterministic. Validation loss is OPTIMISTIC: sibling variations of one family
    are similar, so it measures fit to the distribution, not generalisation to unseen families."""
    rng = random.Random(seed)
    by_family: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_family[r["family"]].append(r)
    train, val = [], []
    for family in sorted(by_family):
        items = sorted(by_family[family], key=lambda r: r["id"])
        rng.shuffle(items)
        k = max(1, round(len(items) * fraction))
        val += items[:k]
        train += items[k:]
    return train, val


def encode(tok, record: dict, max_len: int) -> dict | None:
    """Prompt tokens are masked (-100); only the completion, closed by <|im_end|>, is learned."""
    prompt = tok.apply_chat_template(record["messages"], tokenize=False, add_generation_prompt=True)
    p_ids = tok(prompt, add_special_tokens=False).input_ids
    c_ids = tok(record["completion"].strip() + IM_END, add_special_tokens=False).input_ids
    if len(p_ids) + len(c_ids) > max_len:
        return None  # never truncated silently: dropped and counted
    return {"input_ids": p_ids + c_ids, "labels": [-100] * len(p_ids) + c_ids, "n_prompt": len(p_ids)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--base", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    ap.add_argument("--val-fraction", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--grad-accum", type=int, default=16, help="micro-batch is 1; effective batch = this")
    ap.add_argument("--max-len", type=int, default=4096)
    ap.add_argument("--eval-every", type=int, default=25, help="optimizer steps")
    ap.add_argument("--max-drop-fraction", type=float, default=0.02)
    ap.add_argument("--smoke", action="store_true", help="the 64 LONGEST examples, 20 steps, to find the first error cheaply")
    args = ap.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        sys.exit("No CUDA device. This script is for the 3070; a CPU run would take days.")
    random.seed(args.seed)
    torch.manual_seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)

    records = load_records(args.train)
    refuse_test_prompts(records)
    train_r, val_r = split(records, args.val_fraction, args.seed)
    tok = AutoTokenizer.from_pretrained(args.base)
    enc_train = [e for r in train_r if (e := encode(tok, r, args.max_len))]
    enc_val = [e for r in val_r if (e := encode(tok, r, args.max_len))]
    dropped = (len(train_r) - len(enc_train)) + (len(val_r) - len(enc_val))
    print(f"train {len(enc_train)}  val {len(enc_val)}  dropped for length {dropped}")
    if dropped > args.max_drop_fraction * (len(train_r) + len(val_r)):
        sys.exit(f"{dropped} examples exceed --max-len {args.max_len}: more than "
                 f"{args.max_drop_fraction:.0%}. Do not raise the cap blindly; look at the prompt sizes first.")
    lens = sorted(len(e["input_ids"]) for e in enc_train)
    print(f"tokens/example  median {lens[len(lens) // 2]}  p95 {lens[int(len(lens) * .95)]}  max {lens[-1]}")
    if args.smoke:
        # The LONGEST examples, not a random sample: the logits tensor is the largest VRAM cost, so an
        # out-of-memory on a long example is the likeliest first failure, and this puts it in the first
        # steps instead of step two hundred. (Every step draws 16 of these 64.)
        enc_train = sorted(enc_train, key=lambda e: -len(e["input_ids"]))[:64]
        enc_val = sorted(enc_val, key=lambda e: -len(e["input_ids"]))[:8]
        print(f"smoke: the {len(enc_train)} longest training examples, {enc_train[0]['input_ids'].__len__()} "
              f"tokens down to {len(enc_train[-1]['input_ids'])}")

    (args.out / "split.json").write_text(json.dumps(
        {"seed": args.seed, "val_fraction": args.val_fraction,
         "train_ids": sorted(r["id"] for r in train_r), "val_ids": sorted(r["id"] for r in val_r)}, indent=1))

    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                             bnb_4bit_compute_dtype=torch.bfloat16)
    model = AutoModelForCausalLM.from_pretrained(args.base, quantization_config=bnb, device_map={"": 0},
                                                 dtype=torch.bfloat16, attn_implementation="sdpa")
    # NOT prepare_model_for_kbit_training: on this stack it left attention memory quadratic (4.2 GB -> out of
    # memory / "device not ready" past ~6k tokens). Plain non-reentrant checkpointing is linear: measured
    # 1.8 GB at 2k tokens, 4.2 GB at 11k (the longest example), on the 3070.
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]))
    model.print_trainable_parameters()

    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    steps_per_epoch = math.ceil(len(enc_train) / args.grad_accum)
    total_steps = 20 if args.smoke else steps_per_epoch * args.epochs
    warmup = max(1, int(0.03 * total_steps))

    def lr_at(step: int) -> float:  # linear warmup, then cosine to 10% of the peak
        if step < warmup:
            return args.lr * (step + 1) / warmup
        t = (step - warmup) / max(1, total_steps - warmup)
        return args.lr * (0.1 + 0.9 * 0.5 * (1 + math.cos(math.pi * t)))

    def example_loss(e: dict):
        """Mean cross-entropy over the completion tokens only, with logits computed ONLY there.

        The full-vocabulary logits tensor (sequence x 151,936 x 4 bytes) is the largest VRAM cost and the
        prompts here run 4.7k to 11k tokens (retrieved context), against about 120 completion tokens. The
        completion is the tail of the sequence, so `logits_to_keep` returns just the positions that predict it
        (n_prompt-1 .. end); the loss is the same as the labels-masked one, without the 11k-row tensor."""
        ids = torch.tensor([e["input_ids"]], device="cuda")
        n_c = len(e["input_ids"]) - e["n_prompt"]
        logits = model(input_ids=ids, logits_to_keep=n_c + 1).logits[:, :-1].float()
        target = ids[:, e["n_prompt"]:]
        return torch.nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), target.reshape(-1))

    @torch.no_grad()
    def evaluate() -> float:
        model.eval()
        tot, n = 0.0, 0
        for e in enc_val:
            k = sum(1 for x in e["labels"] if x != -100)
            tot += float(example_loss(e)) * k
            n += k
        model.train()
        return tot / max(n, 1)

    model.train()
    order: list[int] = []
    step_times: list[float] = []
    best_val, log = float("inf"), []
    print(f"{total_steps} optimizer steps, effective batch {args.grad_accum}")
    for step in range(total_steps):
        t0 = time.time()
        for g in opt.param_groups:
            g["lr"] = lr_at(step)
        loss_sum, tok_n = 0.0, 0
        for _ in range(args.grad_accum):
            if not order:
                order = list(range(len(enc_train)))
                random.shuffle(order)
            e = enc_train[order.pop()]
            loss = example_loss(e)
            (loss / args.grad_accum).backward()
            loss_sum += float(loss)
            tok_n += len(e["input_ids"])
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        opt.zero_grad(set_to_none=True)
        dt = time.time() - t0
        step_times.append(dt)
        row = {"step": step + 1, "loss": loss_sum / args.grad_accum, "lr": lr_at(step), "sec": round(dt, 1),
               "tok_s": round(tok_n / dt), "vram_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2)}
        if len(step_times) > 5 and dt > 5 * statistics.median(step_times[:5]):
            row["WARNING"] = "step far slower than the first five: stall, thermal throttle or VRAM spill"
        if (step + 1) % args.eval_every == 0 or step + 1 == total_steps:
            row["val_loss"] = round(evaluate(), 4)
            model.save_pretrained(args.out / "adapter-last")
            if row["val_loss"] < best_val:
                best_val = row["val_loss"]
                model.save_pretrained(args.out / "adapter-best")
        log.append(row)
        print(json.dumps(row), flush=True)

    (args.out / "log.jsonl").write_text("\n".join(json.dumps(r) for r in log) + "\n")
    import importlib.metadata as md
    (args.out / "manifest.json").write_text(json.dumps({
        "base": args.base, "args": {k: str(v) for k, v in vars(args).items()},
        "train_file_sha256": hashlib.sha256(args.train.read_bytes()).hexdigest(),
        "n_train": len(enc_train), "n_val": len(enc_val), "best_val_loss": best_val,
        "libs": {p: md.version(p) for p in ("torch", "transformers", "peft", "bitsandbytes", "accelerate")},
        "note": "adapter-best = lowest validation loss; adapter-last = final step",
    }, indent=1))
    print("done. adapters in", args.out)


if __name__ == "__main__":
    main()
