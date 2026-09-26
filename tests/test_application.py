from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from benchmark.application.bootstrap import build_demo_services
from benchmark.application.connector_monitor import ConnectorConfig, ConnectorMonitor
from benchmark.application.control import ActionControlPlane, InMemoryActionStore
from benchmark.application.deviation_agent import PrimeAgentDeviationOrchestrator
from benchmark.application.execution import ActionExecutionGateway, DemoActionWriter
from benchmark.application.intelligence import DeterministicModelRouter, ToolGateway
from benchmark.application.models import ActionProposal, ApprovalDecision, ProposalStatus, RiskLevel
from benchmark.application.orchestration import CaseOrchestrator
from benchmark.knowledge.domain import AccessContext


class ApplicationControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = InMemoryActionStore()
        self.control = ActionControlPlane(self.store)
        self.requester = AccessContext("SPONSOR-A", "msat-01", roles=("scientist",))

    def proposal(self, operation: str = "release_batch") -> ActionProposal:
        return ActionProposal(
            "PROP-01", "SPONSOR-A", "CASE-01", operation, "BATCH-01", {},
            "msat-01", "Evidence package is ready",
        )

    def test_critical_action_requires_qa_and_sponsor_qa(self) -> None:
        proposal = self.control.propose(self.proposal(), self.requester)
        self.assertEqual(proposal.risk, RiskLevel.CRITICAL)
        self.assertEqual(proposal.required_roles, ("qa", "sponsor_qa"))

        qa = AccessContext("SPONSOR-A", "qa-01", roles=("qa",))
        partly = self.control.decide("PROP-01", ApprovalDecision(
            "APR-1", "qa-01", "qa", "approved", "QA disposition",
        ), qa)
        self.assertEqual(partly.status, ProposalStatus.PENDING)

        sponsor = AccessContext("SPONSOR-A", "sqa-01", roles=("sponsor_qa",))
        approved = self.control.decide("PROP-01", ApprovalDecision(
            "APR-2", "sqa-01", "sponsor_qa", "approved", "Sponsor release authorization",
        ), sponsor)
        self.assertEqual(approved.status, ProposalStatus.APPROVED)
        self.assertEqual(len(self.store.audit("SPONSOR-A")), 3)

    def test_requester_cannot_approve_own_action(self) -> None:
        self.control.propose(self.proposal("place_hold"), self.requester)
        self_approver = AccessContext("SPONSOR-A", "msat-01", roles=("supervisor",))
        with self.assertRaises(PermissionError):
            self.control.decide("PROP-01", ApprovalDecision(
                "APR-1", "msat-01", "supervisor", "approved", "hold authorization",
            ), self_approver)

    def test_rejection_closes_the_approval_request(self) -> None:
        self.control.propose(self.proposal("close_deviation"), self.requester)
        qa = AccessContext("SPONSOR-A", "qa-01", roles=("qa",))
        rejected = self.control.decide("PROP-01", ApprovalDecision(
            "APR-1", "qa-01", "qa", "rejected", "QA disposition", comment="Evidence incomplete",
        ), qa)
        self.assertEqual(rejected.status, ProposalStatus.REJECTED)

    def test_site_scope_and_execution_gateway_are_enforced(self) -> None:
        scoped_requester = AccessContext("SPONSOR-A", "msat-01", ("SITE-01",), ("scientist",))
        proposal = self.proposal("place_hold")
        proposal.site_id = "SITE-02"
        with self.assertRaises(PermissionError):
            self.control.propose(proposal, scoped_requester)

        proposal.site_id = "SITE-01"
        self.control.propose(proposal, scoped_requester)
        writes: list[str] = []

        class CountingWriter:
            def write(self, proposal, access):
                writes.append(proposal.proposal_id)
                return "ACK"

        executor = AccessContext("SPONSOR-A", "gateway-1", ("SITE-01",), ("system_executor",))
        with self.assertRaises(ValueError):
            ActionExecutionGateway(self.control, CountingWriter()).execute("PROP-01", executor)
        self.assertEqual(writes, [])
        supervisor = AccessContext("SPONSOR-A", "supervisor-1", ("SITE-01",), ("supervisor",))
        self.control.decide("PROP-01", ApprovalDecision(
            "APR-1", "supervisor-1", "supervisor", "approved", "hold authorization",
        ), supervisor)
        result = ActionExecutionGateway(self.control, DemoActionWriter()).execute("PROP-01", executor)
        self.assertEqual(result["proposal"].status, ProposalStatus.EXECUTED)
        self.assertTrue(result["source_record_id"].startswith("DEMO-ACK-PROP-01-"))


class IntelligenceAndOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.router = DeterministicModelRouter()
        self.tools = ToolGateway(self.router)

    def test_statistical_and_optimization_jobs_are_deterministic(self) -> None:
        first = self.tools.execute("spc", {"values": [6.9, 7.0, 7.1, 7.0]})
        second = self.tools.execute("spc", {"values": [6.9, 7.0, 7.1, 7.0]})
        self.assertEqual(first, second)
        self.assertEqual(first["result"]["state"], "in_control")
        design = self.tools.execute("doe", {
            "factors": {"temperature": [35, 37], "pH": [6.8, 7.0]}, "max_runs": 4,
        })
        self.assertEqual(design["result"]["run_count"], 4)
        with self.assertRaises(ValueError):
            self.tools.execute("shell", {})

    def test_case_type_routes_to_specialist_and_is_tenant_scoped(self) -> None:
        orchestrator = CaseOrchestrator(self.tools)
        run = orchestrator.start("CASE-1", {
            "case": {"case_id": "CASE-1", "case_type": "maintenance"},
            "identity": {"tenant_id": "TENANT-A"},
            "digital_thread": {"events": [{"event_id": "E-1"}], "documents": []},
        })
        self.assertEqual(run["agent_id"], "production-maintenance")
        self.assertEqual(run["harness"], "deterministic_runtime")
        self.assertEqual(run["status"], "completed")
        state = orchestrator.case_state("CASE-1", "TENANT-A")
        self.assertEqual(state["evidence_count"], 1)
        self.assertIsNone(orchestrator.case_state("CASE-1", "TENANT-B"))
        other = orchestrator.start("CASE-1", {
            "case": {"case_id": "CASE-1", "case_type": "capa"},
            "identity": {"tenant_id": "TENANT-B"}, "digital_thread": {},
        })
        self.assertEqual(orchestrator.latest("CASE-1", "TENANT-A")["agent_id"], "production-maintenance")
        self.assertEqual(orchestrator.latest("CASE-1", "TENANT-B")["run_id"], other["run_id"])

    def test_demo_seed_contains_isolated_tenants(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            services = build_demo_services(Path(temporary) / "evidence")
            northstar = services.thread.cases.list_cases("demo-cdmo")
            helix = services.thread.cases.list_cases("helix-biologics")
            self.assertEqual({case.tenant_id for case in northstar}, {"demo-cdmo"})
            self.assertEqual({case.tenant_id for case in helix}, {"helix-biologics"})
            self.assertEqual([case.case_id for case in helix], ["CASE-7812"])
            access = AccessContext("helix-biologics", "qa-22", ("BOS-02",), ("qa",))
            completed = services.thread.complete_task("TASK-211", access=access)
            self.assertEqual(completed.status, "completed")
            self.assertIsNotNone(completed.completed_at)
            executor = AccessContext(
                "demo-cdmo", "gateway-1", ("PHX-01",), ("system_executor",), ("internal",),
            )
            receipt = services.execution.execute("ACT-2409-HOLD", executor)
            context = services.thread.knowledge.context(
                "action acknowledged", entity_ids=["BATCH-2409"], access=executor,
            )
            self.assertTrue(receipt["source_record_id"].startswith("DEMO-ACK-"))
            self.assertEqual(context.events[0].event_type, "action_acknowledged")


class DeviationAgentOrchestratorTests(unittest.TestCase):
    def test_run_persists_context_session_and_final_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = root / "prime-agent"
            skill = bundle / ".prime" / "agent" / "skills" / "deviation"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("---\nname: deviation\ndescription: test\n---\n")
            (bundle / ".prime" / "agent" / "APPEND_SYSTEM.md").write_text("Deviation system")
            script = (
                "import json;"
                "print(json.dumps({'type':'session','id':'session-1'}));"
                "print(json.dumps({'type':'message_end','message':{'role':'assistant',"
                "'content':[{'type':'text','text':'Investigation staged'}]}}))"
            )
            orchestrator = PrimeAgentDeviationOrchestrator(
                [sys.executable, "-c", script],
                bundle,
                root / "app",
                api_base_url="http://127.0.0.1:8000",
            )
            run = orchestrator.start("CASE-01", {"case": {"case_id": "CASE-01"}})
            completed = orchestrator.wait(run["run_id"])

            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["session_id"], "session-1")
            self.assertEqual(completed["summary"], "Investigation staged")
            input_files = list((root / "app" / ".prime" / "deviation-agent-inputs").glob("*.json"))
            self.assertEqual(len(input_files), 1)
            stored = json.loads(input_files[0].read_text())
            self.assertEqual(stored["case"]["case_id"], "CASE-01")


class ConnectorMonitorTests(unittest.TestCase):
    def test_signal_is_ingested_once_and_starts_agent(self) -> None:
        class FakeOrchestrator:
            def __init__(self) -> None:
                self.started: list[tuple[str, dict]] = []

            def start(self, case_id: str, context: dict) -> dict:
                self.started.append((case_id, context))
                return {"run_id": "run-1", "case_id": case_id, "status": "queued"}

        records = [{
            "source_record_id": "alarm-77",
            "timestamp": "2026-09-26T12:00:00Z",
            "event_type": "critical_process_alarm",
            "title": "V-204 pressure above approved limit",
            "entities": [
                {"entity_id": "BATCH-77", "entity_type": "batch"},
                {"entity_id": "V-204", "entity_type": "asset"},
            ],
        }]

        with tempfile.TemporaryDirectory() as temporary:
            services = build_demo_services(Path(temporary) / "evidence")
            orchestrator = FakeOrchestrator()
            services.extensions.orchestrator = orchestrator
            monitor = ConnectorMonitor(
                services.thread,
                services.extensions,
                Path(temporary) / "connectors.json",
                fetch_records=lambda _config, _cursor: (records, "cursor-1"),
            )
            monitor.put(ConnectorConfig(
                connector_id="hist-1",
                name="Plant historian",
                source_system="PI",
                base_url="https://historian.example",
                records_path="/api/alarms",
                tenant_id="demo-cdmo",
                site_id="PHX-01",
                trigger_event_types=("critical_process_alarm",),
                auto_start_agent=True,
            ))

            first = monitor.sync("hist-1")
            second = monitor.sync("hist-1")

            self.assertEqual(first["ingested"], 1)
            self.assertEqual(first["cases_opened"], 1)
            self.assertEqual(second["duplicates"], 1)
            self.assertEqual(len(orchestrator.started), 1)
            case_id, context = orchestrator.started[0]
            self.assertEqual(context["trigger"]["source_record_id"], "alarm-77")
            self.assertIsNotNone(services.thread.cases.get_case(case_id, "demo-cdmo"))


if __name__ == "__main__":
    unittest.main()
