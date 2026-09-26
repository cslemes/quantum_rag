"""Pod control for the RunPod arm (report-notes.md, "braço RunPod").

    python scripts/runpod_arm.py create --gpu "NVIDIA RTX A5000"
    python scripts/runpod_arm.py status <pod_id>
    python scripts/runpod_arm.py terminate <pod_id>

Only Ollama runs in the pod, bound to localhost; nothing is exposed over
HTTP. The only open port is SSH (22/tcp, key auth with the public key in
~/.ssh/runpod_arm.pub), used for a tunnel from the local app — RunPod's HTTP
proxy is not authenticated and Ollama has none of its own.

Reads RUNPOD_API_KEY from .env. Prints JSON; never prints the key.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

API = "https://rest.runpod.io/v1"
IMAGE = "runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04"  # sshd + PUBLIC_KEY support
OLLAMA_VERSION = "0.34.4"  # the local server's version: parity with the local arm


def _client() -> httpx.Client:
    key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("RUNPOD_API_KEY")
    if not key:
        sys.exit("RUNPOD_API_KEY is not set in .env")
    return httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}"}, timeout=60)


def create(gpu: str) -> dict:
    public_key = (Path.home() / ".ssh" / "runpod_arm.pub").read_text().strip()
    body = {
        "name": "qcagent-runpod-arm",
        "imageName": IMAGE,
        "cloudType": "SECURE",
        "gpuTypeIds": [gpu],
        "gpuCount": 1,
        "containerDiskInGb": 60,
        "volumeInGb": 0,
        "ports": ["22/tcp"],
        "supportPublicIp": True,
        "env": {"PUBLIC_KEY": public_key},
    }
    response = _client().post("/pods", json=body)
    if response.is_error:
        sys.exit(f"create failed: HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


def status(pod_id: str) -> dict:
    response = _client().get(f"/pods/{pod_id}")
    response.raise_for_status()
    return response.json()


def terminate(pod_id: str) -> str:
    response = _client().delete(f"/pods/{pod_id}")
    if response.is_error:
        sys.exit(f"terminate failed: HTTP {response.status_code}: {response.text[:300]}")
    return "terminated"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--gpu", required=True)
    for name in ("status", "terminate"):
        sub.add_parser(name).add_argument("pod_id")
    args = parser.parse_args()
    if args.cmd == "create":
        print(json.dumps(create(args.gpu), indent=1))
    elif args.cmd == "status":
        print(json.dumps(status(args.pod_id), indent=1))
    else:
        print(terminate(args.pod_id))


if __name__ == "__main__":
    main()
