# Annotation to cache_summary.json (added 2026-10-24; the JSON itself is unchanged)

`cache_summary.json` in this directory reads `PARTLY WARM` (112/1,064 hits).
That label is a product of the summary as built on the day of run G, which
counted every hit alike. It is not the run's status. **Run G was cold**: none
of the 112 hits was on an entry that pre-dated the run. 12 were on entries the
protocol check wrote moments earlier (dj_constant_4q 9, qaoa_maxcut_4q_perturbed 3)
and 100 were prompts repeated within a task run. The derivation is by file
count (988 cache files existed before G, all run E's, in the old key format;
988 were written during G = 952 misses + 36 protocol-check calls; 1,064 − 112 =
952) and is in section 5.3 of the chapter 5 and in report-notes.md. Chapter 5
governs; this label does not.

The summary code was changed afterwards (commit 6e311d8) to report pre-existing
hits and self-hits separately. Records of runs A–G predate that and carry no
split, so re-summarising them would still print PARTLY WARM.

sha256 of cache_summary.json when annotated:
e0df6f5391503796d038e0798257fe9385e89eb9782e7484e41089eae5ad7568
