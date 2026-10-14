# Contributing

ELISA Commons is a pre-release public-goods component focused on local-first ownership,
explicit authority, provenance and safe skill/tool integration.

## Ground rules
- Keep model output separate from authorization decisions.
- Fail closed when authority or required evidence is missing.
- Preserve contradictions instead of silently reconciling them.
- Add tests for every observable security/governance behavior.
- Do not add network dependencies to the baseline path without making them optional.
- Do not introduce automatic execution of imported skills.

## Development
```bash
python -m pip install pytest
python -m pytest -q
```

## Security-sensitive changes
Changes to capability checks, resource access, skill activation, receipt generation or
provenance semantics should include adversarial tests and explicit threat-model notes.
