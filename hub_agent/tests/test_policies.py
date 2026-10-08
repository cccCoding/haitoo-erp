import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from policies import candidates, validate_policy
from workbench import ERPRequestError


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.environments = [{"container_code": "10", "name": "环境10"}, {"container_code": "11", "name": "环境11"}]
        self.policy = {"template_id": 1, "container_codes": ["10", "11"], "mode": "round_robin"}

    def test_rotation_restart_busy_and_single_environment(self):
        policies = {"1": self.policy | {"last_container_code": "10"}}
        choices, reason = candidates({"template_id": 1}, policies, self.environments)
        self.assertEqual([e["container_code"] for e in choices], ["11", "10"])
        self.assertIsNone(reason)
        self.assertEqual(candidates({"template_id": 1}, policies, self.environments, ["11"])[0], [self.environments[0]])
        self.assertEqual(candidates({"template_id": 1}, policies, self.environments, ["10", "11"])[1], "无可用环境")
        self.assertEqual(candidates({"template_id": 1}, {"1": self.policy | {"container_codes": ["10"]}}, self.environments)[0], [self.environments[0]])

    def test_random_is_applied_only_to_allowed_available_environments(self):
        def reverse(values): values.reverse()
        with patch("policies.random.shuffle", side_effect=reverse) as shuffle:
            choices, _ = candidates({"template_id": 1}, {"1": self.policy | {"mode": "random"}}, self.environments)
        shuffle.assert_called_once()
        self.assertEqual(choices, list(reversed(self.environments)))

    def test_unknown_unmatched_and_retry_never_switches(self):
        policies = {"1": self.policy}
        self.assertIn("模版未知", candidates({}, policies, self.environments)[1])
        self.assertEqual(candidates({"template_id": 2}, policies, self.environments)[1], "未配置策略")
        task = {"template_id": 1, "container_code": "11"}
        self.assertEqual(candidates(task, policies, self.environments)[0], [self.environments[1]])
        self.assertEqual(candidates(task, policies, self.environments[:1])[1], "无可用环境")
        self.assertEqual(candidates(task, {"1": self.policy | {"container_codes": ["10"]}}, self.environments)[1], "原环境不在策略中")

    def test_validation_defaults_and_unavailable_previous_environment(self):
        templates = [{"id": 1, "name": "M05L"}]
        policy = validate_policy({"template_id": 1, "container_codes": ["10"]}, templates, self.environments)
        self.assertEqual(policy["mode"], "round_robin")
        for payload in ({"template_id": True, "container_codes": ["10"]}, {"template_id": 2, "container_codes": ["10"]}, {"template_id": 1, "container_codes": []}, {"template_id": 1, "container_codes": ["10", "10"]}, {"template_id": 1, "container_codes": ["foreign"]}, {"template_id": 1, "container_codes": ["10"], "mode": []}):
            with self.assertRaises(ERPRequestError): validate_policy(payload, templates, self.environments)
        preserved = validate_policy({"template_id": 1, "container_codes": ["11"]}, templates, self.environments[:1], self.policy)
        self.assertEqual(preserved["container_codes"], ["11"])
