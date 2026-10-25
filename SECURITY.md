# Security policy

GenomeGuard is a research prototype. It has had **no independent security review** and must not be
used with real participant data. See [`docs/threat-model.md`](docs/threat-model.md) for what it
defends against and what it does not.

## Reporting a vulnerability

Please open a private security advisory on GitHub (Security tab, "Report a vulnerability") rather
than a public issue. Include the affected commit, steps to reproduce, and the impact you expect.
Reports are handled on a best-effort basis; there is no bounty or service-level agreement.

## Deployment rules

- Demo mode publishes demo credentials and can enable the audit-tamper exercise. Use it only with
  synthetic data.
- With `GG_DEMO_MODE=false` the server refuses to start unless `GG_ADMIN_API_KEY` is a unique
  secret of at least 32 characters, `GG_MASTER_KEY` is a base64-encoded 32-byte key, and
  `GG_ALLOW_TAMPER_DEMO=false`.
- Keep keys in a secret manager, never in the repository. Publish the audit head hash somewhere
  outside the system, otherwise a full rewrite of the database cannot be detected.

## Known limits

Epsilon accounting is simple sequential composition, not a formal accountant. The Paillier module
is educational and unaudited. SQLite and in-process state mean a single writer. Consent records
and requester identities are simulated.
