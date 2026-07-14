# Skill Sync v1 Fixtures

Status: shared pre-release fixtures for manifest, bundle, and response formats versioned under the `v1` folder.

Backend and CLI tests load repository-local mirrors with one shared corpus fingerprint.

`catalog.json` is the entry point for response, manifest, bundle, archive, and hash-vector fixtures.

The canonical generator is `../generate_v1.py` in the backend repository.

Run that generator only while the v1 fixture corpus is unreleased.

It refreshes the backend, CLI, and optional workspace mirrors from one source.

After release, existing fixture meaning and bytes are immutable.

The generator contains no customer data and uses only synthetic identities and content.

Compatibility is enforced by `/api/v1` routes, minimum CLI version checks, and embedded manifest or local schema `format_version` values — not a separate transport contract version.
