from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app import create_app
from importers import EXPECTED_COLUMNS


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(str(Path(self.temp.name) / "api.db"))
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_wizard_drafts_support_multiple_concurrent_in_progress_engagements(self):
        first = self.client.post("/api/wizard-drafts", json={
            "wizard": {"step": 1, "info": {"engagement_code": "GLC-01", "client_name": "Glacier Bank"}}
        })
        self.assertEqual(first.status_code, 201)
        first_id = first.json["data"]["id"]

        second = self.client.post("/api/wizard-drafts", json={
            "wizard": {"step": 2, "info": {"engagement_code": "ATL-01", "client_name": "Atlas Co"}}
        })
        self.assertEqual(second.status_code, 201)
        second_id = second.json["data"]["id"]
        self.assertNotEqual(first_id, second_id)

        listing = self.client.get("/api/wizard-drafts").json["data"]["drafts"]
        self.assertEqual({row["id"] for row in listing}, {first_id, second_id})
        codes = {row["engagement_code"] for row in listing}
        self.assertEqual(codes, {"GLC-01", "ATL-01"})

        update = self.client.put(f"/api/wizard-drafts/{first_id}", json={
            "wizard": {"step": 4, "info": {"engagement_code": "GLC-01", "client_name": "Glacier Bank"}, "weekly": {"0:0:2026-06-08": 12}}
        })
        self.assertEqual(update.status_code, 200)
        resumed = self.client.get(f"/api/wizard-drafts/{first_id}").json["data"]
        self.assertEqual(resumed["step"], 4)
        self.assertEqual(resumed["wizard"]["weekly"]["0:0:2026-06-08"], 12)

        # the second draft is untouched by editing the first
        still_there = self.client.get(f"/api/wizard-drafts/{second_id}").json["data"]
        self.assertEqual(still_there["wizard"]["info"]["engagement_code"], "ATL-01")

        deleted = self.client.delete(f"/api/wizard-drafts/{first_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/wizard-drafts/{first_id}").status_code, 404)
        remaining = self.client.get("/api/wizard-drafts").json["data"]["drafts"]
        self.assertEqual({row["id"] for row in remaining}, {second_id})

    def test_simple_mode_creates_general_phase_and_rejects_duplicate_name(self):
        response = self.client.post("/api/engagements", json=self.simple_payload("S-1"))
        self.assertEqual(response.status_code, 201)
        data = response.json["data"]
        self.assertEqual(data["engagement"]["complexity_mode"], "simple")
        self.assertEqual(data["phases"][0]["phase_name"], "General")
        duplicate = self.client.post(f"/api/engagements/{data['engagement']['id']}/team", json={
            "name": "Smith, Jane", "role": "Manager"
        })
        self.assertEqual(duplicate.status_code, 409)

    def test_complex_engagement_persists_three_phases(self):
        response = self.client.post("/api/engagements", json=self.complex_payload("C-1", 3))
        self.assertEqual(response.status_code, 201)
        data = response.json["data"]
        self.assertEqual(data["engagement"]["status"], "planning")
        self.assertEqual(len(data["phases"]), 3)
        self.assertEqual(sum(p["sow_fees"] for p in data["phases"]), 18000)

    def test_complex_weekly_budget_must_reconcile_to_team_target(self):
        payload = self.complex_payload("C-RECON", 1)
        payload["weekly_budgets"] = [{
            "phase_index": 0, "team_index": 0,
            "week_start_date": "2026-07-06", "budgeted_hours": 10
        }]
        response = self.client.post("/api/engagements", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json["error"]["code"], "budget_reconciliation_error")

    def test_change_order_requires_owned_phase(self):
        data = self.create_complex("C-2")
        eid = data["engagement"]["id"]
        invalid = self.client.post(f"/api/engagements/{eid}/adjustments", json={
            "adjustment_type": "change_order", "amount": 5000
        })
        self.assertEqual(invalid.status_code, 400)
        phase_id = data["phases"][0]["id"]
        valid = self.client.post(f"/api/engagements/{eid}/adjustments", json={
            "adjustment_type": "change_order", "phase_id": phase_id, "amount": 5000
        })
        self.assertEqual(valid.status_code, 201)
        self.assertEqual(valid.json["data"][0]["phase_id"], phase_id)

    def test_first_import_activates_and_unmatched_time_can_be_resolved(self):
        # budgeted_hours=0: this test exercises the unmatched_phase exception path itself, which
        # requires the worker to have no staffing signal — a worker staffed (even on just this one
        # phase) auto-resolves via allocation_method='staffing_match' and never reaches the queue.
        payload = self.complex_payload("C-3", 1)
        payload["team"][0]["budgeted_hours"] = 0
        data = self.client.post("/api/engagements", json=payload).json["data"]
        eid, phase_id = data["engagement"]["id"], data["phases"][0]["id"]
        preview = self.preview(eid, [self.import_row("T1", "", "2026-07-12", 8, 1600, 1200)])
        self.assertIn("unmatched_phase", preview["rows"][0]["flags"])
        self.assertTrue(preview["rows"][0]["included"])
        committed = self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        self.assertEqual(committed.status_code, 201)
        current = self.client.get(f"/api/engagements/{eid}").json["data"]
        self.assertEqual(current["engagement"]["status"], "active")
        self.assertEqual(current["metrics"]["hours_to_date"], 8)
        self.assertEqual(current["metrics"]["unmatched_phase_hours"], 8)
        resolved = self.client.patch(f"/api/engagements/{eid}/unmatched-phases", json={
            "phase_id": phase_id, "phase_desc": ""
        })
        self.assertEqual(resolved.json["data"]["updated"], 1)
        self.assertEqual(self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["unmatched_phase_rows"], 0)

    def test_active_budget_edit_redirects_to_atomic_revision(self):
        data = self.create_complex("C-4")
        eid, phase_id = data["engagement"]["id"], data["phases"][0]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 8, 1600, 1200)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        blocked = self.client.put(f"/api/engagements/{eid}/phases/{phase_id}", json={"sow_fees": 9000})
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json["error"]["revision_endpoint"], f"/api/engagements/{eid}/revisions")
        revised = self.client.post(f"/api/engagements/{eid}/revisions", json={
            "target_type": "phase", "target_id": phase_id, "field_name": "sow_fees",
            "new_value": 9000, "reason": "Approved re-baseline"
        })
        self.assertEqual(revised.status_code, 201)
        phase = self.client.get(f"/api/engagements/{eid}/phases").json["data"][0]
        self.assertEqual(phase["sow_fees"], 9000)

    def test_client_expense_has_no_realization_effect_and_crowe_expense_does(self):
        data = self.create_complex("C-5")
        eid = data["engagement"]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 5, 1000, 800)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        baseline = self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["realization"]
        self.client.post(f"/api/engagements/{eid}/expenses", json={"expense_type":"client_paid","amount":100})
        after_client = self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["realization"]
        self.client.post(f"/api/engagements/{eid}/expenses", json={"expense_type":"crowe_paid","amount":100})
        after_crowe = self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["realization"]
        self.assertEqual(baseline, after_client)
        self.assertAlmostEqual(after_crowe, baseline-0.1)

    def test_week_over_week_variance_is_informational(self):
        data = self.create_complex("C-6")
        eid = data["engagement"]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 8, 800, 600)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        preview = self.preview(eid, [self.import_row("T2", "A", "2026-07-19", 40, 4000, 3000)])
        self.assertIn("variance_flagged", preview["rows"][0]["flags"])
        self.assertTrue(preview["rows"][0]["included"])

    def test_active_roster_addition_requires_reason_and_is_audited(self):
        data = self.create_complex("C-7")
        eid = data["engagement"]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 8, 800, 600)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        missing_reason = self.client.post(f"/api/engagements/{eid}/team", json={
            "name": "Jones, Alex", "role": "Senior", "budgeted_hours": 80
        })
        self.assertEqual(missing_reason.status_code, 400)
        added = self.client.post(f"/api/engagements/{eid}/team", json={
            "name": "Jones, Alex", "role": "Senior", "reason": "Approved staffing change"
        })
        self.assertEqual(added.status_code, 201)
        revisions = self.client.get(f"/api/engagements/{eid}/revisions").json["data"]
        self.assertEqual(revisions[0]["field_name"], "team_member_added")

    def test_closed_engagement_mutations_are_rejected(self):
        data = self.create_complex("C-8")
        eid, phase_id = data["engagement"]["id"], data["phases"][0]["id"]
        expense = self.client.post(f"/api/engagements/{eid}/expenses", json={
            "expense_type": "crowe_paid", "amount": 100
        }).json["data"][0]
        self.assertEqual(self.client.put(f"/api/engagements/{eid}", json={
            "status": "closed", "reason": "Engagement complete"
        }).status_code, 200)
        mutations = [
            self.client.put(f"/api/engagements/{eid}/phases/{phase_id}", json={"phase_name": "Changed"}),
            self.client.delete(f"/api/engagements/{eid}/expenses/{expense['id']}"),
            self.client.post(f"/api/engagements/{eid}/adjustments", json={
                "adjustment_type": "bima", "amount": 100, "description": "Approved reduction"
            }),
        ]
        self.assertTrue(all(response.status_code == 409 for response in mutations))
        self.assertTrue(all(response.json["error"]["code"] == "engagement_closed" for response in mutations))

    def test_demo_seed_migrates_on_demand(self):
        loaded = self.client.post("/api/demo/load-seed")
        self.assertEqual(loaded.status_code, 200)
        self.assertEqual(len(loaded.json["data"]["engagements"]), 5)

    def test_database_backup_can_be_validated_and_restored(self):
        original = self.client.post("/api/engagements", json=self.simple_payload("BACKUP-1"))
        self.assertEqual(original.status_code, 201)
        backup = self.client.post("/api/settings/backup", json={}).json["data"]
        self.client.post("/api/engagements", json=self.simple_payload("BACKUP-2"))
        with open(backup["path"], "rb") as handle:
            restored = self.client.post("/api/settings/restore", data={
                "file": (handle, "known-good.db")
            }, content_type="multipart/form-data")
        self.assertEqual(restored.status_code, 200)
        codes = [item["engagement_code"] for item in
                 self.client.get("/api/engagements").json["data"]["engagements"]]
        self.assertIn("BACKUP-1", codes)
        self.assertNotIn("BACKUP-2", codes)

    def test_proposal_can_be_created_updated_and_listed(self):
        created = self.client.post("/api/proposals", json=self.proposal_payload("PROP-1"))
        self.assertEqual(created.status_code, 201)
        pid = created.json["data"]["proposal"]["id"]
        self.assertEqual(created.json["data"]["metrics"]["forecast_hours"], 24)
        listed = self.client.get("/api/proposals")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json["data"]["proposals"][0]["proposal_code"], "PROP-1")
        update_payload = created.json["data"]
        update_payload["proposal"]["notes"] = "Refined estimate"
        update_payload["weekly_budgets"] = [
            {"proposal_person_id": update_payload["people"][0]["id"], "week_start_date": "2026-08-17", "budgeted_hours": 12, "forecasted_hours": 10},
            {"proposal_person_id": update_payload["people"][0]["id"], "week_start_date": "2026-08-24", "budgeted_hours": 12, "forecasted_hours": 8},
        ]
        updated = self.client.put(f"/api/proposals/{pid}", json=update_payload)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json["data"]["proposal"]["notes"], "Refined estimate")
        self.assertEqual(updated.json["data"]["metrics"]["forecast_hours"], 18)

    def test_proposal_role_rates_and_discounts_are_calculated_before_conversion(self):
        saved_rates = self.client.put("/api/settings/rate-cards", json={
            "name": "Current governed rates",
            "rates": [{
                "role_name": "Manager FY26", "standard_rate": 350,
                "engagement_rate": 300, "contract_rate": 280, "dte_rate": 320,
            }],
        })
        self.assertEqual(saved_rates.status_code, 200)
        payload = self.proposal_payload("PROP-PRICING")
        payload["proposal"]["rate_basis"] = "contract"
        payload["proposal"]["discount_rate"] = 0.10
        payload["people"][0].pop("rough_rate")
        payload["people"][0].pop("discount_rate")
        created = self.client.post("/api/proposals", json=payload)
        self.assertEqual(created.status_code, 201)
        data = created.json["data"]
        person = data["people"][0]
        self.assertEqual(person["base_rate"], 280)
        self.assertEqual(person["discount_rate"], 0.10)
        self.assertEqual(person["rough_rate"], 252)
        self.assertEqual(data["metrics"]["estimated_base_fees"], 6720)
        self.assertEqual(data["metrics"]["estimated_discount_amount"], 672)
        self.assertEqual(data["metrics"]["estimated_fees"], 6048)

        converted = self.client.post(f"/api/proposals/{data['proposal']['id']}/convert", json={
            "engagement_code": "ENG-GOVERNED", "client_name": "Proposal Client",
            "engagement_lead": "Lead, Alex", "complexity_mode": "complex",
            "first_monday": "2026-09-07",
            "people": [{"proposal_person_id": person["id"], "name": "Smith, Jane",
                        "role": "Manager FY26", "phase_name": "Delivery"}],
        })
        self.assertEqual(converted.status_code, 201)
        team_member = converted.json["data"]["engagement"]["team"][0]
        self.assertEqual(team_member["internal_rate"], 350)
        self.assertEqual(team_member["engagement_rate"], 300)
        # Contract rate is no longer a distinct concept: it always mirrors engagement rate.
        self.assertEqual(team_member["contract_rate"], 300)

    def test_proposal_rejects_unknown_roles_and_invalid_discounts(self):
        payload = self.proposal_payload("PROP-BAD-ROLE")
        payload["people"][0]["role"] = "Made up role"
        self.assertEqual(self.client.post("/api/proposals", json=payload).status_code, 400)
        payload = self.proposal_payload("PROP-BAD-DISCOUNT")
        payload["proposal"]["discount_rate"] = 1.01
        self.assertEqual(self.client.post("/api/proposals", json=payload).status_code, 400)

    def test_proposal_can_convert_to_engagement(self):
        created = self.client.post("/api/proposals", json=self.proposal_payload("PROP-2"))
        pid = created.json["data"]["proposal"]["id"]
        person = created.json["data"]["people"][0]
        missing = self.client.post(f"/api/proposals/{pid}/convert", json={"engagement_code": "ENG-FROM-PROP"})
        self.assertEqual(missing.status_code, 400)
        converted = self.client.post(f"/api/proposals/{pid}/convert", json={
            "engagement_code": "ENG-FROM-PROP", "client_name": "Confirmed Proposal Client",
            "engagement_lead": "Lead, Alex", "complexity_mode": "complex",
            "first_monday": "2026-09-07",
            "people": [{"proposal_person_id": person["id"], "name": "Smith, Jane",
                        "role": "Manager FY26", "phase_name": "Validation"}],
        })
        self.assertEqual(converted.status_code, 201)
        engagement = converted.json["data"]["engagement"]
        self.assertEqual(engagement["engagement"]["engagement_code"], "ENG-FROM-PROP")
        self.assertEqual(engagement["engagement"]["complexity_mode"], "complex")
        self.assertEqual(engagement["engagement"]["engagement_lead"], "Lead, Alex")
        self.assertEqual(engagement["phases"][0]["phase_name"], "Validation")
        self.assertEqual(engagement["metrics"]["total_budgeted_hours"], 24)
        self.assertEqual(engagement["team"][0]["internal_rate"], 350)
        phase_id = engagement["phases"][0]["id"]
        detail = self.client.get(f"/api/engagements/{engagement['engagement']['id']}/phases/{phase_id}").json["data"]
        self.assertEqual(detail["grid"]["weeks"][0], "2026-09-07")

    def test_proposal_person_name_optional_at_creation_but_required_at_conversion(self):
        payload = self.proposal_payload("PROP-NONAME")
        payload["people"][0].pop("name")
        created = self.client.post("/api/proposals", json=payload)
        self.assertEqual(created.status_code, 201)
        pid = created.json["data"]["proposal"]["id"]
        person_id = created.json["data"]["people"][0]["id"]
        self.assertIn(created.json["data"]["people"][0]["name"], (None, ""))

        missing_name = self.client.post(f"/api/proposals/{pid}/convert", json={
            "engagement_code": "ENG-NONAME", "client_name": "No Name Client",
            "engagement_lead": "Lead, Alex", "complexity_mode": "simple",
            "first_monday": "2026-09-07",
            "people": [{"proposal_person_id": person_id, "name": ""}],
        })
        self.assertEqual(missing_name.status_code, 400)

        confirmed = self.client.post(f"/api/proposals/{pid}/convert", json={
            "engagement_code": "ENG-NONAME", "client_name": "No Name Client",
            "engagement_lead": "Lead, Alex", "complexity_mode": "simple",
            "first_monday": "2026-09-07",
            "people": [{"proposal_person_id": person_id, "name": "Smith, Jane"}],
        })
        self.assertEqual(confirmed.status_code, 201)

    def test_standard_rate_locks_once_referenced_by_a_team_member(self):
        created = self.client.post("/api/engagements", json={
            "engagement": {"engagement_code": "RATE-LOCK-1", "client_name": "Rate Client", "max_sow_fees": 10000},
            "team": [{"name": "Doe, Sam", "role": "Manager", "budgeted_hours": 10}],
        })
        self.assertEqual(created.status_code, 201)
        member = created.json["data"]["team"][0]
        self.assertEqual(member["internal_rate"], 350)

        locked_attempt = self.client.put("/api/settings/rate-cards", json={
            "name": "FY26 Governed Rates",
            "rates": [{"role_name": "Manager", "standard_rate": 400,
                       "engagement_rate": 300, "contract_rate": 280, "dte_rate": 320}],
        })
        self.assertEqual(locked_attempt.status_code, 409)
        self.assertEqual(locked_attempt.json["error"]["code"], "rate_locked")

        allowed_edit = self.client.put("/api/settings/rate-cards", json={
            "name": "FY26 Governed Rates",
            "rates": [{"role_name": "Manager", "standard_rate": 350,
                       "engagement_rate": 310, "contract_rate": 280, "dte_rate": 320}],
        })
        self.assertEqual(allowed_edit.status_code, 200)
        updated_rate = next(
            r for r in allowed_edit.json["data"]["rate_cards"][0]["rates"] if r["role_name"] == "Manager")
        self.assertEqual(updated_rate["engagement_rate"], 310)
        self.assertEqual(updated_rate["standard_rate"], 350)

    def test_new_rate_card_vintage_does_not_alter_existing_team_member_rates(self):
        created = self.client.post("/api/engagements", json={
            "engagement": {"engagement_code": "RATE-VINTAGE-1", "client_name": "Vintage Client", "max_sow_fees": 10000},
            "team": [{"name": "Lee, Kim", "role": "Manager", "budgeted_hours": 10}],
        })
        eid = created.json["data"]["engagement"]["id"]
        member_id = created.json["data"]["team"][0]["id"]
        self.assertEqual(created.json["data"]["team"][0]["internal_rate"], 350)

        new_card = self.client.post("/api/settings/rate-cards", json={
            "name": "FY27 Governed Rates",
            "rates": [{"role_name": "Manager", "standard_rate": 500,
                       "engagement_rate": 450, "contract_rate": 420, "dte_rate": 400}],
        })
        self.assertEqual(new_card.status_code, 201)
        card_id = new_card.json["data"]["rate_card"]["id"]
        activated = self.client.post(f"/api/settings/rate-cards/{card_id}/activate")
        self.assertEqual(activated.status_code, 200)
        active_cards = [c for c in activated.json["data"]["rate_cards"] if c["is_active"]]
        self.assertEqual(len(active_cards), 1)
        self.assertEqual(active_cards[0]["id"], card_id)

        team = self.client.get(f"/api/engagements/{eid}/team").json["data"]
        member = next(m for m in team if m["id"] == member_id)
        self.assertEqual(member["internal_rate"], 350)

    def test_reconciliation_updates_and_requires_confirmation_for_removals(self):
        data = self.create_complex("RECON-1")
        eid = data["engagement"]["id"]
        self.preview(eid, [
            self.import_row("T1", "A", "2026-07-12", 8, 1600, 1200),
            self.import_row("T2", "A", "2026-07-12", 4, 800, 600),
        ])
        self.assertEqual(self.client.post(f"/api/engagements/{eid}/import/commit", json={}).status_code, 201)
        corrected = self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 10, 2000, 1500)])
        self.assertEqual(corrected["rows_to_insert"], 0)
        self.assertEqual(corrected["rows_to_update"], 1)
        self.assertEqual(len(corrected["rows_to_remove"]), 1)
        blocked = self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        self.assertEqual(blocked.status_code, 409)
        committed = self.client.post(f"/api/engagements/{eid}/import/commit", json={"confirm_removals": True})
        self.assertEqual(committed.status_code, 201)
        self.assertEqual(committed.json["data"]["updated"], 1)
        self.assertEqual(committed.json["data"]["removed"], 1)
        self.assertEqual(self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["hours_to_date"], 10)

    def test_casefold_matching_and_every_exception_resolution_path(self):
        data = self.create_complex("EXCEPT-1")
        eid, phase_id = data["engagement"]["id"], data["phases"][0]["id"]
        known = self.import_row("KNOWN", "A", "2026-07-12", 2, 400, 300)
        known[2] = "  smith, JANE  "
        unknown = self.import_row("UNKNOWN", "", "2026-07-12", 3, 600, 450)
        unknown[2] = "Jones, Alex"
        preview = self.preview(eid, [known, unknown])
        self.assertNotIn("worker_unknown", preview["rows"][0]["flags"])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        current = self.client.get(f"/api/engagements/{eid}").json["data"]
        self.assertEqual(current["metrics"]["hours_to_date"], 5)
        exceptions = self.client.get(f"/api/engagements/{eid}/exceptions").json["data"]
        worker_exception = next(item for item in exceptions if item["exception_code"] == "worker_unknown")
        phase_exception = next(item for item in exceptions if item["exception_code"] == "unmatched_phase")
        assigned_team = self.client.post(
            f"/api/engagements/{eid}/exceptions/{worker_exception['id']}/assign-team", json={}
        )
        self.assertEqual(assigned_team.status_code, 200)
        assigned_phase = self.client.post(
            f"/api/engagements/{eid}/exceptions/{phase_exception['id']}/assign-phase",
            json={"phase_id": phase_id},
        )
        self.assertEqual(assigned_phase.status_code, 200)
        # Re-import creates a fresh pending exception that can be excluded from all totals.
        bad = self.import_row("BAD", "A", "2026-07-19", 7, 1400, 1050)
        bad[2] = "Wrong, Worker"
        self.preview(eid, [bad])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        bad_exception = next(item for item in self.client.get(
            f"/api/engagements/{eid}/exceptions").json["data"] if item["transaction_id"] == "BAD")
        excluded = self.client.post(
            f"/api/engagements/{eid}/exceptions/{bad_exception['id']}/exclude",
            json={"reason": "Charge belongs to another project"},
        )
        self.assertEqual(excluded.status_code, 200)
        self.assertEqual(self.client.get(f"/api/engagements/{eid}").json["data"]["metrics"]["hours_to_date"], 5)

    def test_allocation_rules_crud_and_sticky_rule_prompt_after_two_manual_assigns(self):
        # budgeted_hours=0: a staffed worker with exactly one candidate phase now auto-resolves
        # (allocation_method='staffing_match') instead of reaching the exceptions queue, which
        # this test needs to stay populated to exercise assign-phase/sticky-rule/allocation-rules.
        payload = self.complex_payload("ALLOC-1", 1)
        payload["team"][0]["budgeted_hours"] = 0
        data = self.client.post("/api/engagements", json=payload).json["data"]
        eid, phase_id, member_id = data["engagement"]["id"], data["phases"][0]["id"], data["team"][0]["id"]
        self.preview(eid, [
            self.import_row("A1", "Unknown Phase", "2026-07-12", 2, 400, 300),
            self.import_row("A2", "Unknown Phase", "2026-07-19", 3, 600, 450),
        ])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        exceptions = [item for item in self.client.get(f"/api/engagements/{eid}/exceptions").json["data"]
                      if item["exception_code"] == "unmatched_phase"]
        self.assertEqual(len(exceptions), 2)

        first = self.client.post(f"/api/engagements/{eid}/exceptions/{exceptions[0]['id']}/assign-phase",
                                 json={"phase_id": phase_id})
        self.assertEqual(first.status_code, 200)
        self.assertIsNone(first.json["data"]["offer_sticky_rule"])
        second = self.client.post(f"/api/engagements/{eid}/exceptions/{exceptions[1]['id']}/assign-phase",
                                  json={"phase_id": phase_id})
        self.assertEqual(second.json["data"]["offer_sticky_rule"], {"team_member_id": member_id, "phase_id": phase_id})

        created = self.client.post(f"/api/engagements/{eid}/allocation-rules",
                                   json={"team_member_id": member_id, "phase_id": phase_id})
        self.assertEqual(created.status_code, 201)
        rules = self.client.get(f"/api/engagements/{eid}/allocation-rules").json["data"]
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["team_member_name"], "Smith, Jane")
        rule_id = rules[0]["id"]

        # The rule now auto-applies on a fresh unmatched import for the same worker.
        self.preview(eid, [self.import_row("A3", "Unknown Phase", "2026-07-26", 1, 200, 150)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        after_rule = self.client.get(f"/api/engagements/{eid}/exceptions").json["data"]
        self.assertFalse(any(item["transaction_id"] == "A3" for item in after_rule
                             if item["exception_code"] == "unmatched_phase"))

        deleted = self.client.delete(f"/api/engagements/{eid}/allocation-rules/{rule_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get(f"/api/engagements/{eid}/allocation-rules").json["data"], [])

    def test_get_exceptions_returns_budget_candidates_and_memo_suggestion_independently(self):
        payload = self.complex_payload("ALLOC-2", 2)
        payload["team"][0]["budgeted_hours"] = 0
        created = self.client.post("/api/engagements", json=payload).json["data"]
        eid = created["engagement"]["id"]
        member_id = created["team"][0]["id"]
        phase_a_id = next(p["id"] for p in created["phases"] if p["phase_code"] == "A")
        phase_b_id = next(p["id"] for p in created["phases"] if p["phase_code"] == "B")
        # Both phases get a staffing signal that week, so the row stays genuinely ambiguous
        # (two candidates) rather than auto-resolving via the single-candidate staffing match.
        bulk = self.client.patch(f"/api/engagements/{eid}/forecasts/bulk", json={
            "team_member_ids": [member_id], "phase_ids": [phase_a_id, phase_b_id], "start_week": "2026-07-13",
            "end_week": "2026-07-13", "mode": "spread", "value": 10,
        })
        self.assertEqual(bulk.status_code, 200)
        row = self.import_row("M1", "Nonexistent Phase", "2026-07-19", 2, 400, 300)
        row[13] = "Nonexistent Task"
        row[-1] = "Charged under A per manager note"
        self.preview(eid, [row])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        exception = next(item for item in self.client.get(f"/api/engagements/{eid}/exceptions").json["data"]
                         if item["transaction_id"] == "M1")
        self.assertEqual(sorted(c["phase_id"] for c in exception["phase_candidates"]),
                        sorted([phase_a_id, phase_b_id]))
        self.assertEqual(exception["memo_suggestion"]["phase_id"], phase_a_id)

    def test_active_new_phase_is_editable_until_actual_posts_and_forecast_bulk_edit_is_independent(self):
        data = self.create_complex("PHASE-1")
        eid = data["engagement"]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 8, 1600, 1200)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        added = self.client.post(f"/api/engagements/{eid}/phases", json={
            "phase_name": "New delivery", "phase_code": "B", "sow_fees": 2000
        })
        self.assertEqual(added.status_code, 201)
        phase_id = next(item["id"] for item in added.json["data"] if item["phase_code"] == "B")
        self.assertEqual(self.client.put(f"/api/engagements/{eid}/phases/{phase_id}", json={"sow_fees": 2500}).status_code, 200)
        member_id = data["team"][0]["id"]
        bulk = self.client.patch(f"/api/engagements/{eid}/forecasts/bulk", json={
            "team_member_ids": [member_id], "phase_ids": [phase_id], "start_week": "2026-07-20",
            "end_week": "2026-08-03", "mode": "spread", "value": 30,
        })
        self.assertEqual(bulk.json["data"]["updated"], 3)
        detail = self.client.get(f"/api/engagements/{eid}/phases/{phase_id}").json["data"]
        self.assertEqual(sum(cell["forecasted_hours"] for cell in detail["grid"]["rows"][0]["cells"]), 30)
        self.assertEqual(sum(cell["budgeted_hours"] for cell in detail["grid"]["rows"][0]["cells"]), 0)
        self.preview(eid, [self.import_row("T2", "B", "2026-07-19", 1, 200, 150)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        locked = self.client.put(f"/api/engagements/{eid}/phases/{phase_id}", json={"sow_fees": 3000})
        self.assertEqual(locked.status_code, 409)

    def test_custom_rates_are_reason_gated_and_flat_tiers_use_governed_internal_rate(self):
        data = self.create_complex("RATE-1")
        eid, member_id = data["engagement"]["id"], data["team"][0]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 1, 350, 280)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        missing = self.client.put(f"/api/engagements/{eid}/team/{member_id}", json={
            "engagement_rate": 275, "is_custom_rate": True
        })
        self.assertEqual(missing.status_code, 400)
        changed = self.client.put(f"/api/engagements/{eid}/team/{member_id}", json={
            "engagement_rate": 275, "is_custom_rate": True, "custom_rate_reason": "Approved MSA"
        })
        self.assertEqual(changed.status_code, 200)
        revisions = self.client.get(f"/api/engagements/{eid}/revisions").json["data"]
        self.assertEqual(revisions[0]["reason"], "Approved MSA")

        flat = self.client.post("/api/engagements", json=self.simple_payload("RATE-FLAT")).json["data"]
        flat_id = flat["engagement"]["id"]
        self.client.put(f"/api/engagements/{flat_id}", json={"rate_mode": "flat_tiered"})
        tiers = self.client.put(f"/api/engagements/{flat_id}/rate-tiers", json={
            "tiers": [{"tier_name": "Delivery", "tier_amount": 210}]
        }).json["data"]
        member = self.client.post(f"/api/engagements/{flat_id}/team", json={
            "name": "Jones, Alex", "role": "Manager FY26", "rate_tier_id": tiers[0]["id"]
        }).json["data"][-1]
        self.assertEqual(member["internal_rate"], 350)
        self.assertEqual(member["engagement_rate"], 210)
        self.assertEqual(member["contract_rate"], 210)

    def test_overview_and_normalized_rate_card_routes_exist(self):
        data = self.create_complex("OVERVIEW-1")
        eid = data["engagement"]["id"]
        overview = self.client.get(f"/api/engagements/{eid}/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertEqual(len(overview.json["data"]["phases"]), 1)
        cards = self.client.get("/api/settings/rate-cards")
        self.assertEqual(cards.status_code, 200)
        self.assertGreater(len(cards.json["data"]["rate_cards"][0]["rates"]), 0)

    def create_complex(self, code):
        return self.client.post("/api/engagements", json=self.complex_payload(code, 1)).json["data"]

    def preview(self, eid, rows):
        text = "\n".join(["\t".join(EXPECTED_COLUMNS), *["\t".join(map(str, row)) for row in rows]])
        response = self.client.post(f"/api/engagements/{eid}/import/preview", json={"text": text})
        self.assertEqual(response.status_code, 200)
        return response.json["data"]

    def simple_payload(self, code):
        return {"engagement": {"engagement_code": code, "client_name": "Simple Client", "max_sow_fees": 10000},
                "team": [{"name":"Smith, Jane","role":"Manager","internal_rate":300,
                          "engagement_rate":280,"contract_rate":260,"budgeted_hours":40}]}

    def complex_payload(self, code, count):
        return {"engagement": {"engagement_code": code, "client_name": "Complex Client",
                "complexity_mode":"complex","first_monday":"2026-07-06","duration_weeks":4},
                "team": [{"name":"Smith, Jane","role":"Manager FY26","internal_rate":350,
                          "engagement_rate":300,"contract_rate":280,"dte_rate":320,"budgeted_hours":40}],
                "phases": [{"phase_name":f"Phase {index+1}","phase_code":chr(65+index),"sow_fees":6000}
                           for index in range(count)]}

    def import_row(self, transaction_id, phase, week_end, hours, std_fees, contract_fees):
        return [transaction_id,"W1","Smith, Jane","Manager FY26","BU","CC","2026-07-06",
                week_end,"2026-07","","Project","X",phase,"Task","Remote","Billable",
                hours,std_fees,contract_fees,"Memo"]

    def proposal_payload(self, code):
        return {
            "proposal": {
                "proposal_code": code,
                "client_name": "Proposal Client",
                "engagement_type": "Advisory",
                "first_monday": "2026-08-17",
                "duration_weeks": 2,
                "rate_basis": "standard",
                "discount_rate": 0,
                "notes": "Initial estimate",
            },
            "people": [
                {"name": "Smith, Jane", "role": "Manager FY26", "base_rate": 350,
                 "discount_rate": 0, "rough_rate": 350, "budgeted_hours": 24}
            ],
            "weekly_budgets": [
                {"person_index": 0, "week_start_date": "2026-08-17", "budgeted_hours": 12, "forecasted_hours": 12},
                {"person_index": 0, "week_start_date": "2026-08-24", "budgeted_hours": 12, "forecasted_hours": 12},
            ],
        }


if __name__ == "__main__":
    unittest.main()
