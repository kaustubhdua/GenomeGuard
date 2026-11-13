import { h } from "../ui.js";

const ENDPOINT = "/research/clinvar/search";
const API_DOCS = "https://www.ncbi.nlm.nih.gov/clinvar/docs/programmatic_access/";
const CLASSIFICATIONS = [
  ["", "All ClinVar reports"],
  ["pathogenic", "Pathogenic report property"],
  ["likely_pathogenic", "Likely pathogenic report property"],
  ["uncertain_significance", "Uncertain significance report property"],
  ["likely_benign", "Likely benign report property"],
  ["benign", "Benign report property"],
  ["conflicting", "Conflicting report property"],
];
const PAGE_SIZE = 20;

function safeExternal(url, label, className = "source-link") {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", {
      href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: className,
    }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

function display(value) {
  return value === null || value === undefined || value === "" ? "Not supplied by ClinVar" : String(value);
}

function classificationCard(label, value) {
  const record = value || {};
  return h("div", { class: "clinvar-classification" },
    h("strong", {}, label),
    h("p", {}, display(record.description)),
    h("p", { class: "fine muted" },
      "Review status: " + display(record.review_status)
      + " · Last evaluated: " + display(record.last_evaluated)),
    Array.isArray(record.traits) && record.traits.length
      ? h("p", { class: "fine muted" }, "Condition/trait: " + record.traits
        .map((trait) => trait.name || "Trait not supplied").join(" · "))
      : null);
}

function recordCard(record) {
  const classifications = record.classifications || {};
  const genes = Array.isArray(record.genes) ? record.genes : [];
  const variations = Array.isArray(record.variations) ? record.variations : [];
  const locations = variations.flatMap((variation) => Array.isArray(variation.locations)
    ? variation.locations.map((location) => ({
      ...location,
      variation_name: variation.name,
    })) : []);
  const locationText = locations.map((location) => [
    location.assembly,
    location.chromosome ? "chr" + location.chromosome : "",
    location.start && location.stop ? location.start + "–" + location.stop : "",
  ].filter(Boolean).join(" ")).filter(Boolean).join(" · ");
  const submissionCount = record.supporting_submissions || {};
  return h("article", { class: "card research-paper clinvar-record" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, "NCBI ClinVar"),
      h("span", { class: "fine" }, record.accession_version || record.accession || "VCV accession unavailable")),
    h("h3", {}, record.title || "Variant record without a title"),
    h("p", { class: "fine" }, "Gene: " + (genes.map((gene) => gene.symbol).filter(Boolean).join(", ") || "Not supplied")),
    h("p", { class: "fine muted" }, "Variant type: " + display(record.variation_type)
      + " · Consequence: " + (record.molecular_consequences || []).join(", ") || "Not supplied"),
    locationText ? h("p", { class: "fine muted" }, "Genomic locations: " + locationText) : null,
    h("div", { class: "clinvar-classifications" },
      classificationCard("Germline classification", classifications.germline),
      classificationCard("Somatic clinical impact", classifications.somatic_clinical_impact),
      classificationCard("Somatic oncogenicity", classifications.somatic_oncogenicity)),
    h("p", { class: "fine muted" }, "Supporting submissions: "
      + (submissionCount.scv_count ?? 0) + " SCV · " + (submissionCount.rcv_count ?? 0) + " RCV"),
    h("div", { class: "source-links" },
      record.source_url ? safeExternal(record.source_url, "Open ClinVar record") : null));
}

