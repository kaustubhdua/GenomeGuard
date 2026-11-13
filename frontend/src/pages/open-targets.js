import { h } from "../ui.js";

const ENDPOINT = "/research/open-targets/target";
const API_DOCS = "https://platform-docs.opentargets.org/data-access/graphql-api";
const PAGE_SIZE = 20;
const EVIDENCE_SIZE = 25;

function safeExternal(url, label, className = "source-link") {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: className }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

function version(value, keys) {
  if (!value || typeof value !== "object") return "Not supplied";
  const parts = keys.map((key) => value[key]).filter((part) => part !== null && part !== undefined && String(part) !== "");
  return parts.length ? parts.join(".") : "Not supplied";
}

function score(value) {
  if (value === null || value === undefined || value === "") return "not supplied";
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(3) : "not supplied";
}

function md(value) {
  return String(value === null || value === undefined || value === "" ? "Not supplied" : value)
    .replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

function downloadFile(filename, content, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

export function renderOpenTargetsPanel() {
  const root = h("section", { class: "card stack open-targets-panel", "aria-labelledby": "ot-heading" },
    h("div", {},
      h("p", { class: "eyebrow" }, "TARGET–DISEASE EVIDENCE · OPEN TARGETS"),
      h("h2", { id: "ot-heading" }, "Gene–disease evidence"),
      h("p", { class: "muted" },
        "Explore direct target–disease associations and their source-level evidence. Enter an Ensembl gene ID and, optionally, an EFO disease ID. Gene symbols are not guessed or silently resolved."),
      h("p", { class: "fine muted" },
        "Open Targets scores are research-prioritisation signals—not probabilities, clinical validity, causal proof, diagnosis, or GenomeGuard confidence.")),
    h("form", { id: "ot-search-form", class: "research-search-form" },
      h("label", { for: "ot-ensembl-id" }, "Ensembl gene identifier"),
      h("input", { id: "ot-ensembl-id", name: "ensembl_id", type: "text", maxlength: "32",
        placeholder: "ENSG00000141510", autocomplete: "off", required: true }),
      h("label", { for: "ot-disease-id" }, "Optional EFO disease identifier"),
      h("input", { id: "ot-disease-id", name: "disease_id", type: "text", maxlength: "32",
        placeholder: "EFO_0000311", autocomplete: "off" }),
      h("div", { class: "hero-actions" },
        h("button", { class: "btn", type: "submit" }, "Search Open Targets evidence"),
        safeExternal(API_DOCS, "Open Targets API documentation"))),
    h("div", { id: "ot-status", class: "fine muted", role: "status", "aria-live": "polite" },
      "Enter an Ensembl gene ID to retrieve source-attributed evidence."),
    h("div", { id: "ot-target-summary", class: "grid g2" }),
    h("div", { class: "grid g2" },
      h("div", { class: "stack" },
        h("h3", {}, "Target–disease associations"),
        h("label", { for: "ot-association-source" }, "Association source filter"),
        h("select", { id: "ot-association-source", disabled: true },
          h("option", { value: "all" }, "All sources")),
        h("div", { id: "ot-association-results", class: "stack", "aria-live": "polite" }),
        h("button", { id: "ot-load-associations", class: "btn secondary", type: "button", hidden: true },
          "Load more associations")),
      h("div", { class: "stack" },
        h("h3", {}, "Source-level evidence"),
        h("label", { for: "ot-evidence-source" }, "Evidence source filter"),
        h("select", { id: "ot-evidence-source", disabled: true },
          h("option", { value: "all" }, "All sources")),
        h("div", { id: "ot-evidence-results", class: "stack", "aria-live": "polite" }),
        h("button", { id: "ot-load-evidence", class: "btn secondary", type: "button", hidden: true },
          "Load more evidence"))),
    h("div", { id: "ot-provenance", class: "card stack" },
      h("h3", {}, "Source provenance and citation metadata"),
      h("p", { class: "fine muted" }, "The API/data release, retrieval time, query identifiers and original evidence links will appear here after a successful search.")),
    h("div", { class: "hero-actions" },
      h("button", { id: "ot-export-json", class: "btn secondary", type: "button", disabled: true },
        "Export evidence JSON"),
      h("button", { id: "ot-export-markdown", class: "btn secondary", type: "button", disabled: true },
        "Export Markdown report")));

  const form = root.querySelector("#ot-search-form");
  const geneInput = root.querySelector("#ot-ensembl-id");
  const diseaseInput = root.querySelector("#ot-disease-id");
  const status = root.querySelector("#ot-status");
  const summary = root.querySelector("#ot-target-summary");
  const associationFilter = root.querySelector("#ot-association-source");
  const evidenceFilter = root.querySelector("#ot-evidence-source");
  const associationResults = root.querySelector("#ot-association-results");
  const evidenceResults = root.querySelector("#ot-evidence-results");
  const associationMore = root.querySelector("#ot-load-associations");
  const evidenceMore = root.querySelector("#ot-load-evidence");
  const provenance = root.querySelector("#ot-provenance");
  const exportJson = root.querySelector("#ot-export-json");
  const exportMarkdown = root.querySelector("#ot-export-markdown");
  const submit = form.querySelector('button[type="submit"]');

  let activeQuery = null;
  let current = null;
  let associations = [];
  let evidence = [];
  let associationPage = 0;
  let evidenceCursor = null;
  let busy = false;
  let generation = 0;

  function setStatus(message, error = false) {
    status.textContent = message;
    status.dataset.state = error ? "error" : "info";
  }

  function populateFilter(select, values) {
    const selected = select.value || "all";
    const unique = [...new Set(values.filter((value) => typeof value === "string" && value.length))].sort();
    select.replaceChildren(h("option", { value: "all" }, "All sources"),
      ...unique.map((value) => h("option", { value }, value)));
    select.disabled = unique.length === 0;
    select.value = unique.includes(selected) ? selected : "all";
  }

  function renderSummary() {
    if (!current) {
      summary.replaceChildren();
      return;
    }
    const target = current.target || {};
    summary.replaceChildren(
      h("article", { class: "card research-paper" },
        h("span", { class: "tag" }, "Open Targets Platform"),
        h("h3", {}, target.approved_symbol || target.id || "Target"),
        h("p", { class: "fine" }, "Ensembl ID: " + (target.id || "Not supplied")),
        h("p", { class: "fine muted" }, "Biotype: " + (target.biotype || "Not supplied"))),
      h("article", { class: "card research-paper" },
        h("span", { class: "tag" }, "Direct-only query"),
        h("h3", {}, String(current.associations?.count ?? 0) + " associations"),
        h("p", { class: "fine" }, String(current.evidence?.count ?? 0) + " source-level evidence records"),
        h("p", { class: "fine muted" }, "Loaded " + associations.length + " associations and " + evidence.length + " evidence records.")));
  }

  function renderAssociations() {
    const selected = associationFilter.value || "all";
    const visible = selected === "all" ? associations : associations.filter((row) =>
      Array.isArray(row.datasourceScores) && row.datasourceScores.some((item) => item && item.id === selected));
    associationResults.replaceChildren();
    if (!visible.length) {
      associationResults.append(h("p", { class: "fine muted" },
        !current ? "Run an Open Targets search to load associations."
          : associations.length ? "No associations match this source filter." : "No association records were returned."));
    }
    for (const row of visible) {
      const disease = row.disease || {};
      const datasourceScores = Array.isArray(row.datasourceScores) ? row.datasourceScores : [];
      const datatypeScores = Array.isArray(row.datatypeScores) ? row.datatypeScores : [];
      associationResults.append(h("article", { class: "card research-paper" },
        h("div", { class: "source-card-top" },
          h("span", { class: "tag" }, "Direct association"),
          h("span", { class: "fine" }, disease.id || "Disease identifier not supplied")),
        h("h3", {}, disease.name || "Disease name not supplied"),
        h("p", { class: "fine" }, "Open Targets prioritisation score (0–1): " + score(row.score)),
        h("p", { class: "fine muted" }, "Source scores: " + (datasourceScores.length
          ? datasourceScores.map((item) => String(item.id) + ": " + score(item.score)).join(" · ")
          : "Not supplied by source")),
        h("p", { class: "fine muted" }, "Datatype scores: " + (datatypeScores.length
          ? datatypeScores.map((item) => String(item.id) + ": " + score(item.score)).join(" · ")
          : "Not supplied by source"))));
    }
    const total = Number(current?.associations?.count || 0);
    associationMore.hidden = !activeQuery || associations.length >= total || associations.length === 0;
    associationMore.disabled = busy;
  }

  function renderEvidence() {
    const selected = evidenceFilter.value || "all";
    const visible = selected === "all" ? evidence : evidence.filter((row) => row.datasourceId === selected);
    evidenceResults.replaceChildren();
    if (!current) {
      evidenceResults.append(h("p", { class: "fine muted" }, "Run an Open Targets search to load source-level evidence."));
    } else if (!activeQuery?.disease_id) {
      evidenceResults.append(h("p", { class: "fine muted" },
        "Enter an EFO disease identifier to request disease-specific evidence records."));
    } else if (!visible.length) {
      evidenceResults.append(h("p", { class: "fine muted" },
        evidence.length ? "No evidence records match this source filter." : "No source-level evidence records were returned."));
    }
    for (const row of visible) {
      const urls = Array.isArray(row.urls) ? row.urls : [];
      const literature = Array.isArray(row.literature) ? row.literature : [];
      const links = [];
      for (const item of urls) {
        if (item && item.url) links.push(safeExternal(item.url, item.niceName || "Original source record"));
      }
      for (const id of literature) {
        const value = String(id);
        if (/^\d+$/.test(value)) {
          links.push(safeExternal("https://pubmed.ncbi.nlm.nih.gov/" + encodeURIComponent(value) + "/",
            "PubMed " + value));
        } else {
          links.push(h("span", { class: "fine muted" }, "Publication ID: " + value));
        }
      }
      evidenceResults.append(h("article", { class: "card research-paper" },
        h("div", { class: "source-card-top" },
          h("span", { class: "tag" }, row.datasourceId || "Source not supplied"),
          h("span", { class: "fine" }, row.datatypeId || "Datatype not supplied")),
        h("h3", {}, row.publicationFirstAuthor
          ? String(row.publicationFirstAuthor) + " · " + (row.publicationDate || "Publication date not supplied")
          : "Evidence record " + (row.id || "")),
        h("p", { class: "fine" }, "Source/platform evidence score (not GenomeGuard confidence): " + score(row.score)),
        h("p", { class: "fine muted" }, "Evidence ID: " + (row.id || "Not supplied")
          + " · Study ID: " + (row.studyId || "Not supplied")),
        h("p", { class: "fine muted" }, "Study sample size: " + (row.studySampleSize ?? "Not supplied")
          + " · Source release: " + (row.releaseVersion || "Not supplied")
          + (row.releaseDate ? " (" + row.releaseDate + ")" : "")),
        row.cohortDescription ? h("p", { class: "fine muted" }, "Cohort: " + row.cohortDescription) : null,
        row.warningMessage ? h("p", { class: "fine" }, "Source warning: " + row.warningMessage) : null,
        h("div", { class: "source-links" }, ...links)));
    }
    evidenceMore.hidden = !activeQuery?.disease_id || !evidenceCursor || evidence.length === 0;
    evidenceMore.disabled = busy;
  }

  function renderProvenance() {
    if (!current?.provenance) {
      provenance.replaceChildren(
        h("h3", {}, "Source provenance and citation metadata"),
        h("p", { class: "fine muted" }, "The API/data release, retrieval time, query identifiers and original evidence links will appear here after a successful search."));
      return;
    }
    const p = current.provenance;
    const apiVersion = version(p.api_version, ["x", "y", "z", "suffix"]);
    const dataVersion = version(p.data_version, ["year", "month", "iteration"]);
    provenance.replaceChildren(
      h("h3", {}, "Source provenance and citation metadata"),
      h("p", { class: "fine" }, "Provider: " + (p.provider || "Open Targets Platform")),
      h("p", { class: "fine" }, "API version: " + apiVersion + " · Data release: " + dataVersion),
      h("p", { class: "fine" }, "Retrieved at: " + (p.retrieved_at || "Not supplied")),
      h("p", { class: "fine" }, "Query: " + activeQuery.ensembl_id
        + (activeQuery.disease_id ? " · " + activeQuery.disease_id : "")),
      h("p", { class: "fine" }, "Association mode: " + (p.association_mode || "Not supplied")),
      h("div", { class: "source-links" },
        safeExternal(p.endpoint || "https://api.platform.opentargets.org/api/v4/graphql", "Open Targets GraphQL endpoint"),
        safeExternal(API_DOCS, "Open Targets API documentation")),
      h("p", { class: "fine muted" },
        "Citation metadata: cite Open Targets Platform with this data release, API version, retrieval timestamp and exact query identifiers. Cite original evidence records and publications separately using their source IDs and links. Scores remain source-defined research-prioritisation signals." ));
  }

  function updateFilters() {
    populateFilter(associationFilter, associations.flatMap((row) =>
      Array.isArray(row.datasourceScores) ? row.datasourceScores.map((item) => item?.id) : []));
    populateFilter(evidenceFilter, evidence.map((row) => row.datasourceId));
  }

  function renderAll() {
    updateFilters();
    renderSummary();
    renderAssociations();
    renderEvidence();
    renderProvenance();
    exportJson.disabled = !current;
    exportMarkdown.disabled = !current;
  }

  function sameRelease(left, right) {
    return JSON.stringify(left?.api_version) === JSON.stringify(right?.api_version)
      && JSON.stringify(left?.data_version) === JSON.stringify(right?.data_version);
  }

  async function fetchOpenTargets(pageIndex, cursor, requestGeneration) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          ensembl_id: activeQuery.ensembl_id,
          disease_id: activeQuery.disease_id,
          page_index: pageIndex,
          page_size: PAGE_SIZE,
          evidence_size: EVIDENCE_SIZE,
          evidence_cursor: cursor,
        }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (requestGeneration !== generation) return null;
      if (!response.ok) throw new Error(data.message || "Open Targets returned HTTP " + response.status + ".");
      if (!data || data.provider !== "Open Targets Platform"
          || !Array.isArray(data.associations?.rows) || !Array.isArray(data.evidence?.rows)
          || !data.provenance || !data.target) {
        throw new Error("Open Targets returned an unexpected evidence response.");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  function exportPayload() {
    return {
      schema_version: "genomeguard.open-targets-research-export.v1",
      generated_at: new Date().toISOString(),
      provider: current.provider,
      query: {
        ensembl_id: activeQuery.ensembl_id,
        disease_id: activeQuery.disease_id,
        page_size: PAGE_SIZE,
        evidence_size: EVIDENCE_SIZE,
        association_mode: current.provenance.association_mode,
      },
      target: current.target,
      associations: {
        ...current.associations,
        rows: associations,
        loaded_count: associations.length,
        loaded_pages: associationPage + 1,
      },
      evidence: {
        ...current.evidence,
        rows: evidence,
        loaded_count: evidence.length,
        next_cursor: evidenceCursor,
      },
      provenance: current.provenance,
      interpretation: current.interpretation,
      citation_requirements: [
        "Cite Open Targets Platform and include the exact data release, API version, retrieval timestamp, and query identifiers.",
        "Retain datasource IDs, datatype IDs, evidence IDs, study IDs, publication IDs, and original source URLs.",
        "Cite original evidence sources and publications separately where available.",
        "Describe association scores only as Open Targets prioritisation scores; not probabilities, clinical validity, causal proof, or GenomeGuard confidence.",
      ],
    };
  }

  function markdownReport(payload) {
    const p = payload.provenance || {};
    const lines = [
      "# GenomeGuard Open Targets research evidence",
      "",
      "Generated: " + md(payload.generated_at),
      "",
      "## Query",
      "- Ensembl gene ID: " + md(payload.query.ensembl_id),
      "- EFO disease ID: " + md(payload.query.disease_id),
      "- Association mode: " + md(payload.query.association_mode),
      "- Page size: " + md(payload.query.page_size),
      "- Evidence page size: " + md(payload.query.evidence_size),
      "",
      "## Provenance",
      "- Provider: " + md(p.provider),
      "- API version: " + version(p.api_version, ["x", "y", "z", "suffix"]),
      "- Data release: " + version(p.data_version, ["year", "month", "iteration"]),
      "- Retrieved at: " + md(p.retrieved_at),
      "- Endpoint: " + md(p.endpoint),
      "",
      "## Interpretation",
      "- Association score: " + md(payload.interpretation?.association_score),
      "- Evidence score: " + md(payload.interpretation?.evidence_score),
      "- This report is for research exploration; it does not establish diagnosis, causality, clinical validity, treatment suitability, or clinical recommendations.",
      "",
      "## Target–disease associations",
    ];
    for (const row of payload.associations.rows) {
      lines.push("- " + md(row.disease?.name) + " (" + md(row.disease?.id) + ")");
      lines.push("  - Open Targets prioritisation score (0–1): " + md(score(row.score)));
      const sources = Array.isArray(row.datasourceScores) ? row.datasourceScores : [];
      lines.push("  - Source scores: " + (sources.length
        ? sources.map((item) => md(item.id) + " " + score(item.score)).join("; ")
        : "Not supplied"));
    }
    lines.push("", "## Source-level evidence");
    for (const row of payload.evidence.rows) {
      lines.push("- Evidence " + md(row.id) + " · " + md(row.datasourceId) + " · " + md(row.datatypeId));
      lines.push("  - Source score (not GenomeGuard confidence): " + md(score(row.score)));
      lines.push("  - Study: " + md(row.studyId) + " · sample size: " + md(row.studySampleSize));
      lines.push("  - Publication: " + md(row.publicationFirstAuthor) + " · " + md(row.publicationDate));
      const urls = Array.isArray(row.urls) ? row.urls : [];
      for (const item of urls) {
        const safeUrl = item?.url ? markdownUrl(item.url) : null;
        if (safeUrl) {
          lines.push("  - Source link: [" + md(item.niceName || "Original source") + "](<" + safeUrl + ">)");
        }
      }
      const literature = Array.isArray(row.literature) ? row.literature : [];
      for (const id of literature) {
        const value = String(id);
        if (/^\d+$/.test(value)) lines.push("  - Publication: [PMID " + value + "](https://pubmed.ncbi.nlm.nih.gov/" + value + "/)");
        else lines.push("  - Publication ID: " + md(value));
      }
    }
    lines.push("", "## Citation and reuse requirements");
    for (const item of payload.citation_requirements) lines.push("- " + md(item));
    lines.push("", "Source records and publication links are authoritative; do not infer consensus where source interpretations conflict.");
    return lines.join("\n");
  }

  async function search(event) {
    event?.preventDefault();
    const ensemblId = geneInput.value.trim().toUpperCase();
    const diseaseId = diseaseInput.value.trim().toUpperCase();
    if (!/^ENSG\d{11}$/.test(ensemblId)) {
      setStatus("Enter a valid Ensembl gene identifier (ENSG followed by 11 digits).", true);
      geneInput.focus();
      return;
    }
    if (diseaseId && !/^EFO_\d{7,}$/.test(diseaseId)) {
      setStatus("Enter a valid EFO disease identifier (EFO_ followed by at least 7 digits), or leave it blank.", true);
      diseaseInput.focus();
      return;
    }
    activeQuery = { ensembl_id: ensemblId, disease_id: diseaseId || null };
    generation += 1;
    const requestGeneration = generation;
    associations = [];
    evidence = [];
    associationPage = 0;
    evidenceCursor = null;
    current = null;
    renderAll();
    busy = true;
    submit.disabled = true;
    setStatus("Retrieving direct-only target–disease associations from Open Targets…");
    try {
      const data = await fetchOpenTargets(0, null, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      current = data;
      associations = data.associations.rows.slice();
      evidence = data.evidence.rows.slice();
      evidenceCursor = data.evidence.cursor || null;
      renderAll();
      setStatus("Loaded " + associations.length + " direct associations and " + evidence.length
        + " source-level evidence records. Scores are source-defined research prioritisation signals.");
    } catch (error) {
      if (requestGeneration === generation) {
        setStatus(error.name === "AbortError" ? "Open Targets search timed out. Please retry."
          : "Open Targets evidence could not be retrieved. No sample evidence is shown. " + error.message, true);
      }
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        submit.disabled = false;
        renderAssociations();
        renderEvidence();
      }
    }
  }

  async function loadMoreAssociations() {
    if (busy || !activeQuery || !current) return;
    busy = true;
    associationMore.disabled = true;
    const requestGeneration = generation;
    try {
      const data = await fetchOpenTargets(associationPage + 1, null, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      if (!sameRelease(current.provenance, data.provenance)) {
        throw new Error("Open Targets data release changed during pagination. Restart the search before combining results.");
      }
      associations.push(...data.associations.rows);
      associationPage += 1;
      current.provenance.retrieved_at = data.provenance.retrieved_at;
      renderAll();
      setStatus("Loaded " + associations.length + " of " + current.associations.count + " associations.");
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      busy = false;
      renderAssociations();
      renderEvidence();
    }
  }

  async function loadMoreEvidence() {
    if (busy || !activeQuery || !current || !evidenceCursor) return;
    busy = true;
    evidenceMore.disabled = true;
    const requestGeneration = generation;
    const cursor = evidenceCursor;
    try {
      const data = await fetchOpenTargets(0, cursor, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      if (!sameRelease(current.provenance, data.provenance)) {
        throw new Error("Open Targets data release changed during pagination. Restart the search before combining results.");
      }
      evidence.push(...data.evidence.rows);
      evidenceCursor = data.evidence.cursor || null;
      if (!data.evidence.rows.length && evidenceCursor === cursor) evidenceCursor = null;
      current.provenance.retrieved_at = data.provenance.retrieved_at;
      renderAll();
      setStatus("Loaded " + evidence.length + " of " + current.evidence.count + " evidence records.");
    } catch (error) {
      setStatus(error.message, true);
    } finally {
      busy = false;
      renderAssociations();
      renderEvidence();
    }
  }

  associationFilter.addEventListener("change", renderAssociations);
  evidenceFilter.addEventListener("change", renderEvidence);
  form.addEventListener("submit", search);
  associationMore.addEventListener("click", loadMoreAssociations);
  evidenceMore.addEventListener("click", loadMoreEvidence);
  exportJson.addEventListener("click", () => {
    if (!current) return;
    downloadFile("genomeguard-open-targets-evidence.json",
      JSON.stringify(exportPayload(), null, 2), "application/json");
  });
  exportMarkdown.addEventListener("click", () => {
    if (!current) return;
    downloadFile("genomeguard-open-targets-research-report.md",
      markdownReport(exportPayload()), "text/markdown");
  });

  return root;
}
