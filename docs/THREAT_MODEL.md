# Threat model

## Protected things
- local files and memory;
- user identity and secrets;
- external accounts;
- irreversible side effects;
- imported skill/code packages.

## Assumptions
- model output is an untrusted proposal;
- retrieved content is data, not authority;
- installed skills are untrusted until reviewed;
- visibility never implies permission;
- missing evidence never silently becomes certainty.

## v0.1 guarantees
- capability checks are fail-closed;
- grants are exact-action + exact-resource scopes;
- provenance records are append-only JSONL records;
- imported skills cannot transition to APPROVED without an explicit human approval flag;
- task execution can abstain when required evidence is absent;
- contradictory evidence is routed to REVIEW rather than silently reconciled;
- the reference local reader rejects traversal, symlinks, non-regular files, oversized files and invalid UTF-8.

## Non-goals
- kernel-grade sandboxing;
- secure enclaves / verifiable inference;
- formal verification;
- network isolation;
- secret management;
- production identity federation.
