# GenomeGuard operational security policies (draft)

**Status:** Operational baseline for review; not an approved institutional policy or service-level commitment.  
**Applies to:** Maintainers and operators of development, staging and production environments.

## 1. Environment separation

- Local tests and public staging use synthetic data only.
- Public literature discovery may use public external APIs; queries must not contain patient-identifying or private genomic information.
- Production must use durable PostgreSQL, institution-controlled identity, managed keys, backups, monitoring and a documented incident process.
- Never copy production data into development or public staging.
- Do not use the production database or secrets in CI.
- A green preview or deployment is not a production-readiness approval.

## 2. Secrets and key management

- Store database URLs, API keys, OIDC secrets and encryption keys only in an approved secret manager.
- Use distinct keys per environment and purpose.
- Never commit secrets or print them in CI logs.
- Rotate after suspected disclosure, staff departure or scheduled key-lifecycle events.
- Document key owner, access approver, rotation date, recovery method and dependencies.
- Production encryption keys must be held by an institution-approved KMS/HSM; an environment variable is a prototype/staging control, not adequate production key custody.
- Test key rotation and recovery before relying on encrypted backups.

## 3. Access management

- Require institution-controlled authentication for controlled data.
- Verify organization membership and role server-side on every protected operation.
- Use least privilege and separate runtime, migration, backup and administrative database roles.
- Review privileged accounts and organization bindings at least quarterly and after role changes.
- Revoke accounts promptly after termination, contract end or suspected compromise.
- Require a separate steward decision and release authorization; no self-approval.

## 4. Retention and deletion

Retention periods must be set by the institution's controller/custodian and applicable law; GenomeGuard does not prescribe a universal period.

Before production, publish a schedule for:
- Raw VCF/genotype artifacts and temporary upload files.
- Derived datasets, aggregates and exports.
- Research queries and saved searches.
- Researcher identity and organization bindings.
- Consent evidence and withdrawal records.
- Governance decisions and audit records.
- Security logs, traces, backups and support records.

Deletion workflow:
1. Verify the requester's authority and scope.
2. Identify primary records, derived artifacts, caches, replicas and exports.
3. Apply the approved deletion/retention rule; preserve records only where a documented legal/audit basis requires it.
4. Propagate revocation/withdrawal to future access and release paths.
5. Record a minimal deletion/propagation receipt without copying the deleted sensitive content.
6. Confirm backup expiry or document the restore-time reapplication procedure.

Consent and audit history may be append-only for integrity; this does not automatically justify retaining all underlying genomic content indefinitely. The institution must define the lawful separation between immutable decision evidence and deletable participant data.

## 5. Incident response

### Severity guide
- **Critical:** confirmed or strongly suspected unauthorized access to restricted genomic/consent data, exposed production key, cross-tenant disclosure, or tampering of production audit history.
- **High:** suspected account compromise, privilege escalation, unauthorized release, major service compromise or loss of critical backups.
- **Medium:** limited confidential-data exposure, abuse, malware or service disruption without evidence of restricted data access.
- **Low:** non-sensitive defect with no evidence of unauthorized access or material service impact.

### Response sequence
1. **Triage:** record detection time, affected environment, reporter, suspected data categories and incident commander.
2. **Contain:** disable affected credentials/accounts, block the vulnerable path, isolate compromised workloads and preserve forensic evidence. Do not destroy evidence or rotate keys before documenting dependencies.
3. **Assess:** determine data subjects, organizations, records, access window, copies, exports, logs and backup exposure.
4. **Notify:** the institution's designated security/privacy/legal contacts decide regulatory, contractual and data-subject notifications and deadlines.
5. **Eradicate/recover:** patch, rotate keys, restore from verified backups if needed, and validate tenant isolation and audit integrity.
6. **Review:** document root cause, impact, evidence, decisions, remediation and prevention actions.
7. **Close:** only the institution's incident owner can accept residual risk and close a regulated-data incident.

Do not claim that a notification has been made or a legal deadline met unless the authorized institution confirms it.

## 6. Backup and recovery

- Backups of Restricted data must be encrypted and access-controlled.
- Separate backup credentials from runtime credentials.
- Record backup age, checksum, key version, database/schema version and restore procedure.
- Test isolated restoration at a documented cadence and after major schema/key changes.
- Define institution-approved RPO/RTO targets; none are promised by this prototype.
- Ensure consent withdrawals, access revocations and deleted records are reconciled after restore.
- A backup that cannot be decrypted after key rotation is not a successful backup.

## 7. Vulnerability disclosure

- Do not publish exploit details, credentials or sensitive data in public issues.
- Use GitHub private vulnerability reporting when enabled; otherwise request a private channel from the maintainer.
- Include affected commit, component, reproducible synthetic steps and impact.
- No remediation SLA is promised until an operator-approved service policy exists.
- Test only systems and data for which explicit authorization exists.

## 8. Operational readiness checklist

- [ ] Named service owner, security contact and privacy contact.
- [ ] Approved environment/data classification and retention schedule.
- [ ] Durable database, separated roles and verified tenant isolation.
- [ ] Managed keys, documented rotation and recovery.
- [ ] Encrypted backups and successful isolated restore.
- [ ] Monitoring, alerting, log minimization and access review.
- [ ] Incident response tabletop and notification decision tree.
- [ ] Vulnerability disclosure channel and patch process.
- [ ] Deployment rollback and exact-commit acceptance.
- [ ] Institution and independent reviewer sign-off.

Until these controls are approved and evidenced, GenomeGuard must be described as a research prototype/staging system, not an institutionally approved production service.
