from app.models.base import Base
from app.models.evidence import (
    AuditReport,
    ClaimVerification,
    ExecutionArtifact,
    ExecutionClaim,
    ExecutionReasoning,
)
from app.models.execution import Execution, ExecutionBug, ExecutionStep
from app.models.meta import (
    Attachment,
    AuditEvent,
    CodeTracker,
    CustomField,
    CustomFieldValue,
    Inventory,
    IssueTracker,
    Plugin,
    ProjectIntegration,
    ReqMgrSystem,
    TestCaseKeyword,
    TextTemplate,
)
from app.models.plan import (
    Build,
    Milestone,
    RiskAssessment,
    TestPlan,
    TestPlanCase,
    TestPlanPlatform,
)
from app.models.requirement import (
    ReqCoverage,
    ReqRelation,
    ReqSpec,
    Requirement,
    ReqVersion,
)
from app.models.structure import Keyword, Platform, Project, TestSuite
from app.models.testcase import (
    TestCase,
    TestCaseRelation,
    TestCaseScriptLink,
    TestCaseVersion,
    TestStep,
)
from app.models.user import (
    Assignment,
    Permission,
    Role,
    RolePermission,
    User,
    UserPlanRole,
    UserProjectRole,
)

# All models are re-exported so importing app.models registers every table on
# Base.metadata (required by Alembic autogenerate and create_all). Listing them
# in __all__ also marks the imports as used for linters.
__all__ = [
    "Base",
    "Keyword",
    "Platform",
    "Project",
    "TestSuite",
    "Assignment",
    "Permission",
    "Role",
    "RolePermission",
    "User",
    "UserPlanRole",
    "UserProjectRole",
    "TestCase",
    "TestCaseRelation",
    "TestCaseScriptLink",
    "TestCaseVersion",
    "TestStep",
    "Build",
    "Milestone",
    "RiskAssessment",
    "TestPlan",
    "TestPlanCase",
    "TestPlanPlatform",
    "Execution",
    "ExecutionBug",
    "ExecutionStep",
    "AuditReport",
    "ClaimVerification",
    "ExecutionArtifact",
    "ExecutionClaim",
    "ExecutionReasoning",
    "ReqCoverage",
    "ReqRelation",
    "ReqSpec",
    "ReqVersion",
    "Requirement",
    "Attachment",
    "AuditEvent",
    "CodeTracker",
    "CustomField",
    "CustomFieldValue",
    "Inventory",
    "IssueTracker",
    "Plugin",
    "ProjectIntegration",
    "ReqMgrSystem",
    "TestCaseKeyword",
    "TextTemplate",
]
