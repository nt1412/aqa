import re

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import embeddings, storage
from app.models.evidence import (
    AuditReport,
    ClaimVerification,
    ExecutionArtifact,
    ExecutionClaim,
    ExecutionReasoning,
)
from app.models.execution import Execution, ExecutionStep
from app.models.testcase import TestCase, TestCaseVersion, TestStep
from app.schemas.evidence import (
    ArtifactOut,
    CaseEvaluation,
    EvidenceBundle,
    EvidenceExecution,
    FailureContext,
    FailureExecution,
    RecurrenceHit,
    SimilarFailure,
    StepFailure,
)
from app.services.errors import NotFound

# Statuses that count as failures for the self-correction loop (similar-failure
# search + failure-context recent executions). Passing runs are excluded.
_FAILURE_STATUSES = ("fail", "blocked")

_WORD = re.compile(r"[a-z0-9]{3,}")


def _tsquery_terms(text: str) -> list[str]:
    """Significant lexemes from free text, de-duped, order-preserving."""
    return list(dict.fromkeys(_WORD.findall((text or "").lower())))


async def search_recurrences(
    session: AsyncSession,
    query_text: str,
    project_id: int | None = None,
    n: int = 5,
    min_terms: int = 2,
) -> list[RecurrenceHit]:
    """Keyword/FTS retrieval over cleaned reasoning text, with a silence gate.

    A hit must share at least ``min_terms`` DISTINCT query lexemes with the prior
    (capped at how many the query has) — so a single common word ("timeout")
    shared with an otherwise-unrelated failure does NOT register. No qualifying
    prior -> empty result ('no known prior', a real signal). Includes BOTH pass
    and fail rows (a fix is often documented in a passing run)."""
    terms = _tsquery_terms(query_text)
    if not terms:
        return []
    required = min(min_terms, len(terms))
    tsvector = func.to_tsvector("english", ExecutionReasoning.search_text)
    rank = func.ts_rank_cd(tsvector, func.to_tsquery("english", " | ".join(terms)))
    # count of DISTINCT query terms whose lexeme appears in this row's text
    match_count = None
    for term in terms:
        hit = cast(tsvector.op("@@")(func.to_tsquery("english", term)), Integer)
        match_count = hit if match_count is None else match_count + hit
    stmt = (
        select(Execution.id, TestCaseVersion.case_id, Execution.status, rank.label("rank"))
        .select_from(ExecutionReasoning)
        .join(Execution, Execution.id == ExecutionReasoning.execution_id)
        .join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
        .where(ExecutionReasoning.search_text.is_not(None), match_count >= required)
        .order_by(match_count.desc(), rank.desc())
        .limit(n)
    )
    if project_id is not None:
        stmt = stmt.join(TestCase, TestCase.id == TestCaseVersion.case_id).where(
            TestCase.project_id == project_id
        )
    rows = (await session.execute(stmt)).all()
    return [
        RecurrenceHit(execution_id=r.id, case_id=r.case_id, status=r.status, rank=float(r.rank))
        for r in rows
    ]


async def record_claims_and_reasoning(
    session: AsyncSession,
    execution_id: int,
    claims: list[str],
    reasoning: dict | None,
    agent_model: str | None,
    session_id: str | None,
    notes: str | None = None,
) -> None:
    """Persist claims + reasoning (+ best-effort embedding). Does NOT commit."""
    for claim_text in claims:
        session.add(ExecutionClaim(execution_id=execution_id, claim_text=claim_text))

    has_reasoning_row = reasoning is not None or agent_model is not None or bool(notes)
    if not has_reasoning_row:
        return

    embed_text = embeddings.embed_text_for(reasoning, notes)
    embedding = None
    if embed_text and embeddings.is_available():
        try:
            embedding = embeddings.embed(embed_text)
        except Exception:
            embedding = None  # best-effort: never fail a run on embedding errors

    session.add(
        ExecutionReasoning(
            execution_id=execution_id,
            reasoning=reasoning,
            agent_model=agent_model,
            agent_session_id=session_id,
            embedding=embedding,
            search_text=embed_text or None,
        )
    )


