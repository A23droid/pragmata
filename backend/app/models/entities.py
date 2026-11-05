import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.enums import (
    AgentRole,
    ApprovalDecision,
    ApprovalTarget,
    ChannelType,
    EvidenceType,
    ImplementationStatus,
    InvestigationOutcome,
    IssueStatus,
    ProvenanceType,
    TaskStatus,
    VerificationStatus,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    issues: Mapped[List["Issue"]] = relationship("Issue", back_populates="project", cascade="all, delete-orphan")


class Issue(Base):
    __tablename__ = "issues"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    expected_behavior: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps_attempted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reporter_environment: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, name="issuestatus"),
        default=IssueStatus.RECEIVED,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="issues")
    investigations: Mapped[List["Investigation"]] = relationship("Investigation", back_populates="issue", cascade="all, delete-orphan")
    tasks: Mapped[List["AgentTask"]] = relationship("AgentTask", back_populates="issue", cascade="all, delete-orphan")
    evidence: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="issue", cascade="all, delete-orphan")
    solutions: Mapped[List["Solution"]] = relationship("Solution", back_populates="issue", cascade="all, delete-orphan")
    approvals: Mapped[List["Approval"]] = relationship("Approval", back_populates="issue", cascade="all, delete-orphan")
    implementations: Mapped[List["Implementation"]] = relationship("Implementation", back_populates="issue", cascade="all, delete-orphan")
    verification_runs: Mapped[List["VerificationRun"]] = relationship("VerificationRun", back_populates="issue", cascade="all, delete-orphan")
    conversations: Mapped[List["ConversationReference"]] = relationship("ConversationReference", back_populates="issue", cascade="all, delete-orphan")
    audit_events: Mapped[List["AuditEvent"]] = relationship("AuditEvent", back_populates="issue", cascade="all, delete-orphan")


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    commit_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    environment_details: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    attempts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    outcome: Mapped[InvestigationOutcome] = mapped_column(
        Enum(InvestigationOutcome, name="investigationoutcome"),
        default=InvestigationOutcome.PENDING,
        nullable=False,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="investigations")
    evidence: Mapped[List["Evidence"]] = relationship("Evidence", back_populates="investigation")


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    agent_role: Mapped[AgentRole] = mapped_column(Enum(AgentRole, name="agentrole"), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="taskstatus"),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    task_input: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    task_output: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    parent_task_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("agent_tasks.id", ondelete="SET NULL"), nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="tasks")


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    investigation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("investigations.id", ondelete="SET NULL"), nullable=True, index=True)

    evidence_type: Mapped[EvidenceType] = mapped_column(Enum(EvidenceType, name="evidencetype"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    line_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    line_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provenance: Mapped[ProvenanceType] = mapped_column(
        Enum(ProvenanceType, name="provenancetype"),
        default=ProvenanceType.TOOL,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="evidence")
    investigation: Mapped[Optional["Investigation"]] = relationship("Investigation", back_populates="evidence")


class Solution(Base):
    __tablename__ = "solutions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    affected_files: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    correctness_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    maintainability_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    risks: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    complexity_score: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="solutions")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    decision: Mapped[ApprovalDecision] = mapped_column(Enum(ApprovalDecision, name="approvaldecision"), nullable=False)
    target_type: Mapped[ApprovalTarget] = mapped_column(Enum(ApprovalTarget, name="approvaltarget"), nullable=False)
    solution_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("solutions.id", ondelete="SET NULL"), nullable=True)
    custom_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="approvals")


class Implementation(Base):
    __tablename__ = "implementations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    solution_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("solutions.id", ondelete="SET NULL"), nullable=True)

    branch_name: Mapped[str] = mapped_column(String(255), nullable=False)
    base_commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    changed_files: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    commit_shas: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[ImplementationStatus] = mapped_column(
        Enum(ImplementationStatus, name="implementationstatus"),
        default=ImplementationStatus.PENDING,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="implementations")
    verification_runs: Mapped[List["VerificationRun"]] = relationship("VerificationRun", back_populates="implementation")


class VerificationRun(Base):
    __tablename__ = "verification_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)
    implementation_id: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("implementations.id", ondelete="SET NULL"), nullable=True)

    status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verificationstatus"),
        default=VerificationStatus.PENDING,
        nullable=False,
    )
    commands_run: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    raw_output: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    regression_test_passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    repro_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="verification_runs")
    implementation: Mapped[Optional["Implementation"]] = relationship("Implementation", back_populates="verification_runs")


class ConversationReference(Base):
    __tablename__ = "conversation_references"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    room_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel_type: Mapped[ChannelType] = mapped_column(
        Enum(ChannelType, name="channeltype"),
        default=ChannelType.GENERAL,
        nullable=False,
    )
    external_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="conversations")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    issue_id: Mapped[str] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), nullable=False, index=True)

    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    from_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    to_state: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    # Relationships
    issue: Mapped["Issue"] = relationship("Issue", back_populates="audit_events")
