from __future__ import annotations

import unittest

from benchmark.application.control import ActionControlPlane, InMemoryActionStore
from benchmark.application.models import ActionProposal, ApprovalDecision, ProposalStatus, RiskLevel
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


if __name__ == "__main__":
    unittest.main()
