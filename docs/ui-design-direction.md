# GenomeGuard UI design direction

## Intent

GenomeGuard is a research governance workspace. It should read as a technical research instrument, the kind of tool a genomics core facility or a data access committee would run, and not as a paper, a landing page or a generic dashboard template. The routes and interaction model stay as they were (vanilla JavaScript, no build step); this change replaces the visual layer.

## The idea: a genome browser crossed with a pathology lab

- **Chromosome as pipeline.** A request passes through seven stages. They are drawn as one banded chromosome, G-band style, with the access decision as the centromere (the pinched waist). The figure is data: each band's colour is the stage's real outcome.
- **Hashes as banded fingerprints.** Audit hashes and file checksums render as a barcode of G-band stripes next to the hex string, so a changed hash is visible at a glance. The hex is always shown too; the fingerprint is a visual aid, not a replacement.
- **Coverage bars on the chromosome explorer.** Bar length is the chromosome's length relative to the longest one; the dark span is where stored variants were observed.
- **Stain-named semantic colour.** Colours are named after histology stains and carry fixed meaning: light green = permit, orange G-band = protected (transformed), eosin = deny, hematoxylin violet = held for a human, DAPI blue = focus and links. The light theme is a light box (clean, cool grey-white); the dark theme is a fluorescence field.

## Biology palette, liveliness and sample data

- The page is leaf-green and white; the left rail is a dark chlorophyll column in both themes, with a few cells drifting at its top.
- The hero carries a slowly drifting DNA double helix whose rungs are the four stain colours (motion is off under reduced-motion).
- The top bar holds only the page name, search and theme. The data-source line sits in its own slim strip below it.
- Where a live source is empty or unreachable (overview, Chromosomes, Datasets) the person can preview a layout with sample data. Sample data is always flagged "Sample data" on screen, uses invented values (only the GRCh38 chromosome lengths are real), and has a "Back to the live view" control. It lives in `frontend/src/sample-data.js`.

## Type

Familjen Grotesk for everything a person reads; Spline Sans Mono for data only (hashes, coordinates, counts). Both are SIL Open Font License, self-hosted in `frontend/src/fonts/` with their licences, so the page makes no third-party font request.

## Principles kept from before

- **Truth over decoration:** no fake KPIs, activity or uptime. Empty and unreachable states say so.
- **Provenance and limits stay visible:** the data-source banner, the "research prototype" release gate and the dataset-level policy labels are unchanged in meaning.
- **Accessibility floor:** WCAG AA contrast in both themes, visible keyboard focus, 24 px minimum targets, no horizontal scroll from 320 px, reduced-motion respected. `make ui-smoke` enforces these.
- **Restrained motion:** one orchestrated moment (the pipeline filling in on load, and on Replay). Nothing else moves unprompted.

## Files

- `frontend/src/fonts.css`, `frontend/src/fonts/`: self-hosted fonts.
- `frontend/src/gg.css`: tokens (light and dark) and all components.
- `frontend/src/ui.js`: `bands()`, `pipeline()`, `timeline()` and the other shared builders.

## Known boundary

This is a visual and interaction change. It does not resolve database security, persistent storage, identity, consent, production deployment, backup and restore, or independent privacy and security review. Those stay tracked in the production readiness audit.
