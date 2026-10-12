# Batch 1 J1 — independent correction review

Claude accepted Batch 1 with a confirmed operational defect: a successful manual
poll followed by a stale scheduler wake returned HTTP 503 for a refused lease.
The scheduler then incorrectly incremented failures and replaced the persisted
poll deadline with failure backoff. This correction makes deferral distinct and
removes stale scheduler writes from owned collection.

Starting verified origin/main: `00a7ad8b9f1324ac954da93fcc0edfbbdf5a32b1`.
Previously reviewed code freeze: `ec97563956859c73254df3d409db5430f25ae6ed`.
Main-only; no HA, source registry, provider/parser, M1/M2 engine or migration change.

## Correction

- `CollectionDeferred` is an internal exception handled before provider errors.
  It is neither HTTP success nor HTTP failure. Existing fixed deferral logging
  remains; no provider failure event, failure increment or schedule write occurs.
- After deferral the scheduler reloads persisted failure count and the later of
  polling/recovery deadline and current lease expiry. Disabled sources wait their
  normal interval. Past/missing state gets a local minimum interval floor; reload
  failure waits maximum backoff locally without saving or inventing failures.
- An owned poll captures pre-reservation failure state under the poll-row lock.
  Its result uses the existing `next_state` policy, including genuine HTTP
  failures, bounded exponential backoff, jitter and Retry-After. Finalization
  requires the current unexpired token; backoff and lease clearing commit together.
- The automatic live scheduler reloads owned outcomes and never saves over them.
  Manual verification also uses owned finalization. Older owners cannot reset a
  newer owner's success/failure or release its lease. No network work holds a DB
  connection or M1 publication lock.
- Cancellation propagates after shielded failure finalization; process death or
  failed finalization retains the existing conservative recovery reservation.
  Legacy scheduler collectors with explicit save callbacks keep their behavior.
- Manual tool deferral reports `collection_deferred=true`, `http_outcome=null`
  and no new successful collection. Read-only installed inspection is unchanged.
  Existing false historical J1 failure counts are not mass-reset.

## Regression coverage

New J1 tests cover manual success/stale wake, active lease, not-due and disabled
refusals, lease later than backoff, restart recovery, expired lease before/at
authorized recovery, genuine 429/503 and Retry-After, exponential failure counts,
timeout/cancellation, stale owner success/failure, a later manual failure winning
over a stale scheduler success, failed finalization, failed reload and no repeated
immediate wake or stale save. Real database cases use disposable PostGIS, and
provider-shaped responses in these tests are explicitly synthetic offline tests.
They are not installed Unraid or genuine provider collection evidence.

All 471 accepted Batch 1 case identities (including all 446 historical H1 cases)
must remain present and pass without deleting or weakening old tests. The full
validation workflow also runs portable tests, Ruff, compilation, real PostGIS,
full/repeat migrations, restart/failure/backup/restore and existing M1 parity.
Current verified test/evidence receipts will be appended after successful CI.

## Concise Claude review request

Review only the J1 delta from the starting SHA. Verify that every ownership
refusal follows `CollectionDeferred`, reloads persisted deadlines/failures and
cannot become HTTP 503 or overwrite state. Inspect live API/tool wiring, atomic
lease-fenced finalization and scheduler read-only behavior under manual/process
races, disabled sources, recovery deadlines, timeout and genuine Retry-After.
Confirm all 471 old case identities and the 446 H1 subset remain green, migrations
and parity are unchanged, and regression tests exercise the required cases.
Return PASS or actionable required fixes with file/line evidence.

Independent acceptance remains pending. After acceptance the operator will back
up, deploy and verify installed Unraid Core; only then proceed to Batch 2.
The 81-entry scope is unchanged. Full ingestion is NOT COMPLETE. No release,
notification, scoring, HA change or M2 production promotion is authorized here.


## Verified J1 correction receipts

Code/test/tool freeze: `762ab90b9ae3bba232a6a6697ad3f819ad27fbbc`. [Complete CI](https://github.com/Tmatz27/photography-events-core/actions/runs/38215256052) passed.
Artifact `11732376914` downloaded ZIP SHA-256: `34f43c65bbf961f0af4c181603d64b00420b56bd96d0e625cc349ab73fd2fbdb`.
Committed evidence: `docs/evidence/ingestion-j1/receipt.json` and adjacent raw
workflow artifacts; the receipt enumerates all 20 new J1 case identities/hashes.

**491 passed in 82.166s**, zero errors/failures/skips in the
complete real PostgreSQL/PostGIS suite. All **471 accepted Batch 1 identities**
and all **446 historical H1 identities** remain; no old test was edited. The
20 new cases include 4 portable and 16 database cases. Local portable verification:
164 passed, 327 expected DB/POSIX/oracle skips. CI portable: 169 passed, 322
expected database skips, followed by the complete real database suite. Ruff
and compilation also passed.

Both independent legacy recaptures remained byte-identical; 15 fixture cases,
nine pipeline cases and 18,000 evaluator comparisons, zero mismatches. Full/repeat
migrations, failure injection/restart and actual backup/restore passed; schema
remains 0009 and nonempty collector state/provenance survived restore. All accepted
privacy/safety/M2 isolation/quota/lifecycle cases remain green. No migrations,
provider contracts/parsers/storage, source inventory or phenomenon engine changed.

The workflow's genuine live collection receipt is separate from synthetic J1
test responses and is preserved verbatim. It is disposable CI database evidence,
not installed Unraid acceptance; per-source failures/empty data/native staleness
must be read truthfully from that receipt. The user will back up and inspect
installed Core after independent correction acceptance. No Unraid connection or
deployment was performed. The 81-entry scope remains; full ingestion NOT COMPLETE.

J1 implementation and CI = READY FOR CLAUDE CORRECTION REVIEW.
Independent acceptance / installed backup and verification / Batch 2 = PENDING.
Production release / promotion / notifications = NO.
