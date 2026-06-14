import datetime as dt

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Role(Base, TimestampMixin):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str | None] = mapped_column(Text)


class Permission(Base):
    __tablename__ = "permissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column(String(128), unique=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(256))
    email: Mapped[str | None] = mapped_column(String(256))
    first: Mapped[str | None] = mapped_column(String(128))
    last: Mapped[str | None] = mapped_column(String(128))
    role_id: Mapped[int | None] = mapped_column(ForeignKey("roles.id"))
    api_key: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    auth_method: Mapped[str] = mapped_column(String(16), default="db")  # db|ldap|oauth|agent
    agent_model: Mapped[str | None] = mapped_column(String(128))
    notification_config: Mapped[dict | None] = mapped_column(JSONB)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class UserProjectRole(Base):
    __tablename__ = "user_project_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))


class UserPlanRole(Base):
    __tablename__ = "user_plan_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("test_plans.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"))


class Assignment(Base, TimestampMixin):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str | None] = mapped_column(String(32))
    case_id: Mapped[int] = mapped_column(ForeignKey("test_cases.id"))
    plan_id: Mapped[int] = mapped_column(ForeignKey("test_plans.id"))
    build_id: Mapped[int | None] = mapped_column(ForeignKey("builds.id"))
    assignee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    assignee_type: Mapped[str] = mapped_column(String(16))  # human|agent
    deadline: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), default="open")
    assigner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
