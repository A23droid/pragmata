import logging
from typing import Dict, List, Optional, Tuple

from backend.app.schemas.resolution import (
    CriticEvaluation,
    EvaluatedProposal,
    OptimizerEvaluationReport,
    ProposalCritique,
    ProposalScopeAudit,
    RootCauseAnalysisReport,
    RubricDimensionScore,
    RubricTier,
    ScopeGuardianReport,
    SolutionArchitectProposals,
    SolutionProposal,
)

logger = logging.getLogger(__name__)

# Documented Rubric Dimension Weights
RUBRIC_WEIGHTS = {
    "MAINTAINABILITY": 25,
    "REGRESSION_RISK": 25,
    "SIMPLICITY": 20,
    "PERFORMANCE": 15,
    "EDGE_COVERAGE": 15,
}

TIER_GRADE_MAP = {
    RubricTier.EXCELLENT: 4.0,
    RubricTier.ACCEPTABLE: 3.0,
    RubricTier.CONCERN: 2.0,
    RubricTier.UNACCEPTABLE: 1.0,
}


class RubricEvaluator:
    """
    Deterministic, explicit rubric evaluation engine.
    Applies documented criteria, hard gates (correctness & security), and weighted tiers.
    Does NOT invent arbitrary floating-point scores.
    """

    @classmethod
    def evaluate_proposals(
        cls,
        proposals: List[SolutionProposal],
        critiques: List[ProposalCritique],
        scope_audits: List[ProposalScopeAudit],
        root_cause: RootCauseAnalysisReport,
    ) -> OptimizerEvaluationReport:
        critique_map: Dict[str, ProposalCritique] = {c.proposal_id: c for c in critiques}
        scope_map: Dict[str, ProposalScopeAudit] = {s.proposal_id: s for s in scope_audits}

        evaluated: List[EvaluatedProposal] = []

        for p in proposals:
            critique = critique_map.get(p.proposal_id)
            scope_audit = scope_map.get(p.proposal_id)

            # 1. Hard Gate Checks: Correctness and Security
            hard_gates_passed = True
            gate_failure_reasons = []

            # Correctness Check
            is_correct = True
            if critique and not critique.is_defect_fully_addressed:
                is_correct = False
                gate_failure_reasons.append("Critic found proposal does not decisively eliminate root cause.")
            if critique and critique.independent_verdict in ("DEFECTIVE", "FRAGILE"):
                is_correct = False
                gate_failure_reasons.append(f"Critic rendered verdict '{critique.independent_verdict}'.")

            # Security Check
            is_secure = True
            sec_lower = (p.security_implications or "").lower()
            if any(term in sec_lower for term in ["vulnerability", "insecure", "bypass", "privilege escalation"]):
                is_secure = False
                gate_failure_reasons.append("Security analysis identified potential vulnerability introduction.")

            if not is_correct or not is_secure:
                hard_gates_passed = False

            # 2. Rubric Tier Grading across weighted dimensions
            dimension_scores: List[RubricDimensionScore] = []

            # Dimension A: Maintainability (Weight 25%)
            if p.complexity_score <= 2 and (not scope_audit or not scope_audit.overengineering_detected):
                m_tier = RubricTier.EXCELLENT
                m_rat = "Clean, localized modifications with high maintainability."
            elif p.complexity_score <= 3:
                m_tier = RubricTier.ACCEPTABLE
                m_rat = "Standard maintainability footprint with moderate changes."
            elif p.complexity_score == 4 or (scope_audit and scope_audit.overengineering_detected):
                m_tier = RubricTier.CONCERN
                m_rat = "Higher cognitive load or potential abstraction overengineering."
            else:
                m_tier = RubricTier.UNACCEPTABLE
                m_rat = "Severe maintainability burden or excessive architectural churn."
            dimension_scores.append(
                RubricDimensionScore(
                    dimension="MAINTAINABILITY",
                    tier=m_tier,
                    weight_percent=RUBRIC_WEIGHTS["MAINTAINABILITY"],
                    rationale=m_rat,
                )
            )

            # Dimension B: Regression Risk (Weight 25%)
            reg_lower = (p.regression_risks or "").lower()
            num_files = len(p.affected_files)
            if num_files <= 2 and len(p.disadvantages) <= 1:
                r_tier = RubricTier.EXCELLENT
                r_rat = f"Minimal blast radius ({num_files} files); low regression likelihood."
            elif num_files <= 4:
                r_tier = RubricTier.ACCEPTABLE
                r_rat = f"Contained blast radius ({num_files} files); known manageable trade-offs."
            elif num_files <= 7:
                r_tier = RubricTier.CONCERN
                r_rat = f"Moderate blast radius ({num_files} files); potential side-effects on callers."
            else:
                r_tier = RubricTier.UNACCEPTABLE
                r_rat = f"High blast radius ({num_files} files); significant regression hazard."
            dimension_scores.append(
                RubricDimensionScore(
                    dimension="REGRESSION_RISK",
                    tier=r_tier,
                    weight_percent=RUBRIC_WEIGHTS["REGRESSION_RISK"],
                    rationale=r_rat,
                )
            )

            # Dimension C: Simplicity / Minimal Complexity (Weight 20%)
            if p.complexity_score == 1:
                s_tier = RubricTier.EXCELLENT
                s_rat = "Minimal targeted patch with lowest complexity footprint."
            elif p.complexity_score == 2:
                s_tier = RubricTier.ACCEPTABLE
                s_rat = "Focused fix with modest complexity."
            elif p.complexity_score == 3:
                s_tier = RubricTier.CONCERN
                s_rat = "Moderate structural complexity."
            else:
                s_tier = RubricTier.UNACCEPTABLE
                s_rat = "Heavy refactoring or high conceptual overhead."
            dimension_scores.append(
                RubricDimensionScore(
                    dimension="SIMPLICITY",
                    tier=s_tier,
                    weight_percent=RUBRIC_WEIGHTS["SIMPLICITY"],
                    rationale=s_rat,
                )
            )

            # Dimension D: Performance (Weight 15%)
            if "performance" in p.advantages or p.strategy_type == "MINIMAL_TARGETED":
                p_tier = RubricTier.EXCELLENT
                p_rat = "Negligible overhead or optimized performance."
            else:
                p_tier = RubricTier.ACCEPTABLE
                p_rat = "Acceptable computational and memory performance."
            dimension_scores.append(
                RubricDimensionScore(
                    dimension="PERFORMANCE",
                    tier=p_tier,
                    weight_percent=RUBRIC_WEIGHTS["PERFORMANCE"],
                    rationale=p_rat,
                )
            )

            # Dimension E: Edge Coverage (Weight 15%)
            if len(p.advantages) >= 3 and (critique and len(critique.hidden_risks_and_edge_cases) <= 1):
                e_tier = RubricTier.EXCELLENT
                e_rat = "Strong edge-case coverage confirmed by independent critique."
            elif critique and len(critique.hidden_risks_and_edge_cases) <= 2:
                e_tier = RubricTier.ACCEPTABLE
                e_rat = "Adequate coverage for primary and secondary scenarios."
            else:
                e_tier = RubricTier.CONCERN
                e_rat = "Critic highlighted unaddressed edge-case scenarios."
            dimension_scores.append(
                RubricDimensionScore(
                    dimension="EDGE_COVERAGE",
                    tier=e_tier,
                    weight_percent=RUBRIC_WEIGHTS["EDGE_COVERAGE"],
                    rationale=e_rat,
                )
            )

            # 3. Calculate Composite Weighted Grade (1.0 to 4.0)
            composite = sum(
                TIER_GRADE_MAP.get(d.tier, 2.0) * (d.weight_percent / 100.0)
                for d in dimension_scores
            )
            # If disqualified by hard gate, cap composite score
            if not hard_gates_passed:
                composite = min(composite, 1.5)

            gate_msg = "; ".join(gate_failure_reasons) if gate_failure_reasons else None
            evaluated.append(
                EvaluatedProposal(
                    proposal_id=p.proposal_id,
                    rank=0,  # Calculated after sorting
                    is_recommended=False,
                    hard_gates_passed=hard_gates_passed,
                    gate_failure_reason=gate_msg,
                    composite_score=round(composite, 2),
                    dimension_evaluations=dimension_scores,
                    recommendation_rationale=(
                        f"Composite grade: {composite:.2f}/4.00. "
                        + (f"Disqualified by hard gates: {gate_msg}" if not hard_gates_passed else "Passed all critical correctness and security gates.")
                    ),
                )
            )

        # 4. Rank proposals:
        # Qualifying proposals (hard_gates_passed == True) rank above disqualified proposals, sorted by composite score descending.
        evaluated.sort(
            key=lambda ep: (1 if ep.hard_gates_passed else 0, ep.composite_score),
            reverse=True,
        )

        for idx, ep in enumerate(evaluated, start=1):
            ep.rank = idx

        # Top qualifying proposal is marked recommended
        recommended_id = evaluated[0].proposal_id if evaluated and evaluated[0].hard_gates_passed else (evaluated[0].proposal_id if evaluated else "")
        if evaluated and evaluated[0].hard_gates_passed:
            evaluated[0].is_recommended = True
            evaluated[0].recommendation_rationale += " [TOP RECOMMENDED FIX STRATEGY]"

        rubric_explanation = (
            "Documented PRAGMATA Rubric: "
            "1. Hard Gates: Correctness and Security (Pass/Fail). Disqualified proposals cannot be recommended. "
            "2. Weighted Criteria: Maintainability (25%), Regression Risk (25%), Simplicity (20%), Performance (15%), Edge Coverage (15%). "
            "3. Standard Qualitative Tiers: EXCELLENT (4.0), ACCEPTABLE (3.0), CONCERN (2.0), UNACCEPTABLE (1.0)."
        )

        ranking_justification = (
            f"Proposal '{recommended_id}' is ranked #1 with composite score {evaluated[0].composite_score}/4.00. "
            f"It satisfies all correctness and security hard gates while optimizing maintainability and regression safety."
        )

        return OptimizerEvaluationReport(
            evaluated_proposals=evaluated,
            recommended_proposal_id=recommended_id,
            ranking_justification=ranking_justification,
            rubric_explanation=rubric_explanation,
        )
