"""固定部署入口的防误配置测试，不调用真实 Docker。"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class ComposeWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "project with spaces"
        (self.root / "deploy").mkdir(parents=True)
        deploy = Path(__file__).resolve().parents[2] / "deploy"
        for name in ("local.sh", "tencent.sh", "compose-common.sh"):
            shutil.copy2(deploy / name, self.root / "deploy" / name)
        for name in (".env", ".env.local", "docker-compose.yml", "docker-compose.local.yml", "docker-compose.tencent.yml"):
            (self.root / name).write_text("", encoding="utf-8")
        self.bin = Path(self.temporary.name) / "bin"
        self.bin.mkdir()
        docker = self.bin / "docker"
        docker.write_text('''#!/bin/sh
printf '%s\\n' "$@" > "$TASK_ARGS_FILE"
pwd > "$TASK_CWD_FILE"
printf '%s|%s|%s|%s' "${COMPOSE_FILE-unset}" "${COMPOSE_PROJECT_NAME-unset}" \
  "${COMPOSE_PROFILES-unset}" "${COMPOSE_ENV_FILES-unset}" > "$TASK_COMPOSE_ENV_FILE"
''', encoding="utf-8")
        docker.chmod(0o755)
        self.args_file = Path(self.temporary.name) / "args"
        self.cwd_file = Path(self.temporary.name) / "cwd"
        self.compose_env_file = Path(self.temporary.name) / "compose-env"
        self.environment = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "TASK_ARGS_FILE": str(self.args_file),
            "TASK_CWD_FILE": str(self.cwd_file),
            "TASK_COMPOSE_ENV_FILE": str(self.compose_env_file),
            "COMPOSE_FILE": "wrong.yml",
            "COMPOSE_PROJECT_NAME": "wrong-project",
            "COMPOSE_PROFILES": "cloudflare",
            "COMPOSE_ENV_FILES": "wrong.env",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, entry, *args):
        return subprocess.run([str(self.root / "deploy" / entry), *args],
            cwd=self.temporary.name, env=self.environment, capture_output=True, text=True)

    def test_targets_are_fixed_and_work_from_another_directory(self):
        for entry, env_file, project, overlay in (
            ("local.sh", ".env.local", "haitoo-test", "docker-compose.local.yml"),
            ("tencent.sh", ".env", "haitorok", "docker-compose.tencent.yml"),
        ):
            with self.subTest(entry=entry):
                result = self.invoke(entry, "exec", "api", "echo", "argument with spaces")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.args_file.read_text().splitlines(), [
                    "compose", "--env-file", env_file, "-p", project,
                    "-f", "docker-compose.yml", "-f", overlay,
                    "exec", "api", "echo", "argument with spaces",
                ])
                self.assertEqual(Path(self.cwd_file.read_text().strip()), self.root.resolve())
                self.assertEqual(self.compose_env_file.read_text(), "unset|unset|unset|unset")

    def test_environment_overrides_are_rejected_before_docker_runs(self):
        for entry in ("local.sh", "tencent.sh"):
            for override in ("--env-file", "--env-file=other.env", "-p", "-pother",
                "--project-name=other", "-f", "-fother.yml", "--file=other.yml",
                "--project-directory=other", "--profile=cloudflare"):
                with self.subTest(entry=entry, override=override):
                    result = self.invoke(entry, "up", override)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("禁止覆盖", result.stderr)
                    self.assertFalse(self.args_file.exists())

    def test_missing_target_env_never_falls_back_to_other_env(self):
        for entry, name in (("local.sh", ".env.local"), ("tencent.sh", ".env")):
            with self.subTest(entry=entry):
                (self.root / name).unlink()
                result = self.invoke(entry, "up", "-d")
                self.assertEqual(result.returncode, 2)
                self.assertIn("缺少文件", result.stderr)
                self.assertFalse(self.args_file.exists())
                (self.root / name).touch()

    def test_missing_compose_file_aborts(self):
        (self.root / "docker-compose.local.yml").unlink()
        result = self.invoke("local.sh", "ps")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.args_file.exists())

    def test_help_does_not_require_env_and_global_flags_are_rejected(self):
        (self.root / ".env.local").unlink()
        self.assertEqual(self.invoke("local.sh", "--help").returncode, 0)
        self.assertEqual(self.invoke("local.sh", "--env-file", "other.env", "ps").returncode, 2)
        self.assertFalse(self.args_file.exists())

    def test_logs_follow_remains_available(self):
        result = self.invoke("local.sh", "logs", "-f", "api")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.args_file.read_text().splitlines()[-3:], ["logs", "-f", "api"])


if __name__ == "__main__":
    unittest.main()
