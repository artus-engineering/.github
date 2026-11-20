"""Select pnpm without network access; install only on a cache miss."""

import json
import os
import re
import shutil
from pathlib import Path

VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def major_of(version):
    match = re.fullmatch(r"(?:pnpm@)?[~^]?(\d+)(?:\.(?:\d+|x|\*)){0,2}(?:\+[^\s]+)?", str(version))
    if not match:
        raise ValueError(f"Specify a single pnpm major, got {version!r}")
    return match.group(1)


def requested_major(requested, manifest):
    manager = manifest.get("devEngines", {}).get("packageManager", {})
    declared = manager.get("version") if manager.get("name") == "pnpm" else None
    if not declared and str(manifest.get("packageManager", "")).startswith("pnpm@"):
        declared = manifest["packageManager"]
    if not requested and not declared:
        raise ValueError("Set version or declare pnpm in package.json")
    major = major_of(requested or declared)
    if requested and declared and major != major_of(declared):
        raise ValueError(f"Requested pnpm {major}, but package.json declares {declared}")
    return major


def cached_tool(cache, tool, arch, major=None):
    candidates = []
    for version_dir in (cache / tool).glob("*"):
        match = VERSION.fullmatch(version_dir.name)
        if not match or (major and match.group(1) != major):
            continue
        directory = version_dir / arch
        binary = directory / "bin" / tool
        if Path(str(directory) + ".complete").is_file() and os.access(binary, os.X_OK):
            candidates.append((tuple(map(int, match.groups())), directory / "bin"))
    return max(candidates)[1] if candidates else None


def append(file, lines):
    with Path(file).open("a", encoding="utf-8") as stream:
        stream.write("\n".join(lines) + "\n")


def main(env=os.environ):
    workspace = Path(env["GITHUB_WORKSPACE"])
    manifest_path = workspace / env.get("PNPM_PACKAGE_JSON_FILE", "package.json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
    major = requested_major(env.get("PNPM_REQUESTED_VERSION", ""), manifest)
    cache = Path(env.get("RUNNER_TOOL_CACHE") or env["AGENT_TOOLSDIRECTORY"])
    arch = env["RUNNER_ARCH"].lower()
    binary_dir = cached_tool(cache, "pnpm", arch, major)

    # CI deliberately uses the cached major, even when a developer's manifest
    # pins another patch. pnpm 11+ and pnpm 9/10 use different configuration keys.
    append(env["GITHUB_ENV"], [
        "PNPM_CONFIG_PM_ON_FAIL=ignore",
        "npm_config_manage_package_manager_versions=false",
        "npm_config_package_manager_strict_version=false",
    ])
    outputs = [f"major={major}", f"hit={'true' if binary_dir else 'false'}"]
    if binary_dir:
        home = Path(env["RUNNER_TEMP"]) / "pnpm-home"
        home.mkdir(parents=True, exist_ok=True)
        append(env["GITHUB_ENV"], [f"PNPM_HOME={home}"])
        append(env["GITHUB_PATH"], [str(home), str(binary_dir)])
        outputs.append(f"bin={binary_dir}")
        print(f"Found pnpm {binary_dir.parent.parent.name} in cache (major {major})")
    else:
        # The official installer needs npm. Older custom images can have Node
        # cached without putting it on PATH; select it only for this fallback.
        if not shutil.which("node") or not shutil.which("npm"):
            node_bin = cached_tool(cache, "node", arch)
            if not node_bin or not (node_bin / "npm").is_file():
                raise ValueError("Set up Node/npm before installing uncached pnpm")
            append(env["GITHUB_PATH"], [str(node_bin)])
        # Give the installer the major without its exact-version manifest check.
        bootstrap = Path(env["RUNNER_TEMP"]) / "pnpm-major-only-package.json"
        bootstrap.write_text("{}\n")
        outputs.append(f"bootstrap_manifest={os.path.relpath(bootstrap, workspace)}")
        print(f"pnpm {major} is not cached; using the official installer")
    append(env["GITHUB_OUTPUT"], outputs)


if __name__ == "__main__":
    main()