export function renderClinVarPanel() {
  const root = h("section", {
    class: "card stack clinvar-panel",
    "aria-labelledby": "clinvar-heading",
  },
    h("div", {},
      h("p", { class: "eyebrow" }, "VARIANT CLASSIFICATIONS · NCBI CLINVAR"),
      h("h2", { id: "clinvar-heading" }, "ClinVar variant evidence"),
      h("p", { class: "muted" },
        "Search variant-level ClinVar records by gene symbol. Aggregate germline, somatic impact, and oncogenicity classifications remain separate; review status and conflicting interpretations are shown as supplied by NCBI."),
      h("p", { class: "fine muted" },
        "ClinVar is an archive of submitted variant classifications—not a patient-specific interpretation, diagnosis, treatment recommendation, or independent guarantee of clinical validity.")),
    h("form", { id: "clinvar-search-form", class: "research-search-form" },
      h("label", { for: "clinvar-gene-symbol" }, "Gene symbol"),
      h("input", {
        id: "clinvar-gene-symbol", name: "gene_symbol", type: "text",
        maxlength: "20", placeholder: "BRCA1", autocomplete: "off", required: true,
      }),
      h("label", { for: "clinvar-classification" }, "ClinVar report property filter"),
      h("select", { id: "clinvar-classification", name: "classification" },
        ...CLASSIFICATIONS.map(([value, label]) => h("option", { value }, label))),
      h("div", { class: "hero-actions" },
        h("button", { class: "btn", type: "submit" }, "Search ClinVar variants"),
        safeExternal(API_DOCS, "ClinVar API documentation"),
        safeExternal("https://www.ncbi.nlm.nih.gov/clinvar/docs/clinsig/", "Classification definitions"))),
    h("div", {
      id: "clinvar-status", class: "fine muted", role: "status", "aria-live": "polite",
    }, "Enter a gene symbol to retrieve current public ClinVar variant records."),
    h("div", { id: "clinvar-summary", class: "grid g2" }),
    h("div", { id: "clinvar-results", class: "stack", "aria-live": "polite" }),
    h("div", { class: "hero-actions" },
      h("button", { id: "clinvar-load-more", class: "btn secondary", type: "button", hidden: true },
        "Load more ClinVar records"),
      h("button", { id: "clinvar-export-json", class: "btn secondary", type: "button", disabled: true },
        "Export ClinVar JSON")),
    h("div", { id: "clinvar-provenance", class: "card stack" },
      h("h3", {}, "ClinVar source provenance"),
      h("p", { class: "fine muted" },
        "The exact gene query, Properties filter, API version, retrieval time, and original record links appear here after a successful search.")));

  const form = root.querySelector("#clinvar-search-form");
  const geneInput = root.querySelector("#clinvar-gene-symbol");
  const classificationInput = root.querySelector("#clinvar-classification");
  const status = root.querySelector("#clinvar-status");
  const summary = root.querySelector("#clinvar-summary");
  const results = root.querySelector("#clinvar-results");
  const loadMore = root.querySelector("#clinvar-load-more");
  const exportJson = root.querySelector("#clinvar-export-json");
  const provenance = root.querySelector("#clinvar-provenance");
  const submit = form.querySelector('button[type="submit"]');

  let current = null;
  let records = [];
  let activeQuery = null;
  let generation = 0;
  let busy = false;
  let seenIds = new Set();
  let activeController = null;

  function renderAll() {
    results.replaceChildren(...records.map(recordCard));
    summary.replaceChildren();
    if (current) {
      summary.append(
        h("article", { class: "card research-paper" },
          h("span", { class: "tag" }, "ClinVar search"),
          h("h3", {}, current.query.gene_symbol),
          h("p", { class: "fine" }, String(current.count) + " matching variant records"),
          h("p", { class: "fine muted" }, current.query.classification_filter
            ? "Properties filter: " + current.query.classification_filter
            : "No Properties filter applied")),
        h("article", { class: "card research-paper" },
          h("span", { class: "tag" }, "Loaded records"),
          h("h3", {}, String(records.length) + " of " + String(current.count)),
          h("p", { class: "fine muted" }, "Records preserve source-provided classifications and review status.")));
      provenance.replaceChildren(
        h("h3", {}, "ClinVar source provenance"),
        h("p", { class: "fine" }, "Provider: " + current.provenance.provider),
        h("p", { class: "fine" }, "API: " + current.provenance.api),
        h("p", { class: "fine" }, "Query: " + current.provenance.query),
        h("p", { class: "fine" }, "Retrieved at: " + current.provenance.retrieved_at),
        h("p", { class: "fine muted" }, current.provenance.classification_note),
        h("p", { class: "fine muted" }, current.query.classification_filter_semantics),
        h("div", { class: "source-links" },
          safeExternal(current.provenance.source_url, "NCBI ClinVar")));
    } else {
      provenance.replaceChildren(
        h("h3", {}, "ClinVar source provenance"),
        h("p", { class: "fine muted" },
          "The exact gene query, Properties filter, API version, retrieval time, and original record links appear here after a successful search."));
    }
    loadMore.hidden = !current || !current.has_more;
    loadMore.disabled = busy;
    exportJson.disabled = !current;
  }

  async function fetchPage(retstart, requestGeneration) {
    if (activeController) activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          gene_symbol: activeQuery.gene_symbol,
          classification: activeQuery.classification,
          retstart,
          retmax: PAGE_SIZE,
        }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (requestGeneration !== generation) return null;
      if (!response.ok) {
        throw new Error(data.message || "ClinVar returned HTTP " + response.status + ".");
      }
      if (!data || data.provider !== "NCBI ClinVar" || !Array.isArray(data.records)
          || !data.provenance || !data.query) {
        throw new Error("ClinVar returned an unexpected response.");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function search(event) {
    event?.preventDefault();
    const geneSymbol = geneInput.value.trim().toUpperCase();
    if (!/^[A-Z][A-Z0-9.-]{0,19}$/.test(geneSymbol)) {
      status.textContent = "Enter a valid gene symbol using letters, digits, dots, or hyphens.";
      geneInput.focus();
      return;
    }
    if (activeController) activeController.abort();
    activeQuery = {
      gene_symbol: geneSymbol,
      classification: classificationInput.value || null,
    };
    generation += 1;
    const requestGeneration = generation;
    current = null;
    records = [];
    seenIds = new Set();
    busy = true;
    submit.disabled = true;
    submit.textContent = "Searching…";
    status.textContent = "Retrieving current ClinVar records from NCBI…";
    renderAll();
    try {
      const data = await fetchPage(0, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      current = data;
      records = data.records.filter((record) => {
        if (!record?.uid || seenIds.has(record.uid)) return false;
        seenIds.add(record.uid);
        return true;
      });
      status.textContent = records.length
        ? "Loaded " + records.length + " ClinVar records. Source classifications and review status are preserved."
        : "No ClinVar records matched this gene and filter.";
      renderAll();
    } catch (error) {
      if (requestGeneration === generation) {
        status.textContent = error.name === "AbortError"
          ? "ClinVar search timed out. Please retry."
          : "ClinVar records could not be retrieved. No sample or fabricated variants are shown. "
            + error.message;
      }
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        submit.disabled = false;
        submit.textContent = "Search ClinVar variants";
        loadMore.disabled = false;
      }
    }
  }

  async function more() {
    if (busy || !current || !current.has_more || !activeQuery) return;
    busy = true;
    loadMore.disabled = true;
    const requestGeneration = generation;
    const nextStart = current.query.retstart + current.returned;
    try {
      const data = await fetchPage(nextStart, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      const fresh = data.records.filter((record) => {
        if (!record?.uid || seenIds.has(record.uid)) return false;
        seenIds.add(record.uid);
        return true;
      });
      records.push(...fresh);
      current = data;
      if (!fresh.length && data.has_more) current.has_more = false;
      status.textContent = "Loaded " + records.length + " ClinVar records. Each page is retrieved from the current public index.";
      renderAll();
    } catch (error) {
      status.textContent = "More ClinVar records could not be loaded. " + error.message;
    } finally {
      busy = false;
      loadMore.disabled = false;
    }
  }

  function exportResults() {
    if (!current) return;
    const payload = {
      schema_version: "genomeguard.clinvar-research-export.v1",
      generated_at: new Date().toISOString(),
      query: activeQuery,
      loaded_count: records.length,
      source_response: current,
      records,
      interpretation_limits: [
        "ClinVar classifications are variant-level assertions, not patient-specific interpretations.",
        "Germline, somatic clinical-impact, and somatic oncogenicity classifications are distinct fields.",
        "Review status and conflicting interpretations are preserved as supplied by ClinVar.",
        "A ClinVar classification is not a diagnosis or treatment recommendation.",
      ],
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "genomeguard-clinvar-" + activeQuery.gene_symbol.toLowerCase() + ".json";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  form.addEventListener("submit", search);
  loadMore.addEventListener("click", more);
  exportJson.addEventListener("click", exportResults);
  return root;
}
