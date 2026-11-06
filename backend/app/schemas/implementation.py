from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.models.enums import ImplementationStatus, VerificationStatus


class ImplementationRequest(BaseModel):
    developer_token: str = Field(..., description="Authenticated developer token")
    push_to_remote: bool = Field(default=False, description="Whether to attempt pushing to remote and opening a PR")


class FilePatch(BaseModel):
    file_path: str = Field(..., description="Relative path of file to modify")
    new_content: str = Field(..., description="Complete replacement content for file")
    rationale: str = Field(..., description="Reasoning for changes")


class ImplementationPlanOutput(BaseModel):
    summary: str = Field(..., description="Summary of implementation work")
    file_patches: List[FilePatch] = Field(..., description="List of file modifications")
    commit_message: str = Field(..., description="Git commit message")


class VerificationRequest(BaseModel):
    run_test_suite: bool = Field(default=True, description="Whether to run project test suite")


class CheckResult(BaseModel):
    name: str
    command: str
    exit_code: int
    output: str
    passed: bool


class VerificationResponse(BaseModel):
    issue_id: str
    overall_status: VerificationStatus
    reproduction_check: CheckResult
    test_suite_check: Optional[CheckResult] = None
    all_passed: bool
    summary: str


class ImplementationDetailResponse(BaseModel):
    id: str
    issue_id: str
    branch_name: str
    base_commit_sha: str
    head_commit_sha: Optional[str] = None
    status: ImplementationStatus
    changed_files: List[str] = Field(default_factory=list)
    git_diff: Optional[str] = None
    pull_request_url: Optional[str] = None
    verification_status: Optional[VerificationStatus] = None
    verification_runs: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime

