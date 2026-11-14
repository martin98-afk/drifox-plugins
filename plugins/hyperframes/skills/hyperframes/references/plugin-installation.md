# Running from an installed DriFox plugin

This bundle is a DriFox plugin: the manifest is `<PLUGIN_ROOT>/.drifox-plugin/plugin.json`,
where `<PLUGIN_ROOT>` is the directory two levels above this file's skill
(`skills/hyperframes/references/` → up three → plugin root). The bundled skills are
fixed by the plugin version; DriFox has no skill auto-update, so never run
`hyperframes skills update`, `skills check`, or `npx skills add`. Report a missing
bundled skill instead of downloading a different release. Resolve every skill
reference inside this bundle.

## Running the CLI

Use `npx hyperframes <command>` exactly as the skills write it. Node.js 22.19+ or
24+ must be on PATH (verify with `node -v`); if it is missing, say so instead of
falling back to something else.

To pin the exact CLI release this plugin was built against (0.9.44), replace
`npx hyperframes` with:

```bash
node "<PLUGIN_ROOT>/skills/hyperframes/scripts/plugin-cli.mjs" <command> <args...>
```

The launcher reads the version from `<PLUGIN_ROOT>/plugin.json`, suppresses CLI
update notices and standalone skill installs, and forwards `--script <path>` to
bundled Node helpers. Prefer it when a project's own `node_modules` might otherwise
shadow the CLI. Either way, run in the user's project directory, never inside the
plugin directory.

## Project layout

Projects live wherever the user works. Do not write inside `<PLUGIN_ROOT>`; treat it
as read-only. Scaffold with `npx hyperframes init <dir>` from the user's directory.

## Telemetry

`npx hyperframes events --skill=<name>` reports anonymous usage. Skip it when the
user has telemetry disabled (`npx hyperframes telemetry`); nothing in the workflow
depends on it.

## Licensing

Bundled skills are Apache-2.0, Copyright 2026 HeyGen, Inc. See `LICENSE` at the
plugin root. The HyperFrames CLI is downloaded separately through npm under its own
terms.
