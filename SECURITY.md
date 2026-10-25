# Security Policy

## Scope

GenomeGuard is a research and demonstration prototype. It is not approved for real participant data, clinical decisions, or production healthcare operations. The default demo intentionally exposes synthetic demo identities and may enable an audit-tampering exercise.

## Reporting a vulnerability

Please do not publish exploit details, credentials, or sensitive data in a public issue. If GitHub private vulnerability reporting is enabled for this repository, use the repository's **Security → Report a vulnerability** flow. Otherwise, contact the maintainer through the GitHub profile and ask for a private disclosure channel before sharing technical details.

Please include the affected commit or version, the impacted component, reproducible steps using synthetic data, and the practical security impact. Do not include real genomic data, participant identifiers, API keys, or other secrets.

There is no guaranteed response or remediation SLA. This project has not undergone an independent security audit, and a passing automated test suite is not a security certification.

## Safe testing

- Use synthetic data and isolated local environments.
- Do not test against systems or data you do not own or have explicit permission to assess.
- Do not use the demo mode, published demo credentials, or tamper controls with real participant data.
- Do not commit downloaded genomic cohorts, secrets, or participant identifiers.

## Deployment rules

- With `GG_DEMO_MODE=false` the server refuses to start unless `GG_ADMIN_API_KEY` is a unique secret of at least 32 characters, `GG_MASTER_KEY` is a base64-encoded 32-byte key, and `GG_ALLOW_TAMPER_DEMO=false`.
- Keep keys in a secret manager, never in the repository.
- Publish the audit head hash somewhere outside the system; otherwise a full rewrite of the database cannot be detected.

## Known limits

Epsilon accounting is sequential composition, not a formal accountant. The Paillier module is educational and unaudited. SQLite and in-process state mean a single writer. Consent records and requester identities are simulated. See [`docs/threat-model.md`](docs/threat-model.md).
