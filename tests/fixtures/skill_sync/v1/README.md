# Skill Sync Contract v1 Fixtures

Status: shared pre-release fixtures for sync contract version `1`.

Backend and CLI tests load repository-local mirrors with one shared corpus fingerprint.

`catalog.json` is the entry point for response, manifest, bundle, archive, and hash-vector fixtures.

The canonical generator is `../generate_v1.py` in the backend repository.

Run that generator only while contract v1 is unreleased.

It refreshes the backend, CLI, and optional workspace mirrors from one source.

After contract v1 releases, existing fixture meaning and bytes are immutable.

The generator contains no customer data and uses only synthetic identities and content.
