# Three-minute demo script

Run it on a **fresh database** (the probe account freezes and the audit chain gets tampered, and
those are permanent). `make demo` runs the same steps automatically and checks each one.

**Shortcut:** on the Overview, **Take the 3-minute tour** walks the same story and performs the
two live actions (send the researcher's request, run the probing account) for you. Use it if you
would rather talk than click. `make ui-smoke` replays it in a headless browser as a regression test.

```
GG_DB_PATH=/tmp/demo.sqlite3 GG_ALLOW_TAMPER_DEMO=true make run
```
Open the app, say once: **"All data here is synthetic."**

| Time | You do | You say |
|---|---|---|
| 0:00 | Requests page, acting as *Dr. Amara Nwosu*. Click **Send request** (diabetes preset). | "A researcher wants allele frequencies for a diabetes study. GenomeGuard checks consent first." |
| 0:25 | Open the decision. Point at the consent bar and the exclusion reasons. | "453 of 600 donors consented to this use. 95 are excluded because their consent is for another disease, 15 withdrew. Withdrawal works immediately." |
| 0:45 | Point at the risk gauge, before and after. Read the **Protections** line. | "The request included two very rare variants with only a few carriers. Those would point at individuals, so they were dropped. Risk goes from high to low." |
| 1:05 | Switch to **Steward**. Open **Family exposure**. | "Rare variants run in families. Dark nodes are carriers; glowing nodes are relatives who never joined the study but would be exposed. This is a simulated model with expected-average kinship, not a forecast about any real database." |
| 1:30 | Switch to *Probe Account*. Requests, **Run probe sequence**. | "Another account sends many slightly different narrow queries, the classic way to triangulate one person." |
| 1:45 | Switch to Steward, **Anomalies**. | "The monitor's score rises, the differencing guard blocks one query because two cohorts differ by fewer than 20 people, and the account is frozen with a clear 403. An escalation waits for a human, who can unfreeze." |
| 2:00 | Open the held request. The **Steward copilot** runs on its own. | "An agent investigates: it chooses to read consent, risk, the account's history and the audit chain, then recommends. It can read but not approve or freeze anything. Without an API key a built-in planner does the same, so this never fails on stage. A human clicks the decision." |
| 2:20 | **Audit log**. Point at *Chain valid* and the head hash. Click **Tamper with entry** 3, then **Verify now**. | "Every step is in a hash chain. Change one past entry and the chain breaks at exactly that entry. It makes tampering detectable, not impossible, so we publish the head hash outside the system." |
| 2:42 | **Red-team results**. | "We attack our own system and measure it. The tracker attack recovers 100% with no defence and falls to the guessing baseline with the guard. Noise that hides membership also destroys most of the signal; that trade-off is reported honestly. Zero false alarms on 500 simulated researchers, which is our assumed traffic, not measured logs." |
| 2:55 | Optional: **Federated** tab. | "Hospitals can also analyse together without pooling genomes." |

## If something goes wrong

- Chain already tampered or probe already frozen: restart with a new `GG_DB_PATH`.
- No API key: nothing to do. Explanations come from templates, which is the default.
- Browser cached an old state: hard reload, or clear site data for the page.
