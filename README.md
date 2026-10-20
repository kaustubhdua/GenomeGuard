# GenomeGuard

Genomic data can expose your relatives, so we built a guard that decides who can see what,
explains why, and proves it never looked the other way.

GenomeGuard is a consent-aware, relative-aware governance and security layer in front of a
genomic data store. **All data in this repository is synthetic.** Designed around the ideas of
DPDP, GDPR and HIPAA; it makes no claim of legal compliance.

## Quick start
```
make setup && make seed && make test && make eval && make run
```
(`seed` and `eval` are filled in at steps 2 and 10; see docs/ as they land.)

Status: step 1 of 12 (skeleton, config, DB models).
