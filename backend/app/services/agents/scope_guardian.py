import logging
from typing import List, Optional, Set

from backend.app.schemas.resolution import (
    DebateMonitoring,
    ProposalScopeAudit,
    RootCauseAnalysisReport,
    ScopeGuardianReport,
    SolutionProposal,
)

logger = logging.getLogger(__name__)

# Maximum debate rounds before Scope Guardian forces termination / escalation
MAX_DEBATE_ROUNDS = 2


class ScopeGuardian:
    """
    Independent Scope Guardian.
    Audits proposed fix strategies for overengineering, scope creep, and excessive debate.
    Guarantees that justified security, correctness, and maintainability improvements are NOT suppressed.
    Reports directly to the Orchestrator.
    """

    @classmethod
    def audit_proposals_and_debate(
        cls,
        proposals: List[SolutionProposal],
        root_cause: RootCauseAnalysisReport,
        current_debate_round: int = 1,
    ) -> ScopeGuardianReport:
        # Determine legitimate root-cause file scope from verified root causes
        known_defect_files: Set[str] = {
            item.file_path for item in root_cause.verified_root_causes if item.file_path
        }
        # If no verified files recorded, allow affected components or primary files
        if not known_defect_files:
            for p in proposals:
                known_defect_files.update(p.affected_files[:2])

        audits: List[ProposalScopeAudit] = []
        intervention_needed = False
        intervention_reasons = []

        for p in proposals:
            touched_files = set(p.affected_files)
            # Find files not in root cause defect set
            unnecessary_files = [f for f in touched_files if f not in known_defect_files]

            # Assess justified scope expansion:
            # Check if additional files are genuinely required for security, correctness, or test coverage
            sec_lower = (p.security_implications or "").lower()
            desc_lower = (p.description + " " + p.expected_changes).lower()

            is_security_improvement = any(
                term in sec_lower for term in ["sanitize", "escape", "auth", "validate", "protect", "harden", "csrf", "xss"]
            )
            is_correctness_preventive = any(
                term in desc_lower for term in ["regression test", "schema update", "prevent invalid state", "handle null", "boundary check"]
            )

            is_justified = False
            overengineering_detected = False

            if unnecessary_files:
                if (is_security_improvement or is_correctness_preventive) and len(unnecessary_files) <= 3:
                    # Justified scope expansion: do NOT suppress!
                    is_justified = True
                    justification_notes = (
                        f"Scope expansion to {len(unnecessary_files)} auxiliary file(s) ({', '.join(unnecessary_files)}) "
                        "is justified by correctness and security defense-in-depth."
                    )
                    verdict = "APPROVED_JUSTIFIED_EXPANSION"
                    is_within_scope = True
                else:
                    # Unjustified scope creep
                    is_justified = False
                    overengineering_detected = p.complexity_score >= 4
                    justification_notes = (
                        f"Unnecessary files modified outside defect boundary: {', '.join(unnecessary_files)}. "
                        "No security or correctness justification provided."
                    )
                    verdict = "REQUIRES_NARROWING"
                    is_within_scope = False
                    intervention_needed = True
                    intervention_reasons.append(
                        f"Proposal '{p.proposal_id}' touches unrelated files ({unnecessary_files})."
                    )
            else:
                # Strictly within defect file boundary
                if p.complexity_score >= 5:
                    overengineering_detected = True
                    justification_notes = "High complexity score indicates potential over-abstraction or premature optimization."
                    verdict = "REQUIRES_NARROWING"
                    is_within_scope = False
                    intervention_needed = True
                    intervention_reasons.append(f"Proposal '{p.proposal_id}' flagged for overengineering.")
                else:
                    is_within_scope = True
                    justification_notes = "Change is strictly contained within root-cause defect boundary."
                    verdict = "APPROVED_IN_SCOPE"

            audits.append(
                ProposalScopeAudit(
                    proposal_id=p.proposal_id,
                    is_within_scope=is_within_scope,
                    overengineering_detected=overengineering_detected,
                    unnecessary_files=unnecessary_files if not is_justified else [],
                    justified_scope_expansion=is_justified,
                    justification_notes=justification_notes,
                    verdict=verdict,
                )
            )

        # 2. Debate Monitoring
        excessive_debate = current_debate_round > MAX_DEBATE_ROUNDS
        diminishing = current_debate_round >= MAX_DEBATE_ROUNDS

        if excessive_debate:
            intervention_needed = True
            intervention_reasons.append(
                f"Debate round {current_debate_round} exceeds maximum allowed budget ({MAX_DEBATE_ROUNDS} rounds). Escalating to Orchestrator."
            )

        debate_status = DebateMonitoring(
            round_count=current_debate_round,
            max_rounds=MAX_DEBATE_ROUNDS,
            excessive_debate_detected=excessive_debate,
            diminishing_returns=diminishing,
            notes=(
                f"Debate round {current_debate_round}/{MAX_DEBATE_ROUNDS}. "
                + ("Terminating debate cycle." if excessive_debate else "Debate within bounded limits.")
            ),
        )

        final_intervention_reason = "; ".join(intervention_reasons) if intervention_reasons else None

        if intervention_needed:
            logger.warning(
                f"Scope Guardian intervention triggered: {final_intervention_reason}"
            )

        return ScopeGuardianReport(
            proposals_scope_audit=audits,
            debate_status=debate_status,
            intervention_required=intervention_needed,
            intervention_reason=final_intervention_reason,
        )
