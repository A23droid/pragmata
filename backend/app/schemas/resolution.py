import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import ApprovalDecision, ApprovalTarget, IssueStatus


class RootCauseItem(BaseModel):
    description: str = Field(..., description="Description of specific root cause mechanism")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="IDs of Evidence entities backing this cause")
    file_path: str = Field(..., description="Repository file path containing the defect")
    line_start: Optional[int] = Field(None, description="Starting line of defect")
    line_end: Optional[int] = Field(None, description="Ending line of defect")
    verified: bool = Field(True, description="True if proven by reproduction trace; False if hypothesis")


class RootCauseAnalysisReport(BaseModel):
    root_cause_summary: str = Field(..., description="High-level explanation of the defect cause")
    verified_root_causes: List[RootCauseItem] = Field(..., description="Concrete root causes supported by evidence")
    hypotheses: List[str] = Field(default_factory=list, description="Suspected or unverified hypotheses")
    affected_components: List[str] = Field(default_factory=list, description="Affected modules or components")
    underlying_defect_type: str = Field(..., description="e.g. Edge-case omission, Race condition, Type mismatch")


class SolutionProposal(BaseModel):
    proposal_id: str = Field(..., description="Identifier such as 'strategy_1', 'strategy_2'")
    strategy_type: str = Field(..., description="'MINIMAL_TARGETED', 'DEFENSIVE_REFACTOR', or 'ARCHITECTURAL'")
    title: str = Field(..., description="Concise strategy title")
    description: str = Field(..., description="Complete explanation of the proposed fix")
    affected_files: List[str] = Field(..., description="List of source files that will be modified")
    expected_changes: str = Field(..., description="Summary of expected code diff and logic changes")
    advantages: List[str] = Field(..., description="Key benefits of this approach")
    disadvantages: List[str] = Field(..., description="Trade-offs, limitations, or downsides")
    complexity_score: int = Field(ge=1, le=5, description="1=Minimal patch, 5=Significant refactoring")
    complexity_explanation: str = Field(..., description="Rationale for the assigned complexity score")
    security_implications: str = Field(..., description="Security posture impact analysis")
    regression_risks: str = Field(..., description="Identified potential regression points or blast radius")
    supporting_evidence_ids: List[str] = Field(default_factory=list, description="References to evidence items")


class SolutionArchitectProposals(BaseModel):
    proposals: List[SolutionProposal] = Field(
        ...,
        min_length=2,
        max_length=3,
        description="2 to 3 meaningfully different fix strategies",
    )
    design_summary: str = Field(..., description="Architect's overview comparing the strategy alternatives")


class ProposalCritique(BaseModel):
    proposal_id: str = Field(..., description="ID of the criticized proposal")
    independent_verdict: str = Field(
        ...,
        description="'FEASIBLE', 'FRAGILE', 'DEFECTIVE', or 'OVERENGINEERED'",
    )
    is_valid: bool = Field(..., description="Whether proposal is technically sound")
    identified_weaknesses: List[str] = Field(default_factory=list, description="Specific flaws or weak points")
    hidden_risks_and_edge_cases: List[str] = Field(default_factory=list, description="Edge cases or unaddressed scenarios")
    tradeoff_challenges: List[str] = Field(default_factory=list, description="Counter-arguments to architect's assumptions")
    is_defect_fully_addressed: bool = Field(..., description="True only if root cause is decisively eliminated")


class CriticEvaluation(BaseModel):
    critiques: List[ProposalCritique] = Field(..., description="Independent critiques for each proposal")
    overall_critique_summary: str = Field(..., description="Summary of comparative risks and blind spots")


class ProposalScopeAudit(BaseModel):
    proposal_id: str = Field(..., description="Proposal ID being audited")
    is_within_scope: bool = Field(..., description="True if change remains bounded to the defect")
    overengineering_detected: bool = Field(False, description="Flag for premature abstractions or over-complexity")
    unnecessary_files: List[str] = Field(default_factory=list, description="Files touched outside defect boundary")
    justified_scope_expansion: bool = Field(
        False,
        description="True if scope expansion is genuinely justified by correctness/security",
    )
    justification_notes: str = Field(..., description="Explanation of scope assessment and justification check")
    verdict: str = Field(
        ...,
        description="'APPROVED_IN_SCOPE', 'APPROVED_JUSTIFIED_EXPANSION', 'REQUIRES_NARROWING', 'REJECTED_OUT_OF_SCOPE'",
    )


