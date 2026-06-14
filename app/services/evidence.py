from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.models.evidence import (
    AuditReport,
    ClaimVerification,
    ExecutionArtifact,
    ExecutionClaim,
    ExecutionReasoning,
)
from app.models.execution import Execution
from app.models.testcase import TestCaseVersion, TestStep
from app.schemas.evidence import CaseEvaluation
from app.services.errors import NotFound


async def record_claims_and_reasoning(
    session: AsyncSession,
    execution_id: int,
    claims: list[str],
    reasoning: dict | None,
    agent_model: str | None,
    session_id: str | None,
) -> None:
    """Persist claims + reasoning for an execution. Does NOT commit (caller owns tx)."""
    for claim_text in claims:
        session.add(ExecutionClaim(execution_id=execution_id, claim_text=claim_text))
    if reasoning is not None or agent_model is not None:
        session.add(
            ExecutionReasoning(
                execution_id=execution_id,
                reasoning=reasoning,
                agent_model=agent_model,
                agent_session_id=session_id,
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
        # project scoping resolves through the plan; left to plan_id for Phase 2b
    stmt = stmt.order_by(ExecutionClaim.id)
    return list((await session.execute(stmt)).scalars().all())


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
