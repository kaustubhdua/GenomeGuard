# Changelog

## Unreleased

- Added a database-free local VCF QC command, local JSON report preview, and steward-only
  temporary server-side VCF QC upload. The upload is bounded, does not persist or import the
  source file, and runs only on the configured GenomeGuard server. Reports include parser,
  checksum, metadata, genotype-missingness, allele-frequency, QUAL, and optional GQ measures;
  they omit sample identifiers and do not establish licensing, consent, or import approval.
- UI redesign: a biology and medical research-instrument look. The request pipeline is drawn as a
  banded chromosome with the decision as the centromere, audit hashes and checksums get banded
  fingerprints, the chromosome explorer gains coverage bars, and outcome colours are named after
  histology stains. Self-hosted Familjen Grotesk and Spline Sans Mono (SIL Open Font License) replace
  the previous theme; `style.css` and `field-theme.css` are replaced by `gg.css`. No behaviour,
  route or API change.
- Demo mode: **Undo demo tamper** on the Audit page removes the demo marker so the exercise can be
  repeated. Genuine edits to an entry stay detected.

## 0.1.0

- Consent-aware, relative-aware release pipeline: consent, risk, protections, anomaly monitor,
  deterministic decision, audit.
- Steward copilot: read-only tool loop, capped by a rules baseline, fully audited.
- Donor portal with consent changes, withdrawal and FHIR R4 Consent export (simulated consent).
- GA4GH Beacon v2 style endpoint governed by the same checks.
- Paillier homomorphic aggregation and secure-aggregation demos.
- Real-genotype cohort builder for 1000 Genomes (family-first for trios) and `make eval-real`.
- Red-team evaluation with fixed seeds, benchmark script, guided tour, accessibility and
  phone-width regression checks.
