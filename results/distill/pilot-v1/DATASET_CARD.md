# pilot-v1: dataset card

**What this is.** The RECORD of the first live run of the distillation pipeline
(4 families x 20 statements, one teacher, one sample each). It answers one
question, "does the pipeline work end to end", and nothing else. It is **not
training data**, and must not be exported as such, for reasons independent of its
irregularities:

* family 2 (modular adder) was cut from the pilot;
* families 1 (permutations), 3 (graph states) and 4 (random Pauli energy) have
  recorded adjacency with the held-out slice (`specs/001-qcircuit-agent/distill-pilot-families.md`);
* the teacher's completion headroom was raised afterwards (12,000 -> 32,000),
  which is part of the teacher's identity, so a training set from this teacher is a
  new dataset version.

**Teacher.** `deepseek/deepseek-v4.1-flash-1017` (canonical
`deepseek/deepseek-v4.1-flash-20261017`), reasoning effort high, temperature 1.0,
top_p 1.0, `provider.enforce_distillable_text: true`, headroom 12,000 (see
`dataset_meta.json`). Serving model equalled the requested id on all 80 paid calls.

**This record is annotated, not cleaned.** A cleaned record of an irregular run
is worse than an annotated one. The irregularities, none of them removed:

1. **Two stretches of one run.** The first invocation was interrupted by the
   operator after 53 records, when ten energy statements had hit sandbox timeouts;
   it was resumed twice (the second time after a fix to recognise the older
   record form). `records.jsonl` is append-only and shows all three stretches.
2. **Eleven statements were checked twice.** Their first record is an
   infrastructure failure: the sandbox timed out at 60 s, and the cascade labelled
   the timeout `SyntaxError` (recorded here as `static_failed:SyntaxError` with
   message `timeout after 60s`; ten of the eleven are energy statements). Cause:
   sandbox workers were FORKED from an orchestrator that had already used
   `SparsePauliOp.to_matrix()`; the generated code called the same function and
   hung. Their second record is a re-check of the SAME teacher response, answered
   from the response cache (cost 0, `cost.source: cache`), and carries
   `retry_of_infrastructure_failure` with the original call's cost and tokens.
3. **One record has a superseded reason code.** One energy response ended with
   `finish_reason: length` (16,096 tokens, all reasoning, empty visible text) and
   is recorded as `static_failed:SyntaxError`; there was no code, hence no syntax
   error. Current code would record `truncated:finish_reason_length`.
4. **`summary.json` covers only the last invocation** (11 re-checks). The figures
   for the whole run are in `report.json`.
5. **`dataset_meta.json` records the FIRST estimate** and the spend authorization
   ($0.36 ceiling, `--authorize-spend 0.36`).

**How to read it.** A statement's verdict is its LATEST record. Its cost is the
record whose `cost.source` is not `cache`. `scripts/distill_report.py` does both
(`report.json`): 76 of 80 accepted; actual spend $0.0703 against the $0.12 registered
estimate; 113,752 of 121,389 output tokens were reasoning; 11 serving providers.
`records.jsonl` also holds the responses and the executed code, so the examples can
be re-judged by anyone.

**Not covered by the filter.** The oracle checks correctness only. A provider running
a more aggressive quantisation would produce correct but poor code, and every
example carries its serving provider (`provenance.derived.served_provider`) so one
provider's examples can be excluded afterwards.
