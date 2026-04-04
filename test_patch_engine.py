import unittest
from copy import deepcopy
from unittest.mock import patch

import sheetops_gws_demo as demo


class PatchEngineTests(unittest.TestCase):
    def test_build_sample_rows_returns_large_sector_dataset(self):
        rows = demo.build_sample_rows(row_count=120)

        self.assertEqual(len(rows), 120)
        self.assertEqual(len(rows[0]), len(demo.SAMPLE_HEADERS))
        self.assertIn("Diagnostics", rows[0][1])
        self.assertTrue(any(row[8] == "Disputed" for row in rows))
        self.assertTrue(any(row[6] == "" for row in rows))

    def test_map_headers_with_messy_business_labels(self):
        headers = [
            "Client Label",
            "Inv Amt (INR)",
            "Due Dt",
            "Days Late",
            "Last Touch",
            "Collector",
            "Payment Risk",
            "A/R State",
            "Region",
        ]
        mapping = demo.map_headers(headers)

        self.assertEqual(mapping["customer"], "Client Label")
        self.assertEqual(mapping["invoice_amount"], "Inv Amt (INR)")
        self.assertEqual(mapping["status"], "A/R State")
        self.assertEqual(mapping["owner"], "Collector")

    def test_map_headers_requires_customer_and_invoice_amount(self):
        with self.assertRaises(RuntimeError):
            demo.map_headers(["Foo", "Bar"])

    def test_normalize_status_variants(self):
        self.assertEqual(demo.normalize_status("Overdue"), "Overdue")
        self.assertEqual(demo.normalize_status("Promise to Pay"), "Promise to Pay")
        self.assertEqual(demo.normalize_status("Disputed"), "Disputed")
        self.assertEqual(demo.normalize_status("Paid"), "Paid")
        self.assertEqual(demo.normalize_status("Partial Pay"), "Partial Payment")
        self.assertEqual(demo.normalize_status(""), "Overdue")

    def test_plan_row_assigns_owner_and_priority(self):
        mapping = {
            "customer": "Client Label",
            "invoice_amount": "Inv Amt (INR)",
            "days_overdue": "Days Late",
            "last_follow_up": "Last Touch",
            "owner": "Collector",
            "risk": "Payment Risk",
            "status": "A/R State",
            "region": "Region",
        }
        row = {
            "Client Label": "Orbit Hotels",
            "Inv Amt (INR)": 150000,
            "Days Late": 21,
            "Last Touch": "",
            "Collector": "",
            "Payment Risk": "Medium",
            "A/R State": "Overdue",
            "Region": "East",
        }

        plan = demo.plan_row(row, mapping, row_index=0, prompt=demo.DEFAULT_PROMPT)

        self.assertIn(plan.priority, {"Critical", "High", "Medium", "Low"})
        self.assertEqual(plan.assigned_owner, "Karan")
        self.assertGreater(plan.projected_recoverable_cash, 0)
        self.assertRegex(plan.follow_up_eta, r"\d{4}-\d{2}-\d{2}")

    def test_build_patch_set_skips_paid_rows(self):
        headers = ["Client Label", "Inv Amt (INR)", "Days Late", "Collector", "Payment Risk", "A/R State", "Region"]
        rows = [
            {
                "Client Label": "Nova MedLabs",
                "Inv Amt (INR)": 45000,
                "Days Late": 20,
                "Collector": "Rohit",
                "Payment Risk": "Low",
                "A/R State": "Paid",
                "Region": "West",
            }
        ]
        mapping = {
            "customer": "Client Label",
            "invoice_amount": "Inv Amt (INR)",
            "days_overdue": "Days Late",
            "owner": "Collector",
            "risk": "Payment Risk",
            "status": "A/R State",
            "region": "Region",
        }

        patches, plans = demo.build_patch_set(headers, rows, mapping, demo.DEFAULT_PROMPT)
        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].priority, "Done")
        self.assertEqual(patches, [])

    def test_build_patch_set_does_not_mutate_input_rows(self):
        headers = ["Client Label", "Inv Amt (INR)", "Days Late", "Collector", "Payment Risk", "A/R State", "Region"]
        rows = [
            {
                "Client Label": "Apex Pharma",
                "Inv Amt (INR)": 165000,
                "Days Late": 21,
                "Collector": "",
                "Payment Risk": "High",
                "A/R State": "Overdue",
                "Region": "North",
            }
        ]
        mapping = {
            "customer": "Client Label",
            "invoice_amount": "Inv Amt (INR)",
            "days_overdue": "Days Late",
            "owner": "Collector",
            "risk": "Payment Risk",
            "status": "A/R State",
            "region": "Region",
        }

        original = deepcopy(rows)
        demo.build_patch_set(headers, rows, mapping, demo.DEFAULT_PROMPT)
        self.assertEqual(rows, original)

    def test_compose_effective_prompt_includes_profile_sections(self):
        profile = {
            "business_context": "Diagnostics network with aggressive DSO goals.",
            "business_logic": "Escalate >60 days overdue accounts.",
            "operating_style": "Act like a senior collections manager.",
        }
        prompt = demo.compose_effective_prompt("Build today's queue.", profile)

        self.assertIn("Build today's queue.", prompt)
        self.assertIn("Business context:", prompt)
        self.assertIn("Business logic and SOP:", prompt)
        self.assertIn("Employee operating style:", prompt)

    def test_assess_prompt_specificity_flags_short_prompt(self):
        assessment = demo.assess_prompt_specificity("Fix this", demo.DEFAULT_PROMPT_PROFILE)
        self.assertTrue(assessment["needs_decision"])
        self.assertTrue(assessment["details"])

    def test_map_headers_with_ai_can_require_openai(self):
        headers = ["Client Label", "Inv Amt (INR)"]
        rows = [{"Client Label": "Apex", "Inv Amt (INR)": 1000}]

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                demo.map_headers_with_ai(headers, rows, demo.DEFAULT_PROMPT, {}, require_ai=True)

    def test_build_source_snapshot_includes_row_and_tab_signals(self):
        values = [["Customer", "Amount"], ["Acme", 1000]]
        metadata = {
            "sheets": [
                {"properties": {"title": "Receivables Raw"}},
                {"properties": {"title": "Report"}},
            ]
        }
        snapshot = demo.build_source_snapshot(values, metadata)

        self.assertEqual(snapshot["row_count"], 1)
        self.assertEqual(snapshot["header_count"], 2)
        self.assertIn("signature", snapshot)
        self.assertIn("tabs_hash", snapshot)


if __name__ == "__main__":
    unittest.main()
