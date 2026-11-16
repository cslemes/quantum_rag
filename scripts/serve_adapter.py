"""Adapter -> merged weights -> Ollama model, over HTTP. Three subcommands, run in this order:

    python scripts/serve_adapter.py merge  --adapter runs/ft-v1/adapter-best --out runs/ft-v1/merged
    # (GGUF conversion is a llama.cpp command, see training-handoff.md step 6)
    python scripts/serve_adapter.py create --gguf runs/ft-v1/model-f16.gguf --name qwen2.5-coder-ft:1.5b-v1 \\
        --base-model qwen2.5-coder:1.5b --manifest runs/ft-v1/serve-manifest.json

Read specs/001-qcircuit-agent/training-handoff.md. The `create` path is the one the sandbox round-trip was
meant to prove and has NOT yet been exercised end to end; the API calls follow Ollama's documented
/api/blobs and /api/create. If it fails, the error text is printed whole.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

QUANTIZE = "q4_K_M"  # an identity field of the served model: recorded in the manifest, never defaulted silently


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def call(method: str, url: str, body: bytes | None = None, headers: dict | None = None, timeout: int = 3600):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def merge(args: argparse.Namespace) -> None:
    """Merge into the UNQUANTISED base (bf16, on CPU), never into the 4-bit one: the adapter was trained
    against the dequantised NF4 weights, and merging into the original weights is the standard, slightly
    lossy choice; merging into a quantised copy would add a second rounding."""
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    base = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16, device_map="cpu")
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    merged.save_pretrained(args.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base).save_pretrained(args.out)
    print("merged ->", args.out)


def create(args: argparse.Namespace) -> None:
    host = (args.host or os.environ.get("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
    version = json.loads(call("GET", f"{host}/api/version")[1])["version"]
    print("server", host, "version", version)
    if args.expect_version and version != args.expect_version:
        sys.exit(f"server is {version}, expected {args.expect_version}. Quantisation is done by the server on "
                 "create, so the build that creates the model is part of its identity. Not creating.")

    digest = "sha256:" + sha256_file(args.gguf)
    status, _ = call("HEAD", f"{host}/api/blobs/{digest}")
    if status != 200:
        status, body = call("POST", f"{host}/api/blobs/{digest}", args.gguf.read_bytes())
        if status not in (200, 201):
            sys.exit(f"blob upload failed: {status} {body.decode(errors='replace')}")
    print("blob", digest)

    # The template of the base is copied, not retyped: the chat format used in training is the base's.
    status, body = call("POST", f"{host}/api/show", json.dumps({"model": args.base_model}).encode())
    if status != 200:
        sys.exit(f"cannot read the base model {args.base_model}: {status} {body.decode(errors='replace')}")
    shown = json.loads(body)
    payload = {"model": args.name, "files": {args.gguf.name: digest}, "template": shown["template"],
               "stream": False}
    if not args.quantized_by:
        # Ollama 0.40.15 refuses this for GGUF ("create-time quantization is only supported for safetensors
        # imports"), and its safetensors path offers int4/int8/nvfp4/mxfp4/mxfp8, not q4_K_M. On such a server,
        # quantise with llama.cpp's llama-quantize first and pass --quantized-by.
        payload["quantize"] = QUANTIZE
    status, body = call("POST", f"{host}/api/create", json.dumps(payload).encode())
    if status != 200:
        sys.exit(f"create failed: {status} {body.decode(errors='replace')}")
    print("create:", body.decode()[:300])

    tags = json.loads(call("GET", f"{host}/api/tags")[1])["models"]
    mine = next((m for m in tags if m["name"] == args.name), None)
    base = next((m for m in tags if m["name"] == args.base_model), None)
    if mine is None:
        sys.exit("created, but not listed in /api/tags")
    manifest = {"name": args.name, "model_digest": mine["digest"], "base_model": args.base_model,
                "base_digest": base["digest"] if base else None, "quantize": QUANTIZE,
                "gguf_sha256": digest, "server_version": version,
                "quantized_by": args.quantized_by or f"ollama {version} (on create)",
                "quantization_level_reported": json.loads(call(
                    "POST", f"{host}/api/show", json.dumps({"model": args.name}).encode())[1])["details"].get(
                    "quantization_level"),
                "template_copied_from": args.base_model}
    args.manifest.write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest, indent=1))
    if base and mine["digest"] == base["digest"]:
        sys.exit("the new model has the SAME digest as the base: nothing was served from the adapter")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("merge")
    m.add_argument("--adapter", type=Path, required=True)
    m.add_argument("--out", type=Path, required=True)
    m.add_argument("--base", default="Qwen/Qwen2.5-Coder-1.5B-Instruct")
    c = sub.add_parser("create")
    c.add_argument("--gguf", type=Path, required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--base-model", default="qwen2.5-coder:1.5b")
    c.add_argument("--manifest", type=Path, required=True)
    c.add_argument("--host")
    c.add_argument("--expect-version", default="0.40.8", help="the pinned build; pass '' to skip (throwaway only)")
    c.add_argument("--quantized-by", default="",
                   help="the GGUF is ALREADY q4_K_M: name the tool and build that did it (recorded in the "
                        "manifest); the server is then not asked to quantise")
    args = ap.parse_args()
    {"merge": merge, "create": create}[args.cmd](args)


if __name__ == "__main__":
    main()
