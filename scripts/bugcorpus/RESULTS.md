# STAGED bug-corpus recall results (project BUGCORPUS #17)

Pipeline: Subagent A wrote 20 originals; Subagent B wrote 10 recurrences (blind to A);
30/30 embedded via REST→embedding path; SQL produced id-level cosine rankings;
a SEPARATE checker agent scored from ids+frozen-labels only (no text).

## Raw numbers (checker)
- recall@1 = recall@3 = recall@5 = **10/10 = 1.000**; MRR = 1.000 (every true prior at rank 1)
- Inversions: **0**. Near-miss (gap<0.05): **R10 only** (O20=0.670 vs O8=0.673, gap 0.003).
- True-prior distance: mean 0.375, min 0.251 (R1), max 0.670 (R10).
- Nearest-distractor distance: mean 0.517. Same-family nearest distractor: 6/10.

| Q | truth | true dist | nearest distractor | gap |
|---|---|---|---|---|
| R1 | O1 | 0.251 | O2 0.320 | −0.069 |
| R2 | O4 | 0.428 | O5 0.581 | −0.153 |
| R3 | O7 | 0.352 | O14 0.494 | −0.142 |
| R4 | O10 | 0.313 | O11 0.394 | −0.081 |
| R5 | O11 | 0.292 | O3 0.458 | −0.166 |
| R6 | O13 | 0.379 | O14 0.560 | −0.181 |
| R7 | O14 | 0.335 | O13 0.618 | −0.283 |
| R8 | O16 | 0.369 | O3 0.588 | −0.219 |
| R9 | O18 | 0.364 | O17 0.487 | −0.123 |
| R10 | O20 | 0.670 | O8 0.673 | −0.003 |

## Pre-registered prediction (committed before results, DESIGN.md)
recall@1 ≈ 60%, recall@5 ≈ 80–90%, ≥2 inversions. → ACTUAL beat all three. Overshoot = flag.

## Interpretation (STAGED — recall, not base rate)
POSITIVE: when failure reasoning is distinct + reasoning-rich, semantic retrieval cleanly
recovers the true prior over same-family distractors. The retrieval *math* is sound; the
mechanism is not the bottleneck.

EASIER THAN REAL DATA (why 100% is a ceiling, not production):
1. 30 items — no distance compression from scale (real corpora: 1000s).
2. zero boilerplate — real L33T was 45% infra-boilerplate that collapsed similarity.
3. every note clean/distinct/well-formed — real agent notes are terse, sloppy, heterogeneous.
Calibration: unlike L33T (false 0.166 < genuine 0.216), here every true pair is strictly
closer than its distractor — a cleaner regime than reality.

CANARY: R10 near-tie (gap 0.003, None-deref vs empty-password, both "null/empty") shows even
in a clean corpus a cross-family distractor nearly ties. At scale these become inversions →
precision degradation is the real open risk.

STILL UNANSWERED: base rate (set by fiat here) — how often a real task has a prior at all.

## FOLLOW-UP TEST 2 — symptom→note + silence (the realistic query form)
Doer C wrote 15 SYMPTOM-ONLY queries (10 RS = real priors, 5 N = no prior in corpus),
blind to A/B/corpus. Ranked vs unchanged 20 O. Separate checker scored.

Symptom-only RS (vs note↔note in parens):
- recall@1 = 5/10 = 0.50  (was 1.00)  — true prior usually NOT #1 once fix-text removed
- recall@3 = 9/10 = 0.90 ; recall@5 = 10/10 = 1.00 ; MRR = 0.725  (was 1.00)
- inversions = 5/10: RS2,RS4,RS5,RS9,RS10 (was 0). 3 same-family, 2 cross-family.

SILENCE TEST (decisive): NO distance threshold separates real priors from no-prior noise.
- N (no-prior) top-hit distances 0.453–0.520 ALL fall inside RS true-prior range 0.314–0.671.
- Reject all 5 N → need T<0.453 → keeps only 3/10 genuine (30% recall).
- T admitting 80% genuine (0.515) → 4/5 N fire as FALSE POSITIVES.

## CONCLUSION (STAGED)
- Retrieval-as-RANKER works: top-3/top-5 recall strong (90%/100%) even symptom-only, IF a prior exists.
- Retrieval-as-GATE fails: no usable confidence signal — cannot decide WHETHER a prior exists.
- Since real base rate of "prior exists" ≈ 0 (L33T), gating is the critical function, and it's
  the one that doesn't work on distance alone. The scout must retrieve top-K then LLM-JUDGE each
  candidate every task. The reasoning agent is NECESSARY (not optional) and runs per-task.
- Economic question (unanswered): paying per-task LLM judgment to almost always conclude
  "no relevant prior" — worth it only if real base rate is meaningfully > 0. Unmeasured on real dev.
