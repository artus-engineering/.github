# Setup cached pnpm

Selects the highest completed pnpm tool-cache entry matching the project's
major version. A cache hit performs no downloads or package installation.
On a cache miss, `pnpm/action-setup` installs the requested major, including on
GitHub-hosted runners. Node and dependency-store caching remain the caller's
responsibility; use `actions/setup-node` with `cache: pnpm` after this action.

```yaml
- uses: actions/checkout@v7
- uses: artus-engineering/.github/actions/setup-pnpm@main
  # Optional: version: '12' under with; otherwise reads package.json.
- uses: actions/setup-node@v7
  with:
    node-version: '26'
    cache: pnpm
- run: pnpm install --frozen-lockfile
```

The cache layout is `$RUNNER_TOOL_CACHE/pnpm/<version>/<arch>/bin/pnpm`, with
an adjacent `<arch>.complete` marker. The full pnpm distribution belongs beside
the executable when the release includes support files. Architectures use the
runner's lowercase `RUNNER_ARCH`, such as `arm64` or `x64`.

`version` selects a major, even when passed an exact version. Without it, the
action reads `devEngines.packageManager` or `packageManager` from
`package_json_file` (default `package.json`). A conflicting major is an error.
CI disables pnpm's automatic switching to an exact manifest version for pnpm
9/10 and 11+, so a newer cached patch of the same major remains selected.

Cached pnpm can run before Node setup because the runner image supplies native
or standalone pnpm releases. The installer fallback needs Node/npm on PATH or
a completed Node entry in the tool cache. This action does not install project
dependencies or manage the pnpm dependency-store cache.
