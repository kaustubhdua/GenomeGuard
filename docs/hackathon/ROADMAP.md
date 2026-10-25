# GenomeGuard roadmap: 24 Oct to 2 Nov 2026

Written 24 Oct 2026 (IST). Submission window 25 Oct to 2 Nov, 11:59 PM. Final on 14 Nov in Delhi.
Track 2: Agentic AI for Healthcare.

## Status (24 Oct, end of build session)

**Done and verified in the sandbox (248 tests, ruff clean, `scripts/demo.py` and `scripts/ui_smoke.py` pass):** steward copilot (read-only tool loop, rules cap), FHIR R4 Consent export, guided tour, accessibility and phone-width fixes, `make bench` + `docs/scalability.md`, family-first real-trio builder, `make eval-real`, provenance labelling driven by cohort-file metadata.

**Only you can do these (the sandbox had no network access to 1000 Genomes, hosting or your accounts):**
1. Run `make setup test lint demo` on your machine.
2. Download one chromosome's VCF and the pedigree from IGSR (file names unconfirmed), then `make real-trios` and `make eval-real`.
3. Deploy (re-check free-tier limits first), optionally set `ANTHROPIC_API_KEY`.
4. Publish the audit head hash somewhere outside the system.
5. Record the demo video, build the slides (slide 1 needs the five links), submit before 6 PM IST on 2 Nov.

## 0. Where the project stands (read from the repo, not assumed)

Already built: consent engine (DUO-inspired), risk estimator with relative exposure, transform
ladder with epsilon ledger, anomaly monitor with differencing guard, hash-chained audit log,
AES-256-GCM at rest, Paillier aggregation demo, federated secure aggregation, Beacon v2 style
endpoint, advisory agents with a sanitizer and template fallback, donor portal, red-team harness,
CI, Dockerfile, Render blueprint, and a vanilla-JS frontend with 9 pages, a command palette and
dark mode.

Not verified yet (the build sandbox had no PyPI or 1000 Genomes access): the test suite, `make
eval`, `make demo`, a real-data run, and a live deployment. Step 1 of Day 1 is to run them.

## 1. The honest answer to "nothing simulated"

Three things can be made real. Two cannot, and pretending would cost you with judges.

| Part | Can it be real? | Plan |
|---|---|---|
| Genotypes, allele frequencies, populations | Yes | Deploy on real 1000 Genomes data, not synthetic. |
| Relatives | Yes | Use the 602 real trios from the high-coverage release so family exposure comes from real pedigrees. |
| Agents | Yes | Make the steward copilot a real tool-using agent (section 3), with a real LLM key on the deployed demo. |
| Donor consent | **No.** No real person consented to this system | Keep it labelled "simulated consent". Add a FHIR `Consent` export so the format is real even though the records are demo records. |
| Requesters and traffic | **No** | Label as demo accounts. The red-team traffic is scripted; say so. |

The top bar already shows a provenance chip. Keep it, and make it say "Real genotypes, simulated
consent" on the deployed build. A judge who finds an unlabelled simulation will distrust
everything; a judge who sees you label it will trust the rest.

## 2. Judging criteria and what moves each one

| Criterion | Current gap | Action |
|---|---|---|
| Innovation | Strong (relative-aware, tamper-evident). | Lead with relative exposure on real trios. |
| Relevance to Track 2 | Agents are thin wrappers over templates; "agentic" is arguable. | Build the tool-using steward copilot. This is the single most valuable change. |
| Technical implementation | Unverified end to end. | Green CI, `make demo` passing, deployed build. |
| UI/UX | Good base. Needs a guided first-run path. | Section 4. |
| Real-world impact | Claims are fine. | Add FHIR Consent export and a Beacon v2 conformance note. |
| Scalability and feasibility | SQLite, in-memory cohort. | Written answer, plus one measured number (requests per second, cohort size, memory). |
| Team presentation | Slide inputs exist. | Rehearse the 3-minute demo twice. |

## 3. The one big build: a real agent loop

Today an agent receives pre-computed facts and writes text. A Track 2 judge will ask "where is the
agent deciding what to do next?" Add:

- A **steward copilot** for held requests. It gets a read-only tool belt: `consent_summary`,
  `risk_estimate`, `family_exposure_counts`, `requester_history`, `audit_lookup`. It calls tools
  in a loop (cap of 6 steps), then returns a recommendation with the tool calls it made.
- Authority stays with the deterministic core and a human click. The agent cannot approve,
  deny, freeze, or read genotypes. Tools return only what `sanitizer.py` already whitelists.
- Every tool call and the final recommendation are written to the audit chain.
- Without an API key it falls back to a fixed tool sequence, so the demo never fails.
- Tests: the canary test must cover tool outputs; a test that the agent has no write tools.

Keep the existing explainer, compliance, and donor concierge as they are.

## 4. UI/UX plan

1. **Guided demo mode.** A "Start the 3-minute tour" button on the Overview that walks the six
   demo steps, each deep-linking to the right page with a one-line caption.
2. **Plain-language first.** Every decision page opens with the outcome and a three-sentence
   explanation; risk numbers sit under "Details".
