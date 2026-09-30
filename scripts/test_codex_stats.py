import datetime as dt
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

spec = importlib.util.spec_from_file_location("stats", Path(__file__).with_name("update_codex_stats.py"))
stats = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stats)


class ProfileStatsTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 29, 12, tzinfo=stats.ZONE)
        metrics = {key: 1 for key in stats.METRICS}
        metrics.update(lifetime_tokens=698745204, peak_daily_tokens=171724138,
                       current_streak_days=128, longest_streak_days=128,
                       total_threads=578, longest_running_turn_sec=1632,
                       most_used_reasoning_effort="medium",
                       most_used_reasoning_effort_percentage=45.7074,
                       daily_usage_buckets=[{"start_date": "2026-09-29", "tokens": 216410}],
                       top_invocations=[{"type": "skill", "skill_name": "imagegen",
                                         "usage_count": 13, "skill_id": "PRIVATE_SENTINEL"}])
        self.response = {"profile": {"display_name": "MotoChase", "username": "motochase",
                                     "email": "PRIVATE_SENTINEL"}, "stats": metrics,
                         "metadata": {}, "account_id": "PRIVATE_SENTINEL"}

    def data(self):
        return stats.public_data(self.response, self.now)

    def test_only_public_fields_are_retained(self):
        data = self.data()
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(data))
        self.assertNotIn("motochase", json.dumps(data).lower())
        self.assertEqual(data["stats"]["lifetime_tokens"], 698745204)
        self.assertEqual(data["stats"]["total_threads"], 578)

    def test_invalid_or_failed_stats_are_rejected(self):
        self.response["metadata"]["stats_error"] = "temporary failure"
        with self.assertRaises(ValueError): self.data()
        self.response["metadata"] = {}
        for invalid in (-1, True, float("nan")):
            self.response["stats"]["lifetime_tokens"] = invalid
            with self.assertRaises(ValueError): self.data()

    def test_card_escapes_text_and_renders_correct_values(self):
        data = self.data()
        data["stats"]["top_invocations"][0]["name"] = "<Image & Gen>"
        data["updated_at"] = self.now.isoformat()
        root = ET.fromstring(stats.render_card(data))
        text = "".join(root.itertext())
        for value in ("<Image & Gen>", "ChatGPT + Codex", "698.7M", "171.7M", "128 days", "27m 12s"):
            self.assertIn(value, text)
        self.assertGreater(len(root.findall(".//{http://www.w3.org/2000/svg}rect")), 350)

    def test_unchanged_data_does_not_write_to_github(self):
        data = self.data()
        old = dict(data, updated_at=self.now.isoformat())
        import base64
        encoded = base64.b64encode(json.dumps(old).encode()).decode()
        with patch.object(stats, "gh_api", side_effect=[
                {"object": {"sha": "old"}}, {"tree": {"sha": "old-tree"}},
                {"content": encoded}]) as api:
            stats.publish(data)
        self.assertTrue(all(call.args[1:] == () for call in api.call_args_list))

    def test_updated_assets_share_one_commit_without_force(self):
        with patch.object(stats, "gh_api", side_effect=[
                {"object": {"sha": "old"}}, {"tree": {"sha": "old-tree"}}, None,
                {"sha": "new-tree"}, {"sha": "new-commit"}, {}]) as api:
            stats.publish(self.data())
        tree = api.call_args_list[3].args[2]["tree"]
        self.assertEqual({item["path"] for item in tree},
                         {"assets/codex-stats.json", "assets/codex-activity-v2.svg"})
        self.assertEqual(api.call_args_list[4].args[2]["parents"], ["old"])
        self.assertEqual(api.call_args_list[5].args[2], {"sha": "new-commit", "force": False})


if __name__ == "__main__":
    unittest.main()
