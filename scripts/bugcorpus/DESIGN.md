# STAGED bug corpus — recall@k / precision harness (NOT a base-rate test)

**What this proves:** given a genuine prior exists, does semantic retrieval over failure-reasoning
text surface it above same-family false neighbors, on realistic dev-failure text.
**What it does NOT prove:** the real-world base rate (set by fiat here). Label all results STAGED.

Calibration target from real L33T data: a *false* neighbor sat CLOSER (0.166) than a *genuine*
pair (0.216). Corpus is only valid if its distractors are that hard. Genuine match zone ≈ 0.24–0.34.

## 6 vocabulary-colliding families (20 originals O1–O20)

**F1 money** (total, amount, cents, price, tax, invoice)
- O1 [RECURS] integer truncation: `int(price*qty)` drops fractional cents; order total short.
- O2 float accumulation: summing taxes as floats → 19.999999 vs 20.00 assertion fail.
- O3 integer overflow: invoice seq stored int32, wraps negative past 2.1B.

**F2 cache** (cache, stale, invalidate, key, ttl)
- O4 [RECURS] missing invalidation: profile cache not cleared on update; stale name served.
- O5 cache race/stampede: concurrent misses recompute; lost write-through update.
- O6 key collision: cache key omits tenant_id; tenant A served tenant B's dashboard.

**F3 auth** (auth, login, session, token, password, user)
- O7 [RECURS] SQL injection: login query string-formats username; `' OR '1'='1` bypass.
- O8 empty-password bypass: `password == user.pw` true when both empty/None.
- O9 session fixation: session id not rotated after login.

**F4 concurrency** (lock, thread, concurrent, race, deadlock, pool)
- O10 [RECURS] deadlock: order locks (orders,payments); refund locks (payments,orders); inversion.
- O11 [RECURS] non-atomic counter: `c=get(); set(c+1)` race loses increments.
- O12 pool exhaustion: connections not returned on exception path; pool drained, timeouts.

**F5 query** (query, rows, db, select, index, page)
- O13 [RECURS] N+1: serializing orders queries customer per row; 500 queries/request.
- O14 [RECURS] missing index: WHERE on unindexed column → full scan timeout.
- O15 pagination off-by-one: OFFSET uses page*size not (page-1)*size; rows skipped.

**F6 input/parse/null** (parse, null, none, type, encode, datetime)
- O16 [RECURS] timezone: naive datetime across DST; scheduled job fires 1h off.
- O17 encoding: bytes vs str; `b'..'.startswith('..')` TypeError on UTF-8.
- O18 [RECURS] type coercion: env "false" is truthy string → flag always on.
- O19 slice off-by-one: `s[:n-1]` drops last char of fixed-width field.
- O20 [RECURS] None deref: optional field accessed without guard → AttributeError.

## 10 recurrences (R1–R10) — fresh module, SAME root cause, authored BLIND by Subagent B

| Rk | new scenario (given to B) | FROZEN true prior |
|----|---------------------------|-------------------|
| R1 | payroll: `int(hours*rate)` truncates partial-hour cents; paystub short | **O1** |
| R2 | product catalog: price cache not invalidated on change; checkout old price | **O4** |
| R3 | search endpoint: SQL filter f-string from `q`; `'; DROP` injectable | **O7** |
| R4 | inventory↔shipping lock-order inversion deadlock | **O10** |
| R5 | rate limiter: `hits=redis.get(); set(hits+1)` non-atomic, over-admits | **O11** |
| R6 | report builder loops invoices, queries line-items per invoice (N+1) | **O13** |
| R7 | audit-log search filters unindexed actor_id; sequential scan timeout | **O14** |
| R8 | log correlation compares naive UTC vs local; events misordered across DST | **O16** |
| R9 | config flag "0"/"no" treated truthy → debug enabled in prod | **O18** |
| R10| optional `address.zip` on user with no address → NoneType attr error | **O20** |

Singletons (no true pair; pure distractors): O2,O3,O5,O6,O8,O9,O12,O15,O17,O19.

## Pre-registered expectations (committed BEFORE any result)
- recall@1 ≈ 60% (6/10 true prior is the single nearest)
- recall@5 ≈ 80–90%
- ≥2 of 10 queries will have a same-family distractor ranked ABOVE the true prior
  (mirroring L33T's 0.166<0.216 inversion); most likely in F6 (input, most homogeneous)
  and F4 (R4/R5 cross-contaminate — both deadlock/race).
- F1 money (R1→O1 truncation vs O2 float vs O3 overflow) ≈ coin-flip on recall@1.
- Mean true-pair distance predicted ≈ 0.30; nearest distractor predicted ≈ 0.40.

## FOLLOW-UP TEST 2 — symptom→note (frozen before results)
Doer C (blind to A/B/corpus) writes SYMPTOM-ONLY queries: error/observation only, no
root cause, no fix. Ranked against the unchanged 20 O candidates.
- True-prior labels (same as before): RS1→O1, RS2→O4, RS3→O7, RS4→O10, RS5→O11,
  RS6→O13, RS7→O14, RS8→O16, RS9→O18, RS10→O20.
- NO-PRIOR queries (silence expected, share family vocab, root cause absent from corpus):
  N1 regex-backtracking-timeout, N2 missing-await-coroutine, N3 CSRF, N4 unbounded-memory-leak,
  N5 wrong-HTTP-status → label NONE.
Pre-registered prediction (committed): symptom-only recall@1 DROPS to ~50–70% (vs 100% note↔note);
no-prior top-hit distances OVERLAP the genuine RS range → no clean silence threshold.

## Protocol
1. Labels above are FROZEN. Subagent A writes O1–O20 text (blind to which recur).
   Subagent B writes R1–R10 text from the "new scenario" column ONLY (blind to A's text,
   never told "recurrence of X"). Mapping held here, not given to subagents.
2. Insert into isolated project BUGCORPUS (prefix BUGS), status=fail, embed via app.embeddings.
3. recall@k computed mechanically against frozen R→O map. No post-hoc genuineness judgment.
4. Report raw vs L33T calibration: is any false neighbor closer than its true pair?
