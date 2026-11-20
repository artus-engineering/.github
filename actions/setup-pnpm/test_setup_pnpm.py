import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pnpm_select", Path(__file__).with_name("setup_pnpm.py"))
selector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selector)


class SelectionTest(unittest.TestCase):
    def test_major_from_exact_package_manager_and_integrity(self):
        self.assertEqual(selector.requested_major("", {"packageManager": "pnpm@12.18.0+sha512.test"}), "12")
        self.assertEqual(selector.requested_major("12", {"packageManager": "pnpm@12.18.0"}), "12")
        self.assertEqual(selector.requested_major("", {"devEngines": {"packageManager": {"name": "pnpm", "version": "^11.20.0"}}}), "11")

    def test_conflicting_major_and_ambiguous_ranges_fail(self):
        with self.assertRaises(ValueError):
            selector.requested_major("11", {"packageManager": "pnpm@12.18.0"})
        for value in [">=11 <13", "latest", "12\nhit=true", ""]:
            with self.assertRaises(ValueError):
                selector.major_of(value)

    def cache_entry(self, root, tool, version, arch="arm64", complete=True):
        directory = root / tool / version / arch
        (directory / "bin").mkdir(parents=True)
        binary = directory / "bin" / tool
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)
        if complete:
            Path(str(directory) + ".complete").touch()
        return directory / "bin"

    def test_only_highest_completed_version_in_the_requested_major_and_arch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.cache_entry(root, "pnpm", "12.9.0")
            expected = self.cache_entry(root, "pnpm", "12.21.0")
            self.cache_entry(root, "pnpm", "12.99.0", complete=False)
            self.cache_entry(root, "pnpm", "13.0.0")
            self.cache_entry(root, "pnpm", "12.30.0", arch="x64")
            self.assertEqual(selector.cached_tool(root, "pnpm", "arm64", "12"), expected)
            self.assertIsNone(selector.cached_tool(root, "pnpm", "arm64", "11"))

    def test_cache_hit_sets_path_and_disables_exact_patch_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.cache_entry(root / "cache", "pnpm", "12.21.0")
            (root / "package.json").write_text(json.dumps({"packageManager": "pnpm@12.18.0"}))
            env = {"GITHUB_WORKSPACE": str(root), "RUNNER_TEMP": str(root / "temp"),
                   "RUNNER_TOOL_CACHE": str(root / "cache"), "RUNNER_ARCH": "ARM64",
                   "GITHUB_ENV": str(root / "env"), "GITHUB_PATH": str(root / "path"),
                   "GITHUB_OUTPUT": str(root / "output")}
            with patch.object(selector.shutil, "which", side_effect=AssertionError("cache hit should not bootstrap Node")):
                selector.main(env)
            self.assertIn("hit=true", (root / "output").read_text())
            self.assertIn(str(binary), (root / "path").read_text())
            self.assertIn("PNPM_CONFIG_PM_ON_FAIL=ignore", (root / "env").read_text())
            self.assertIn("npm_config_manage_package_manager_versions=false", (root / "env").read_text())
            self.assertFalse((root / "temp/pnpm-major-only-package.json").exists())

    def test_cache_miss_bootstraps_node_from_cache_and_supplies_major_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = self.cache_entry(root / "cache", "node", "26.13.1")
            (binary / "npm").touch()
            (root / "temp").mkdir()
            (root / "package.json").write_text('{"packageManager":"pnpm@10.12.1"}')
            env = {"GITHUB_WORKSPACE": str(root), "RUNNER_TEMP": str(root / "temp"),
                   "RUNNER_TOOL_CACHE": str(root / "cache"), "RUNNER_ARCH": "ARM64",
                   "GITHUB_ENV": str(root / "env"), "GITHUB_PATH": str(root / "path"),
                   "GITHUB_OUTPUT": str(root / "output")}
            with patch.object(selector.shutil, "which", return_value=None):
                selector.main(env)
            output = (root / "output").read_text()
            self.assertIn("hit=false", output)
            self.assertIn("major=10", output)
            self.assertIn(str(binary), (root / "path").read_text())
            self.assertEqual(json.loads((root / "temp/pnpm-major-only-package.json").read_text()), {})


if __name__ == "__main__":
    unittest.main()
