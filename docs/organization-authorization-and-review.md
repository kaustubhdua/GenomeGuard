# Organization authorization and review workflow

## Scope

Migration `20261029180000_genomeguard_organization_consent_workflows.sql` adds server-side organization and membership records, an evidence-backed participant-consent ledger, organization-scoped request records, and a reviewer action.

No organizations, memberships, consent records, or participants are seeded. A new Supabase Auth user is not automatically a researcher or reviewer. Until a trusted operator provisions and activates the appropriate organization and membership, request submission fails closed.

## Authorization rules

- The requester's role and institution are resolved from the active server-side membership and organization, not trusted from browser fields.
- A user must have exactly one active organization membership to submit a request. Multiple active memberships fail closed rather than selecting an organization silently.
- A reviewer must have an active `reviewer` or `organization_admin` membership.
- Review actions are limited to requests belonging to the reviewer's organization.
- Review decisions are persisted to `genomeguard.decisions`, update request status, and append an `api_events` record.
- Approval transitions to `approved_pending_release`; it does not release genomic data.
- The membership and consent tables have RLS enabled and no direct grants to browser roles.
- The RPCs are executable only by `service_role`; the Edge Function validates the Supabase bearer token and supplies the verified user ID server-side.

## Request review API

`POST /requests/{request_id}/review`

Request JSON:

```json
{
  "outcome": "approved",
  "reason": "The stated research purpose meets the reviewed criteria; release remains separately gated."
}
```

Allowed outcomes: `approved`, `denied`, `needs_more_information`. Every outcome requires a reason. The API returns a generic authorization/unavailability error when the RPC fails, without disclosing cross-organization request existence.

## Consent ledger limitations

`participant_consent_records` supports scoped evidence references, allowed purposes/data levels, verification metadata, expiry and withdrawal status. It does not itself verify a source document, identify a real-world person, or automatically authorize data release. The table is empty until consent evidence is verified through an approved governance process. No private participant data should be imported into this shared research project.

Participant consent withdrawal must be wired into the full authorization decision path before participant-specific data workflows are enabled. The current schema and request/review endpoints are not a claim that this complete path is already operational.

## Provisioning and deployment

Membership provisioning must be performed through a separately authorized administrative procedure; there is no public endpoint to create organizations, promote roles, or create consent evidence. The migration is not applied to the live project until its CI checks and review pass. Do not mark production readiness true until the deployed Edge Function, database grants, live negative tests, consent lifecycle and recovery controls are independently verified.


## Consent withdrawal API

`POST /consents/{consent_uuid}/withdraw`

Request JSON:

```json
{ "reason": "Withdrawal recorded by the authorized consent steward." }
```

The route requires a valid Supabase bearer token and an active reviewer/organization-admin membership for the organization owning the consent record. The database marks the record withdrawn and appends a governance event. Repeated withdrawal is idempotent. This records a governance state change; the data-release policy must still check consent status on every relevant request before any participant-specific release can be enabled.


## Request detail and history API

`GET /requests/{request_id}` requires a valid Supabase bearer token and an active membership in the request's organization. Researchers can retrieve their own requests; reviewers and organization administrators can inspect requests in their organization. A cross-organization or otherwise unauthorized request returns the same not-found response as an unavailable request.

The response includes the persisted request fields, current decision, and recorded API event history. It does not include genotype calls or raw participant rows. The endpoint reports that it did not release data; a review approval remains a governance decision only.
