"""Unit tests for LLM evidence planner and finish deferral guard."""

import pytest


@pytest.fixture
def app_ctx(app):
    with app.app_context():
        yield app


class TestEvidencePlanValidation:
    def test_validate_accepts_multi_source_plan(self, app_ctx):
        from app.services.ai.planning.evidence_plan import AIEvidencePlanner

        plan = AIEvidencePlanner.validate_plan(
            {
                "source_families": ["indicator_bank", "documents"],
                "rationale": "Needs definitions and plan text.",
                "confidence": 0.92,
            },
            tool_names={"search_indicator_bank", "search_documents", "get_indicator_metadata"},
            documents_allowed=True,
            databank_allowed=True,
        )
        assert plan is not None
        assert plan.source_families == ["indicator_bank", "documents"]

    def test_validate_rejects_low_confidence(self, app_ctx):
        from app.services.ai.planning.evidence_plan import AIEvidencePlanner

        app_ctx.config["AI_AGENT_EVIDENCE_PLAN_MIN_CONFIDENCE"] = 0.7
        plan = AIEvidencePlanner.validate_plan(
            {
                "source_families": ["indicator_bank", "documents"],
                "rationale": "Maybe both.",
                "confidence": 0.5,
            },
            tool_names={"search_indicator_bank", "search_documents"},
            documents_allowed=True,
            databank_allowed=True,
        )
        assert plan is None

    def test_validate_strips_unavailable_document_family(self, app_ctx):
        from app.services.ai.planning.evidence_plan import AIEvidencePlanner

        plan = AIEvidencePlanner.validate_plan(
            {
                "source_families": ["indicator_bank", "documents"],
                "rationale": "Needs both.",
                "confidence": 0.9,
            },
            tool_names={"search_indicator_bank"},
            documents_allowed=False,
            databank_allowed=True,
        )
        assert plan is not None
        assert plan.source_families == ["indicator_bank"]


class TestEvidencePlanDeferral:
    def test_pending_when_documents_not_called(self, app_ctx):
        from app.services.ai.planning.evidence_plan import EvidencePlan, pending_evidence_families

        plan = EvidencePlan(
            source_families=["indicator_bank", "documents"],
            rationale="Eligibility needs definitions and docs.",
            confidence=0.9,
        )
        pending = pending_evidence_families(
            plan,
            ["search_indicator_bank", "get_indicator_metadata"],
        )
        assert pending == ["documents"]

    def test_no_pending_when_all_families_satisfied(self, app_ctx):
        from app.services.ai.planning.evidence_plan import EvidencePlan, pending_evidence_families

        plan = EvidencePlan(
            source_families=["indicator_bank", "documents"],
            rationale="Both required.",
            confidence=0.9,
        )
        pending = pending_evidence_families(
            plan,
            ["search_indicator_bank", "search_documents"],
        )
        assert pending == []

    def test_should_defer_finish(self, app_ctx):
        from app.services.ai.planning.evidence_plan import EvidencePlan
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        plan = EvidencePlan(
            source_families=["indicator_bank", "documents"],
            rationale="Compound eligibility question.",
            confidence=0.9,
        )
        should_defer, pending, msg, effective = AgentRoutingPolicy.should_defer_finish_for_evidence(
            evidence_plan=plan,
            tools_used=["search_indicator_bank"],
            deferrals_used=0,
        )
        assert should_defer is True
        assert pending == ["documents"]
        assert "documents" in msg.lower()
        assert effective is plan

    def test_deferrals_exhausted(self, app_ctx):
        from app.services.ai.planning.evidence_plan import EvidencePlan
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        app_ctx.config["AI_AGENT_EVIDENCE_PLAN_MAX_DEFERRALS"] = 2
        plan = EvidencePlan(
            source_families=["indicator_bank", "documents"],
            rationale="Compound eligibility question.",
            confidence=0.9,
        )
        should_defer, _, _, _ = AgentRoutingPolicy.should_defer_finish_for_evidence(
            evidence_plan=plan,
            tools_used=["search_indicator_bank"],
            deferrals_used=2,
        )
        assert should_defer is False

    def test_finish_assessment_gate_partial_coverage(self, app_ctx):
        from app.services.ai.planning.evidence_plan import should_run_finish_evidence_assessment

        assert should_run_finish_evidence_assessment(
            tool_names={"search_indicator_bank", "search_documents", "get_indicator_value"},
            tools_used=["search_indicator_bank", "get_indicator_metadata"],
            documents_allowed=True,
            databank_allowed=True,
        ) is True

        assert should_run_finish_evidence_assessment(
            tool_names={"search_indicator_bank", "search_documents", "get_indicator_value"},
            tools_used=["get_indicator_value"],
            documents_allowed=True,
            databank_allowed=True,
        ) is True

        assert should_run_finish_evidence_assessment(
            tool_names={"get_indicator_value"},
            tools_used=["get_indicator_value"],
            documents_allowed=True,
            databank_allowed=True,
        ) is False


class TestEvidencePlanSupplement:
    def test_supplement_includes_required_families(self, app_ctx):
        from app.services.ai.planning.evidence_plan import EvidencePlan
        from app.services.ai.policies.agent_routing import AgentRoutingPolicy

        plan = EvidencePlan(
            source_families=["indicator_bank", "documents"],
            rationale="Check definitions and documentation.",
            confidence=0.9,
        )
        block = AgentRoutingPolicy.evidence_plan_supplement(plan)
        assert "indicator_bank" in block
        assert "documents" in block
        assert "mandatory" in block.lower()
