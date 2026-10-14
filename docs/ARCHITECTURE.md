# Architecture

ELISA Commons Host keeps five concerns deliberately separate.

## 1. Owner state
Human-readable, non-secret state:
- owner profile;
- explicit principles/preferences;
- selected local memory.

Owner state is portable and is not embedded in the model weights.

## 2. Model runtime
The inference model is replaceable.

The host configuration names:
- model name;
- endpoint;
- selected memory keys.

The default sovereignty profile treats loopback/local endpoints as the baseline and rejects
unapproved remote endpoints.

## 3. Authority
Tool visibility is not permission.

`CapabilityGrant` and `GovernedToolProxy` mediate actions by exact action/resource scope.

## 4. Evidence
Evidence is kept separate from model prose.

Missing required evidence -> ABSTAIN.
Contradictory evidence -> REVIEW.

## 5. Skills
Discovered/imported code is not trusted automatically.

Reference lifecycle:
QUARANTINED -> INSPECTED -> APPROVED / REJECTED.

## Portable bundle
`HostBundle` transports only selected owner state and configuration.

`EncryptedBundleEnvelope` can protect the portable bundle at rest using:
- scrypt;
- AES-256-GCM;
- authenticated associated data.

This does not encrypt the source SQLite database or secure a compromised running OS.
