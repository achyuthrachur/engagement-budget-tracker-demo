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
        data = self.create_complex("C-3")
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

    def test_active_roster_cannot_bypass_budget_lock(self):
        data = self.create_complex("C-7")
        eid = data["engagement"]["id"]
        self.preview(eid, [self.import_row("T1", "A", "2026-07-12", 8, 800, 600)])
        self.client.post(f"/api/engagements/{eid}/import/commit", json={})
        blocked = self.client.post(f"/api/engagements/{eid}/team", json={
            "name": "Jones, Alex", "role": "Senior", "budgeted_hours": 80
        })
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json["error"]["code"], "budget_locked")

    def test_closed_engagement_mutations_are_rejected(self):
        data = self.create_complex("C-8")
        eid, phase_id = data["engagement"]["id"], data["phases"][0]["id"]
        expense = self.client.post(f"/api/engagements/{eid}/expenses", json={
            "expense_type": "crowe_paid", "amount": 100
        }).json["data"][0]
        self.assertEqual(self.client.put(f"/api/engagements/{eid}", json={"status": "closed"}).status_code, 200)
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
        self.assertEqual(len(loaded.json["data"]["engagements"]), 3)

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
                week_end,"2026-07","C-IGNORED","Project","X",phase,"Task","Remote","Billable",
                hours,std_fees,contract_fees,"Memo"]


if __name__ == "__main__":
    unittest.main()
