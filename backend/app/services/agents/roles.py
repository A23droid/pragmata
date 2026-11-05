from typing import List, Optional
from pydantic import BaseModel, Field


class IntakeAnalysisResult(BaseModel):
    title: str = Field(description="Normalized concise bug title")
    summary: str = Field(description="Structured summary of the reported bug")
    expected_behaviour: str = Field(description="What should happen")
    actual_behaviour: str = Field(description="What actually happens")
    missing_context: bool = Field(description="True if critical info is missing to proceed")
    clarification_questions: List[str] = Field(default_factory=list, description="Questions if missing context")
    tags: List[str] = Field(default_factory=list)


class InvestigatorResult(BaseModel):
    relevant_files: List[str] = Field(description="Repository files related to this issue")
    suspected_symbols: List[str] = Field(description="Functions, methods, or classes involved")
    execution_path_summary: str = Field(description="Summary of likely code flow")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Confidence in file localization")


class ReproducerPlan(BaseModel):
    reproduction_strategy: str = Field(description="Minimal reproduction approach")
    command_to_run: str = Field(description="Exact safe command to execute in sandbox")
    test_script_content: Optional[str] = Field(default=None, description="Targeted reproduction test script")
    expected_failure_pattern: str = Field(description="Error message or pattern that confirms reproduction")


class RootCauseResult(BaseModel):
    defect_description: str = Field(description="Exact root cause explanation")
    affected_components: List[str] = Field(description="Components/modules containing the defect")
    evidence_citations: List[str] = Field(description="References to code lines or logs confirming root cause")


class FixProposal(BaseModel):
    proposal_id: str
    title: str
    description: str
    why_it_addresses_root_cause: str
    files_to_modify: List[str]
    maintainability_impact: str
    regression_risk: str
    complexity_score: int = Field(ge=1, le=5, description="1=Minimal, 5=High refactoring")


class SolutionArchitectResult(BaseModel):
    proposals: List[FixProposal] = Field(min_length=1, max_length=3, description="2 to 3 distinct fix strategies")


class CriticReview(BaseModel):
    proposal_id: str
    is_valid: bool
    challenges_and_weaknesses: List[str]
    hidden_risks: List[str]


class ScopeGuardianEvaluation(BaseModel):
    proposal_id: str
    is_within_scope: bool
    unnecessary_files: List[str] = Field(default_factory=list)
    has_overengineering: bool = False
    verdict: str = Field(description="APPROVED or REQUIRES_NARROWING with reasoning")