3. **Family exposure as a tree** with exposed relatives highlighted (check it renders for real trios).
4. **Empty, loading and error states** on every page; a visible "waking up" message for the cold start.
5. **Accessibility pass**: keyboard-only walkthrough, contrast check, 24 px targets, reduced-motion.
6. **Mobile check** at 375 px; judges may open the link on a phone.
7. Screenshots in the README for each page.

## 5. Day by day

**Sat 24 Oct (today).** Run `make setup test lint eval-smoke demo` on your machine and fix
whatever fails. Push. Do not start features until this is green.

**Sun 25 Oct.** Run `make fetch-real` with the high-coverage VCF and pedigree (section 6). Confirm
real relative pairs appear. Re-run `make eval` on real genotypes and regenerate `docs/eval-results.md`;
the numbers will change, and that is fine. Submission window opens today: open the Unstop form and
read exactly what it asks for.

**Mon 26 Oct.** Build the agent loop (section 3) and its tests.

**Tue 27 Oct.** UI items 1 to 3 (guided tour, plain-language decision page, family tree on real data).

**Wed 28 Oct.** FHIR `Consent` export endpoint (`GET /donor/{id}/consent.fhir.json`) and a small
test that it parses as valid JSON with the required fields. UI items 4 to 6.

**Thu 29 Oct.** Feature freeze. Task 2 individual forms (each member). Deploy to a host (section 7).

**Fri 30 Oct.** Full dry run on the deployed link. Fix only bugs. Measure scalability numbers.

**Sat 31 Oct.** Record the demo video (3 minutes, scripted in `docs/walkthrough.md`). Final README
with screenshots. Publish the audit head hash in the README and on slide 1's notes.

**Sun 1 Nov.** Buffer. Hand slide inputs to teammates. Check every link while logged out.

**Mon 2 Nov.** Submit before 6 PM, not 11:59 PM.

**Cut order if time runs short:** FHIR export, then guided tour polish, then the compliance
report, then the Paillier page. Never cut: green tests, real-data run, deployed link, demo video.

## 6. Real data: what is confirmed and what is not

Confirmed from the paper's text: the expanded 1000 Genomes cohort has 3,202 samples (2,504
original plus 698 related), completing 602 parent-child trios, and the participants consented to
public release of their genetic data.

Found but not independently verified here: the phased SNV/INDEL/SV VCFs live under
`http://ftp.1000genomes.ebi.ac.uk/vol1/ftp/data_collections/1000G_2504_high_coverage/working/20220422_3202_phased_SNV_INDEL_SV/`
(from a Biostars answer). Open that directory in a browser and read the file names yourself. The
pedigree file path was not confirmed; look in the parent `1000G_2504_high_coverage/` directory and
the IGSR data portal. Run `python -m app.data.real build --vcf <file> --ped <file>`.

Notes: files are large, so use one small chromosome (22) and keep the existing sampling. Never
commit downloaded data. Check IGSR's current data-use statement before you show real rows publicly;
the demo only ever shows aggregates, which is the safer position.

The `parse_ped` loader expects a header row with family, individual, paternal, maternal and
population columns. If the high-coverage pedigree uses different headers, extend the column
aliases and add a test with a three-line fixture.

## 7. Deployment (checked 24 Oct against vendor pages; re-check before you rely on it)

- **Render free web service**: spins down after 15 minutes of no traffic and takes about a minute
  to wake; 512 MB RAM; 750 free hours a month. Source: the temps.sh 2026 pricing write-up, not
  Render's own page, so confirm on render.com. Consequence: the database resets without a disk, so
  the audit chain restarts. Open the link 2 minutes before any judge looks, or pay $7 for a
  month to remove sleep. Check that the real cohort fits in 512 MB; if not, lower `--samples`.
- **Hugging Face Spaces**: the docs say the free CPU tier is 2 vCPU and 16 GB RAM and free Spaces
  sleep, but that Docker Spaces need a paid plan. So it is not a free option for this app.
- The frontend is served by the same Starlette app, so one host is enough. No Vercel needed.
- Whatever you pick, put the demo video on a link that does not depend on the live site, so a
  sleeping server cannot sink your submission.

## 8. Scalability answers for judges (say what is true)

- Today: single process, SQLite, cohort held in memory. Fine for thousands of donors.
- Next: Postgres for the audit log and ledger, a queue for escalations, per-requester caches for
  the anomaly windows, genotype access through a columnar store instead of one array.
- The audit chain is single-writer: say so. Fixing it needs a sequencer or periodic Merkle anchoring.
- Measure and report one real figure (requests per second on the deployed host). Do not estimate.

## 9. Likely judge questions

1. *Is this real data?* Genotypes are real 1000 Genomes; consent and requesters are demo records.
2. *Why agents?* The copilot chooses which evidence to gather per case; the core and a human decide.
3. *Does the LLM see DNA?* No. A test plants a canary and checks it never reaches a prompt.
4. *What if the server is compromised?* The hash chain detects edits only if the head is anchored outside.
5. *Is it compliant with DPDP?* No claim of compliance; it is designed around the ideas.
6. *What does the evaluation not show?* See the first section of `docs/eval-results.md`.