async def _get_execution(session: AsyncSession, execution_id: int) -> Execution:
    ex = await session.get(Execution, execution_id)
    if ex is None:
        raise NotFound(f"execution {execution_id} not found")
    return ex


async def upload_artifact(
    session: AsyncSession,
    execution_id: int,
    artifact_type: str,
    title: str | None,
    content: bytes,
    mime_type: str | None,
) -> ExecutionArtifact:
    await _get_execution(session, execution_id)
    key = storage.build_key(execution_id, artifact_type, title or artifact_type)
    storage.put_object(key, content, mime_type or "application/octet-stream")
    artifact = ExecutionArtifact(
        execution_id=execution_id,
        artifact_type=artifact_type,
        title=title,
        blob_key=key,
        size=len(content),
        mime_type=mime_type,
    )
    session.add(artifact)
    await session.commit()
    await session.refresh(artifact)
    return artifact


async def list_artifacts(session: AsyncSession, execution_id: int) -> list[ExecutionArtifact]:
    stmt = (
        select(ExecutionArtifact)
        .where(ExecutionArtifact.execution_id == execution_id)
        .order_by(ExecutionArtifact.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_unverified_claims(
    session: AsyncSession, project_id: int | None = None, plan_id: int | None = None
) -> list[ExecutionClaim]:
    """Claims with zero verifications. Optional project/plan scoping via executions."""
    verified_subq = select(ClaimVerification.claim_id).distinct()
    stmt = select(ExecutionClaim).where(ExecutionClaim.id.not_in(verified_subq))
    if project_id is not None or plan_id is not None:
        stmt = stmt.join(Execution, Execution.id == ExecutionClaim.execution_id)
        if plan_id is not None:
            stmt = stmt.where(Execution.plan_id == plan_id)
        if project_id is not None:
            stmt = (
                stmt.join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
                .join(TestCase, TestCase.id == TestCaseVersion.case_id)
                .where(TestCase.project_id == project_id)
            )
    stmt = stmt.order_by(ExecutionClaim.id)
    return list((await session.execute(stmt)).scalars().all())


async def list_claims(
    session: AsyncSession, project_id: int | None = None, plan_id: int | None = None
) -> list[dict]:
    """All claims (optionally scoped) with their latest verdict + verification count.

    Powers the audit board: verdict None => Unverified column; otherwise the
    most recent verdict decides the column (re-verifying overrides, history kept).
    """
    stmt = select(ExecutionClaim)
    if project_id is not None or plan_id is not None:
        stmt = stmt.join(Execution, Execution.id == ExecutionClaim.execution_id)
        if plan_id is not None:
            stmt = stmt.where(Execution.plan_id == plan_id)
        if project_id is not None:
            stmt = (
                stmt.join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
                .join(TestCase, TestCase.id == TestCaseVersion.case_id)
                .where(TestCase.project_id == project_id)
            )
    stmt = stmt.order_by(ExecutionClaim.id)
    claims = list((await session.execute(stmt)).scalars().all())
    if not claims:
        return []

    claim_ids = [c.id for c in claims]
    vrows = (
        await session.execute(
            select(ClaimVerification.claim_id, ClaimVerification.verdict, ClaimVerification.id)
            .where(ClaimVerification.claim_id.in_(claim_ids))
            .order_by(ClaimVerification.id.desc())  # newest first
        )
    ).all()
    latest: dict[int, str] = {}
    counts: dict[int, int] = {}
    for cid, verdict, _vid in vrows:
        counts[cid] = counts.get(cid, 0) + 1
        if cid not in latest:  # first seen is newest
            latest[cid] = verdict

    return [
        {
            "id": c.id,
            "execution_id": c.execution_id,
            "claim_text": c.claim_text,
            "created_at": c.created_at,
            "verification_count": counts.get(c.id, 0),
            "verdict": latest.get(c.id),
        }
        for c in claims
    ]


async def verify_claim(
    session: AsyncSession, claim_id: int, data, auditor_id: int
) -> ClaimVerification:
    claim = await session.get(ExecutionClaim, claim_id)
    if claim is None:
        raise NotFound(f"claim {claim_id} not found")
    verification = ClaimVerification(
        claim_id=claim_id,
        auditor_id=auditor_id,
        verdict=data.verdict,
        reasoning=data.reasoning,
    )
    session.add(verification)
    await session.commit()
    await session.refresh(verification)
    return verification


async def list_verifications(session: AsyncSession, claim_id: int) -> list[ClaimVerification]:
    stmt = (
        select(ClaimVerification)
        .where(ClaimVerification.claim_id == claim_id)
        .order_by(ClaimVerification.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def create_audit_report(session: AsyncSession, data, auditor_id: int) -> AuditReport:
    report = AuditReport(
        entity_type=data.entity_type,
        entity_id=data.entity_id,
        auditor_id=auditor_id,
        findings=data.findings,
        quality_score=data.quality_score,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


async def evaluate_test_case(session: AsyncSession, case_version_id: int) -> CaseEvaluation:
    version = await session.get(TestCaseVersion, case_version_id)
    if version is None:
        raise NotFound(f"test case version {case_version_id} not found")
    step_count = (
        await session.execute(
            select(func.count()).select_from(TestStep).where(TestStep.version_id == case_version_id)
        )
    ).scalar_one()
    exec_stmt = (
        select(Execution)
        .where(Execution.version_id == case_version_id)
        .order_by(Execution.created_at.desc())
    )
    executions_for_version = list((await session.execute(exec_stmt)).scalars().all())
    return CaseEvaluation(
        case_version_id=case_version_id,
        version=version.version,
        summary=version.summary,
        step_count=step_count,
        execution_count=len(executions_for_version),
        last_status=executions_for_version[0].status if executions_for_version else None,
    )


async def get_execution_evidence(session: AsyncSession, case_id: int) -> EvidenceBundle:
    case = await session.get(TestCase, case_id)
    if case is None:
        raise NotFound(f"test case {case_id} not found")
    version_ids = (
        (
            await session.execute(
                select(TestCaseVersion.id).where(TestCaseVersion.case_id == case_id)
            )
        )
        .scalars()
        .all()
    )
    bundle = EvidenceBundle(case_id=case_id, executions=[])
    if not version_ids:
        return bundle
    exec_rows = (
        (
            await session.execute(
                select(Execution)
                .where(Execution.version_id.in_(version_ids))
                .order_by(Execution.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    for ex in exec_rows:
        claim_texts = (
            (
                await session.execute(
                    select(ExecutionClaim.claim_text)
                    .where(ExecutionClaim.execution_id == ex.id)
                    .order_by(ExecutionClaim.id)
                )
            )
            .scalars()
            .all()
        )
        artifacts = await list_artifacts(session, ex.id)
        bundle.executions.append(
            EvidenceExecution(
                id=ex.id,
                status=ex.status,
                build_id=ex.build_id,
                created_at=ex.created_at,
                claims=list(claim_texts),
                artifacts=[ArtifactOut.model_validate(a) for a in artifacts],
            )
        )
    return bundle


async def get_agent_execution_history(
    session: AsyncSession, agent_id: int, project_id: int | None = None
) -> list[Execution]:
    stmt = select(Execution).where(Execution.tester_id == agent_id)
    if project_id is not None:
        stmt = (
            stmt.join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
            .join(TestCase, TestCase.id == TestCaseVersion.case_id)
            .where(TestCase.project_id == project_id)
        )
    stmt = stmt.order_by(Execution.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def search_similar_failures(
    session: AsyncSession, case_id: int, n: int = 5
) -> list[SimilarFailure]:
    # query vector = most recent embedded FAILURE for this case (anchor on a failure,
    # not a pass — this loop is about finding similar failures to learn from)
    q = (
        select(ExecutionReasoning.embedding)
        .select_from(ExecutionReasoning)
        .join(Execution, Execution.id == ExecutionReasoning.execution_id)
        .join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
        .where(
            TestCaseVersion.case_id == case_id,
            ExecutionReasoning.embedding.is_not(None),
            Execution.status.in_(_FAILURE_STATUSES),
        )
        .order_by(Execution.created_at.desc())
        .limit(1)
    )
    query_vec = (await session.execute(q)).scalars().first()
    if query_vec is None:
        return []

    distance = ExecutionReasoning.embedding.cosine_distance(query_vec)
    stmt = (
        select(Execution.id, TestCaseVersion.case_id, Execution.status, distance.label("distance"))
        .select_from(ExecutionReasoning)
        .join(Execution, Execution.id == ExecutionReasoning.execution_id)
        .join(TestCaseVersion, TestCaseVersion.id == Execution.version_id)
        .where(
            ExecutionReasoning.embedding.is_not(None),
            TestCaseVersion.case_id != case_id,
            Execution.status.in_(_FAILURE_STATUSES),
        )
        .order_by(distance)
        .limit(n)
    )
    rows = (await session.execute(stmt)).all()
    return [
        SimilarFailure(
            execution_id=r.id, case_id=r.case_id, status=r.status, distance=float(r.distance)
        )
        for r in rows
    ]


async def get_failure_context(
    session: AsyncSession, case_id: int, plan_id: int | None = None, last_n: int = 5
) -> FailureContext:
    case = await session.get(TestCase, case_id)
    if case is None:
        raise NotFound(f"test case {case_id} not found")
    version_ids = (
        (
            await session.execute(
                select(TestCaseVersion.id).where(TestCaseVersion.case_id == case_id)
            )
        )
        .scalars()
        .all()
    )

    ctx = FailureContext(case_id=case_id, case_name=case.name)
    if not version_ids:
        return ctx

    exec_stmt = (
        select(Execution)
        .where(
            Execution.version_id.in_(version_ids),
            Execution.status.in_(_FAILURE_STATUSES),
        )
        .order_by(Execution.created_at.desc())
        .limit(last_n)
    )
    if plan_id is not None:
        exec_stmt = exec_stmt.where(Execution.plan_id == plan_id)
    exec_rows = list((await session.execute(exec_stmt)).scalars().all())

    for ex in exec_rows:
        step_fail_rows = (
            (
                await session.execute(
                    select(ExecutionStep)
                    .where(
                        ExecutionStep.execution_id == ex.id,
                        ExecutionStep.status.in_(["fail", "blocked"]),
                    )
                    .order_by(ExecutionStep.id)
                )
            )
            .scalars()
            .all()
        )
        ctx.recent_executions.append(
            FailureExecution(
                execution_id=ex.id,
                status=ex.status,
                notes=ex.notes,
                step_failures=[
                    StepFailure(step_id=sf.step_id, status=sf.status, notes=sf.notes)
                    for sf in step_fail_rows
                ],
            )
        )
        for art in await list_artifacts(session, ex.id):
            ctx.artifacts.append(ArtifactOut.model_validate(art))

    reasoning_rows = (
        (
            await session.execute(
                select(ExecutionReasoning.reasoning)
                .join(Execution, Execution.id == ExecutionReasoning.execution_id)
                .where(
                    Execution.version_id.in_(version_ids),
                    ExecutionReasoning.reasoning.is_not(None),
                )
                .order_by(Execution.created_at.desc())
                .limit(last_n)
            )
        )
        .scalars()
        .all()
    )
    ctx.prior_reasoning = [r for r in reasoning_rows if r is not None]

    # last-green: reasoning of the most-recent PASSING run, surfaced separately so
    # the recency cap above can't bury "why this test was green" (often the fix).
    green_stmt = (
        select(ExecutionReasoning.reasoning)
        .join(Execution, Execution.id == ExecutionReasoning.execution_id)
        .where(
            Execution.version_id.in_(version_ids),
            Execution.status == "pass",
            ExecutionReasoning.reasoning.is_not(None),
        )
        .order_by(Execution.created_at.desc(), Execution.id.desc())
        .limit(1)
    )
    if plan_id is not None:
        green_stmt = green_stmt.where(Execution.plan_id == plan_id)
    ctx.last_green_reasoning = (await session.execute(green_stmt)).scalars().first()

    ctx.similar_failures = await search_similar_failures(session, case_id, n=last_n)
    return ctx
