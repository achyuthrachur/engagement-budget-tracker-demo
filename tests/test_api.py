from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from importers import EXPECTED_COLUMNS


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.temp_dir.name) / "api.db"
        self.app = create_app(str(self.db_file))
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_engagement_and_duplicate_code(self):
        payload = self._engagement_payload("P100")
        created = self.client.post("/api/engagements", json=payload)
        self.assertEqual(created.status_code, 201)
        self.assertIsNone(created.json["error"])
        duplicate = self.client.post("/api/engagements", json=payload)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json["error"]["code"], "duplicate_engagement_code")

    def test_missing_required_field_uses_error_envelope(self):
        response = self.client.post("/api/engagements", json={"engagement_code": "P100"})
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(response.json["data"])
        self.assertIn("client_name", response.json["error"]["fields"])

    def test_reimporting_full_export_skips_duplicate_transaction_ids(self):
        created = self.client.post("/api/engagements", json=self._engagement_payload("P100"))
        engagement_id = created.json["data"]["engagement"]["id"]
        text = self._import_text()

        first_preview = self.client.post(
            f"/api/engagements/{engagement_id}/import/preview", json={"text": text}
        )
        self.assertEqual(first_preview.status_code, 200)
        self.assertEqual(first_preview.json["data"]["summary"]["to_import"], 2)
        first_commit = self.client.post(
            f"/api/engagements/{engagement_id}/import/commit", json={"notes": "first"}
        )
        self.assertEqual(first_commit.status_code, 201)
        self.assertEqual(first_commit.json["data"]["imported"], 2)
        self.assertEqual(first_commit.json["data"]["duplicates"], 0)

        second_preview = self.client.post(
            f"/api/engagements/{engagement_id}/import/preview", json={"text": text}
        )
        self.assertEqual(second_preview.status_code, 200)
        self.assertEqual(second_preview.json["data"]["summary"]["total"], 2)
        self.assertEqual(second_preview.json["data"]["summary"]["duplicates"], 2)
        self.assertEqual(second_preview.json["data"]["summary"]["to_import"], 0)
        second_commit = self.client.post(
            f"/api/engagements/{engagement_id}/import/commit", json={"notes": "second"}
        )
        self.assertEqual(second_commit.status_code, 200)
        self.assertEqual(second_commit.json["data"]["imported"], 0)
        self.assertEqual(second_commit.json["data"]["duplicates"], 2)

        snapshots = self.client.get(f"/api/engagements/{engagement_id}/snapshots")
        self.assertEqual(len(snapshots.json["data"]), 1)
        self.assertEqual(snapshots.json["data"][0]["row_count"], 2)
        engagement = self.client.get(f"/api/engagements/{engagement_id}")
        self.assertEqual(engagement.json["data"]["metrics"]["hours_to_date"], 3.0)
        weekly = engagement.json["data"]["weekly_summary"]
        self.assertEqual(len(weekly), 1)
        self.assertEqual(weekly[0]["week_end_date"], "2023-07-22")
        self.assertEqual(weekly[0]["hours"], 3.0)
        self.assertEqual(weekly[0]["entries"], 2)

    def _engagement_payload(self, code: str):
        return {
            "engagement": {
                "engagement_code": code,
                "client_name": "Client",
                "max_sow_fees": 10000,
            },
            "team": [
                {
                    "name": "Smith, Jane",
                    "role": "Manager",
                    "internal_rate": 300,
                    "engagement_rate": 350,
                    "budgeted_hours": 10,
                }
            ],
        }

    def _import_text(self) -> str:
        rows = [
            [
                "T1",
                "W1",
                "Smith, Jane",
                "Manager",
                "",
                "",
                "45123",
                "45129",
                "2026-06",
                "P100",
                "Project",
                "P100",
                "Phase",
                "Task",
                "Remote",
                "Billable",
                "1.0",
                "350",
                "350",
                "Memo 1",
            ],
            [
                "T2",
                "W1",
                "Smith, Jane",
                "Manager",
                "",
                "",
                "45124",
                "45129",
                "2026-06",
                "P100",
                "Project",
                "P100",
                "Phase",
                "Task",
                "Remote",
                "Billable",
                "2.0",
                "700",
                "700",
                "Memo 2",
            ],
        ]
        return "\n".join(["\t".join(EXPECTED_COLUMNS), *["\t".join(row) for row in rows]])


if __name__ == "__main__":
    unittest.main()
