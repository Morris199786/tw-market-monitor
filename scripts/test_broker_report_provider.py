import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from report_plan_worker import reached_limit
from report_provider import NoReportCapacity, complete_report
from update_reports_ai_eps import normalize_financial


@patch.dict(os.environ, {"REPORT_AI_ROUTE": "plan-first", "OPENAI_API_KEY": "test"})
class RoutingTest(unittest.TestCase):
    @patch("requests.post")
    @patch("report_provider.plan_request")
    def test_success_and_unconfirmed_errors_never_call_api(self, plan, api):
        plan.return_value = {"status": "ok", "text": "report"}
        self.assertEqual(complete_report({}), "report")
        plan.return_value = {"status": "error"}
        with self.assertRaises(RuntimeError):
            complete_report({})
        plan.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            complete_report({})
        api.assert_not_called()

    @patch("requests.post")
    @patch("report_provider.plan_request", return_value={"status": "plan_limit"})
    def test_only_confirmed_limit_uses_original_payload(self, plan, api):
        payload = {"input": ["original"]}
        api.return_value = Mock(status_code=200)
        api.return_value.json.return_value = {"output": [{"content": [{"type": "output_text", "text": "ok"}]}]}
        self.assertEqual(complete_report(payload), "ok")
        self.assertEqual(api.call_args.kwargs["json"], payload)
        api.return_value.status_code = 429
        api.return_value.json.return_value = {"error": {"code": "insufficient_quota"}}
        with self.assertRaises(NoReportCapacity):
            complete_report(payload)

    def test_limit_requires_failed_turn(self):
        msg = {"message": "You've hit your usage limit. Try again later."}
        self.assertTrue(reached_limit({"type": "turn.failed", "error": msg}))
        self.assertFalse(reached_limit({"type": "item.completed", "error": msg}))
        self.assertFalse(reached_limit({"type": "turn.failed", "error": {"message": "429 rate limit"}}))

    def test_other_metrics_stay_distinct(self):
        row = dict(period="2026", metric="other", type="actual", unit="億元", value=7,
                   evidence="報告列示 2026 年實際數值")
        facts = normalize_financial([dict(row, metric_name=k) for k in ["現金流", "存貨"]])
        self.assertEqual([f["metric_name"] for f in facts], ["現金流", "存貨"])
