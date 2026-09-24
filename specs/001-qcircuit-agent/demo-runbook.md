# Demo runbook (US6)

Everything below was rehearsed against the containerized stack. Read the
caveats before quoting a number.

---

## From nothing to a working page (Windows)

Once:

```powershell
cd D:\Projects\Quantum-RAG
ollama pull qwen2.5-coder:7b
docker compose build app            # ~10 min; REQUIRED again after matplotlib was added
docker compose up -d
docker compose exec app make index  # ~15 min, populates Qdrant
```

Every session:

```powershell
docker compose up -d
curl http://localhost:8000/api/health
```

Expect `{"qdrant":"1020 documents","ollama":"qwen2.5-coder:7b"}`. If Ollama
reads *unreachable*, the health message names the URL it tried and the usual
cause. Then open <http://localhost:8000>.

### The warm-up run — AFTER the stack is up, immediately before demoing

Order matters and the reason is not obvious.

1. `docker compose up -d` — starts the app and Qdrant. It does **not** touch
   Ollama, which runs on the host, so the model is still unloaded.
2. Open the page and run **any** prompt once. Discard the result.
3. Demo.

The first generation after a model load can take a different number of
attempts than later ones (F19: engine state affects output, and the suite's
determinism protocol is deliberately NOT applied in the UI, because unloading
the model before every run would add a reload to each one).

The warm-up holds: the client sends `keep_alive=60m`, so once warmed the model
stays resident for an hour. Warming up an hour early is the same as not
warming up at all.

---

## Timings here are NOT performance numbers

**Every rehearsed timing below benefited from a warm response cache.** The
demo machine will too, once a prompt has been run — which is exactly what the
warm-up does. But the numbers are not representative of generation:

- cached replay: **~0.1 s**
- genuine generation: **~2.5 s to ~28 s** depending on how many attempts run

Do not cite 2.3 s as system performance. If asked how fast it is, the honest
answer is that a task takes seconds to tens of seconds depending on how many
repair attempts it needs, and that the reference suite's 360 runs took
**3 h 26 min cold**, which is the citable figure.

---

## The five scenarios

Open with **4**. It is the thesis in one view.

| # | prompt | assertions | what it shows |
|---|---|---|---|
| 1 | *A 2-qubit circuit that puts both qubits in superposition using Hadamard gates.* | `PROBABILITY(\|00>) ~= 0.25`, `PROBABILITY(\|11>) ~= 0.25`, `GATES_SUBSET_OF({"h"})` | converges and **VERIFIES** — US3 doing the work, since the UI has no reference oracle |
| 2 | *A 3-qubit quantum Fourier transform with the final swap gates.* | *(none)* | MAX_ITER at 5/5, the repair loop visible, honest failure. **No diagram** — nothing compiled, so there is no circuit to draw. Say that out loud; it looks like a bug otherwise |
| 3 | *A 2-qubit Bell state: apply a Hadamard to qubit 0, then a CNOT from qubit 0 to qubit 1.* | `PROBABILITY(\|00>) ~= 0.5`, `PROBABILITY(\|11>) ~= 0.5` | assertions catch a real error: the histogram shows uniform 25%, not 50/50 |
| 4 | *A 2-qubit Bell state: apply a Hadamard to qubit 0, then a CNOT from qubit 0 to qubit 1.* | *(none)* | **NOT VERIFIED — nothing checked.** Executed yes, transpiled yes, and the verdict still says nothing established correctness |
| 5 | *A 2-qubit circuit that applies a Hadamard gate to both qubits.* | *(none)* | plausible but **inert**: produces `qc.ch(0, 1)`, a controlled-H with the control in `\|0>`. Reads fine, does nothing, exposed by `\|00> 100%` in one line |

### 6 — the on-ramp (observe → draft → check)

Run **4**, then in the distribution panel click **use as assertion** on each
outcome, then **Check this circuit**.

This demonstrates `/api/check`: the assertions are evaluated against the
circuit already on screen — no model, nothing regenerated, instant.

**Narrate the warning that appears.** When every assertion was auto-drafted
from that circuit's own output, the check passes *by construction* and the
interface says so. Drafting writes an assertion; only the user can decide it
is the one they wanted. Edit one to state intent (e.g. change 0.25 to 0.5 for
a real Bell state) and check again — now it means something, and for scenario
4's circuit it fails.

That sequence is the strongest few minutes available: it shows the product
knowing the difference between verifying something and restating it.

---

## Off-script requests

Near certain, and worth expecting rather than reacting to.

**"Try a W state"** — measured, uncached:

```
A 3-qubit W state: an equal superposition of |001>, |010> and |100>.
→ completed_unverified, 1 attempt, 5.9 s
→ distribution: |000> 12%, |001> 12%, |010> 12%, |011> 12%, |100> 12% …
```

It does **not** fail loudly and it is **not** slow. It produces a plausible
wrong circuit — Hadamards on all three qubits, a uniform 8-way superposition —
and completes as `completed_unverified`. That is the honest outcome and a good
moment: the histogram shows 8 outcomes at 12% where a W state has 3 at 33%,
and the verdict says nothing was verified. The failure is visible in one
glance without the system ever claiming success.

If asked why it didn't just get it right: the generator is a 7B local model,
and the measured success rate over the reference suite is 1.7%. The product's
claim is not that generation is reliable — it is that you are told precisely
what was and was not established.

**Anything above 12 qubits** shows no diagram, with a stated reason. Same for
circuits over 120 operations.

**A wrong ket width** (e.g. `|11>` with the qubit count set to 3) is refused
by the parser with the width named. That is deliberate — no implicit padding —
and it is worth showing on purpose if the question comes up.

---

## What to avoid claiming

- Do not present the distribution as a verdict. It is descriptive; the
  guarantee card is evaluative. They are visually separate for that reason.
- Do not describe a self-drafted check as verification of correctness.
- Do not quote UI timings as performance (see above).
- `verified@1 = 0.0%` over 341 clean runs is real and citable. Small non-zero
  deltas in the project's history are not (see "Threats to validity").
