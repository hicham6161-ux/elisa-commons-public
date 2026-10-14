# ELISA Commons Host

**Version:** 0.5.0  
**Status:** pre-release reference implementation

ELISA Commons Host is a local-first owner layer for personal AI.

Its core design rule is:

`OWNER STATE != MODEL != AUTHORITY != EVIDENCE`

The project explores a simple idea: a person's durable AI state should remain portable even when the underlying model, provider, or machine changes.

## What v0.5 includes

- local SQLite memory;
- portable owner profile and selected-memory export;
- replaceable model endpoints, including an Ollama-compatible local adapter;
- sovereignty checks that can reject unapproved remote endpoints;
- exact capability grants and a governed tool proxy;
- `ABSTAIN` for missing required evidence;
- `REVIEW` for contradictory evidence;
- skill quarantine → inspection → explicit human approval;
- hash-linked provenance records and content-addressed decision receipts;
- portable owner-state bundles;
- encrypted owner-state bundles using scrypt + AES-256-GCM.

## Why this exists

Many personal-AI systems couple the user's memory and continuity to a specific hosted product.

ELISA Commons separates the durable owner layer from inference. The reference host can export selected owner state, restore it into a fresh local memory store, and continue with a different compatible model configuration.

That does **not** prove human-level continuity or production security. It demonstrates a concrete, inspectable portability primitive.

## Install for development

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e .
python -m pip install pytest
```

## Run the test suite

```bash
python -m pytest -q
```

Current local reference result:

**66 passed / 0 failed**

## Run the demo

```bash
python -m elisa_commons.demo
```

Or use the CLI entry point after installation:

```bash
elisa-commons demo
```

## Main components

- `LocalMemory` — local SQLite memory.
- `OwnerProfile` / `HostBundle` — portable owner state.
- `EncryptedBundleEnvelope` — authenticated encrypted export.
- `LocalModelRegistry` — local vs remote endpoint classification.
- `CapabilityGate` — exact action/resource grants.
- `GovernedToolProxy` — evidence + authority checks before a tool effect.
- `EvidenceLedger` — append-only hash-linked provenance.
- `DecisionReceipt` — content-addressed decision evidence.
- `SkillVault` — quarantined skill review workflow.
- `LocalResourceReader` — bounded strict-UTF-8 local reads.

## Security boundary

This is **not** a production security boundary.

Do not rely on it to protect money, credentials, regulated data, production infrastructure, or irreversible effects.

See [SECURITY.md](SECURITY.md) and [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md).

## Privacy model

The reference host exports only explicitly selected memory keys. Encrypted bundles protect the exported bundle at rest, not a compromised running OS, process, keyboard, or source database.

See [docs/PRIVACY.md](docs/PRIVACY.md).

## Project direction

The next milestones focus on:

- stable/versioned owner-state schema;
- revocable/expiring tool grants;
- local runtime/model discovery;
- stronger cross-platform resource identity;
- encrypted backup/recovery hardening;
- external testing and interoperability with open agent ecosystems.

See [ROADMAP.md](ROADMAP.md).

## Licence

A final open-source licence has not yet been activated in this repository. Apache-2.0 is the current candidate pending explicit project-owner approval.
