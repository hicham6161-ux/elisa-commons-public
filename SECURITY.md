# Security policy

ELISA Commons Host is a pre-release reference implementation and is **not** a production security boundary.

Do not rely on it to protect:
- money or payment authorization;
- credentials or production secrets;
- regulated/sensitive production data;
- production infrastructure;
- irreversible external effects.

## Reporting

Please avoid posting active secrets, private memory, or exploit details in public issues.

When private vulnerability reporting is enabled for this repository, use GitHub's private security-advisory flow for security-sensitive reports.

## Current boundary

The repository includes reference mechanisms for capability checks, provenance, selective memory export, encrypted portable bundles, and skill review. These are engineering primitives, not a formal security proof.

See `docs/THREAT_MODEL.md` and `docs/PRIVACY.md`.