class DebateMonitoring(BaseModel):
    round_count: int = Field(default=1, description="Current debate round number")
    max_rounds: int = Field(default=2, description="Maximum permitted debate rounds")
    excessive_debate_detected: bool = Field(False, description="True if debate is cycling without new evidence")
    diminishing_returns: bool = Field(False, description="True if further debate yields no material clarity")
    notes: str = Field(..., description="Debate bounding governance note")


class ScopeGuardianReport(BaseModel):
    proposals_scope_audit: List[ProposalScopeAudit] = Field(..., description="Audit for each proposal")
    debate_status: DebateMonitoring = Field(..., description="Monitoring of debate cycles")
    intervention_required: bool = Field(False, description="True if Scope Guardian must intervene")
    intervention_reason: Optional[str] = Field(None, description="Reason for intervention if required")


class RubricTier(str):
    EXCELLENT = "EXCELLENT"      # Grade 4
    ACCEPTABLE = "ACCEPTABLE"    # Grade 3
    CONCERN = "CONCERN"          # Grade 2
    UNACCEPTABLE = "UNACCEPTABLE"# Grade 1


class RubricDimensionScore(BaseModel):
    dimension: str = Field(..., description="e.g. MAINTAINABILITY, REGRESSION_RISK, SIMPLICITY, PERFORMANCE")
    tier: str = Field(..., description="EXCELLENT (4), ACCEPTABLE (3), CONCERN (2), or UNACCEPTABLE (1)")
    weight_percent: int = Field(..., description="Weight in final ranking calculation")
    rationale: str = Field(..., description="Documented justification for tier rating")


class EvaluatedProposal(BaseModel):
    proposal_id: str = Field(..., description="Proposal ID")
    rank: int = Field(..., description="Ordinal rank: 1=Best, 2=Second, 3=Third")
    is_recommended: bool = Field(..., description="True if this proposal is the top recommendation")
    hard_gates_passed: bool = Field(..., description="Must pass Correctness and Security hard gates")
    gate_failure_reason: Optional[str] = Field(None, description="Explanation if disqualified by a hard gate")
    composite_score: float = Field(..., description="Documented weighted score based on rubric tiers")
    dimension_evaluations: List[RubricDimensionScore] = Field(..., description="Detailed rubric breakdown")
    recommendation_rationale: str = Field(..., description="Justification for recommendation status")


class OptimizerEvaluationReport(BaseModel):
    evaluated_proposals: List[EvaluatedProposal] = Field(..., description="Ranked proposals using explicit rubric")
    recommended_proposal_id: str = Field(..., description="ID of recommended proposal")
    ranking_justification: str = Field(..., description="Clear comparative analysis explaining the ranking")
    rubric_explanation: str = Field(..., description="Documentation of criteria and weighting applied")


class SolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_id: str
    title: str
    strategy_type: Optional[str] = None
    description: str
    rationale: str
    affected_files: List[str] = Field(default_factory=list)
    expected_changes: Optional[str] = None
    advantages: List[str] = Field(default_factory=list)
    disadvantages: List[str] = Field(default_factory=list)
    security_implications: Optional[str] = None
    regression_risks: Optional[str] = None
    complexity_score: int
    is_recommended: bool
    rank: Optional[int] = None
    critique: Dict[str, Any] = Field(default_factory=dict)
    evaluation: Dict[str, Any] = Field(default_factory=dict)
    scope_assessment: Dict[str, Any] = Field(default_factory=dict)
    supporting_evidence_ids: List[str] = Field(default_factory=list)
    created_at: datetime


class FixApprovalRequest(BaseModel):
    decision: ApprovalDecision = Field(
        ...,
        description="FIX_APPROVED, CUSTOM_STRATEGY_APPROVED, REQUEST_INFORMATION, REJECTED, or DEFERRED",
    )
    solution_id: Optional[uuid.UUID] = Field(None, description="ID of selected solution if FIX_APPROVED")
    custom_strategy: Optional[str] = Field(None, description="Custom fix strategy if developer supplies one")
    notes: Optional[str] = Field(None, description="Developer fix approval notes")


class FixApprovalResponse(BaseModel):
    issue_id: str
    status: IssueStatus
    approval_id: uuid.UUID
    decision: ApprovalDecision
    target_type: ApprovalTarget
    solution_id: Optional[uuid.UUID] = None
    custom_strategy: Optional[str] = None
    actor: str
    notes: Optional[str] = None
    created_at: datetime
