# Privacy model

## Default goals
- local memory;
- selective export;
- no ambient remote model endpoint;
- no automatic skill activation;
- no raw content in decision receipts.

## Selective memory
A host bundle includes only keys explicitly listed in `HostConfig.memory_keys`.

Other SQLite keys remain outside:
- prompt construction;
- bundle export.

## Encrypted portable bundle
The encrypted bundle protects the exported JSON payload at rest.

Current construction:
- scrypt KDF;
- 256-bit AES-GCM key;
- random salt;
- random nonce;
- authenticated associated data.

## Out of scope
v0.5 does not protect against:
- malware with access to the running process;
- local account compromise;
- memory scraping;
- keyboard capture;
- a weak password;
- a compromised Python runtime;
- unencrypted source databases.

The project should continue to describe these boundaries explicitly.
