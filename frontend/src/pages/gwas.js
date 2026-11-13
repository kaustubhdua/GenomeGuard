import { h } from "../ui.js";

const ENDPOINT = "/research/gwas/search";
const API_DOCS = "https://www.ebi.ac.uk/gwas/rest/api/v2/docs";
const PAGE_SIZE = 20;

function safeExternal(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", {
      href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "source-link",
    }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

function display(value) {
  return value === null || value === undefined || value === "" ? "Not reported" : String(value);
}

function formatPValue(record) {
  if (Number.isFinite(record.pvalue_mantissa) && Number.isFinite(record.pvalue_exponent)) {
    return record.pvalue_mantissa + " × 10^" + record.pvalue_exponent;
  }
  if (typeof record.p_value === "number" && Number.isFinite(record.p_value)) {
    return record.p_value.toExponential(2);
  }
  return display(record.p_value);
}

function associationCard(record) {
  const traits = [
    ...(record.reported_traits || []),
    ...(record.efo_traits || []).map((trait) => trait.label).filter(Boolean),
  ];
  const uniqueTraits = [...new Set(traits)];
  const alleles = (record.snp_alleles || []).map((allele) => [
    allele.rs_id, allele.effect_allele ? "effect allele " + allele.effect_allele : "",
  ].filter(Boolean).join(" — "));
  const effect = record.beta || (
    record.odds_ratio_text ? "Odds ratio " + record.odds_ratio_text
      : record.odds_ratio !== null && record.odds_ratio !== undefined
        ? "Odds ratio " + record.odds_ratio : "Not reported"
  );
  return h("article", { class: "card research-paper gwas-record" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, "GWAS Catalog"),
      h("span", { class: "fine" }, "Association " + record.association_id)),
    h("h3", {}, uniqueTraits.join(" · ") || "Association without a reported trait"),
    h("p", { class: "fine" }, "Study: " + display(record.study_accession)
      + " · First author: " + display(record.first_author)),
    h("p", { class: "fine muted" }, "Mapped gene(s): "
      + ((record.mapped_genes || []).join(", ") || "Not reported")
      + " · Location(s): " + ((record.locations || []).join(", ") || "Not reported")),
    h("p", { class: "fine muted" }, "Variant(s): "
      + (alleles.join(" · ") || "Not reported")),
    h("div", { class: "gwas-metrics" },
      h("div", { class: "gwas-metric" },
        h("strong", {}, "Reported p-value"),
        h("span", {}, formatPValue(record)),
        record.pvalue_description ? h("small", {}, record.pvalue_description) : null),
      h("div", { class: "gwas-metric" },
        h("strong", {}, "Effect estimate"),
        h("span", {}, effect),
        h("small", {}, "Beta / odds ratio as supplied by the Catalog"))),
    h("p", { class: "fine muted" }, "Risk/effect allele frequency: "
      + display(record.risk_frequency)
      + " · Confidence interval: " + display(record.confidence_interval?.text)),
    h("div", { class: "source-links" },
      record.source_url ? safeExternal(record.source_url, "GWAS association") : null,
      record.study_url ? safeExternal(record.study_url, "Study record") : null,
      record.pubmed_url ? safeExternal(record.pubmed_url, "PubMed publication") : null,
      record.snp_url ? safeExternal(record.snp_url, "SNP record") : null,
      record.loci_url ? safeExternal(record.loci_url, "Locus evidence") : null));
}

export function renderGwasPanel() {
  const root = h("section", {
    class: "card stack gwas-panel",
    "aria-labelledby": "gwas-heading",
  },
    h("div", {},
      h("p", { class: "eyebrow" }, "GENETIC ASSOCIATIONS · GWAS CATALOG"),
      h("h2", { id: "gwas-heading" }, "GWAS Catalog associations"),
      h("p", { class: "muted" },
        "Explore literature-curated variant–trait associations by gene, rsID, or ontology trait. The source release, mapped genes, p-values, effect estimates, ancestry-independent metadata, and original study links are retained."),
      h("p", { class: "fine muted" },
        "The GWAS Catalog REST API v2 exposes curated top associations and metadata—not full genome-wide summary statistics. Association is not causation, clinical validity, or an individual risk estimate.")),
    h("form", { id: "gwas-search-form", class: "research-search-form" },
      h("label", { for: "gwas-gene-symbol" }, "Gene symbol (optional)"),
      h("input", {
        id: "gwas-gene-symbol", name: "gene_symbol", type: "text",
        maxlength: "20", placeholder: "BRCA1", autocomplete: "off",
      }),
      h("label", { for: "gwas-rs-id" }, "Variant rsID (optional)"),
      h("input", {
        id: "gwas-rs-id", name: "rs_id", type: "text",
        maxlength: "24", placeholder: "rs10445316", autocomplete: "off",
      }),
      h("label", { for: "gwas-trait" }, "Trait / phenotype (optional)"),
      h("input", {
        id: "gwas-trait", name: "trait", type: "text",
        maxlength: "100", placeholder: "breast cancer", autocomplete: "off",
      }),
      h("label", { class: "gwas-child-traits-label" },
        h("input", { id: "gwas-child-traits", type: "checkbox" }),
        "Include more specific child ontology traits"),
      h("div", { class: "hero-actions" },
        h("button", { class: "btn", type: "submit" }, "Search GWAS Catalog"),
        safeExternal(API_DOCS, "GWAS Catalog API v2 documentation"))),
    h("div", {
      id: "gwas-status", class: "fine muted", role: "status", "aria-live": "polite",
    }, "Enter a gene symbol, rsID, or trait to search the current GWAS Catalog release."),
    h("div", { id: "gwas-summary", class: "grid g2" }),
    h("div", { id: "gwas-results", class: "stack", "aria-live": "polite" }),
    h("div", { class: "hero-actions" },
      h("button", { id: "gwas-load-more", class: "btn secondary", type: "button", hidden: true },
        "Load more GWAS associations"),
      h("button", { id: "gwas-export-json", class: "btn secondary", type: "button", disabled: true },
        "Export GWAS JSON")),
    h("div", { id: "gwas-provenance", class: "card stack" },
      h("h3", {}, "GWAS Catalog release provenance"),
      h("p", { class: "fine muted" },
        "The API version, data release, gene build, ontology version, license, query parameters, and retrieval time appear here after a successful search.")));

  const form = root.querySelector("#gwas-search-form");
  const geneInput = root.querySelector("#gwas-gene-symbol");
  const rsInput = root.querySelector("#gwas-rs-id");
  const traitInput = root.querySelector("#gwas-trait");
  const childInput = root.querySelector("#gwas-child-traits");
  const status = root.querySelector("#gwas-status");
  const summary = root.querySelector("#gwas-summary");
  const results = root.querySelector("#gwas-results");
  const loadMore = root.querySelector("#gwas-load-more");
  const exportJson = root.querySelector("#gwas-export-json");
  const provenance = root.querySelector("#gwas-provenance");
  const submit = form.querySelector('button[type="submit"]');

  let current = null;
  let records = [];
  let activeQuery = null;
  let generation = 0;
  let busy = false;
  let activeController = null;
  let seenIds = new Set();

  function renderAll() {
    results.replaceChildren(...records.map(associationCard));
    summary.replaceChildren();
    if (current) {
      summary.append(
        h("article", { class: "card research-paper" },
          h("span", { class: "tag" }, "GWAS Catalog release"),
          h("h3", {}, current.provenance.data_release_date || "Release date unavailable"),
          h("p", { class: "fine" }, "API v" + current.api_version
            + " · " + current.count + " total associations"),
          h("p", { class: "fine muted" }, "Gene build: "
            + display(current.provenance.gene_build)
            + " · EFO: " + display(current.provenance.efo_version))),
        h("article", { class: "card research-paper" },
          h("span", { class: "tag" }, "Loaded associations"),
          h("h3", {}, String(records.length) + " of " + String(current.count)),
          h("p", { class: "fine muted" }, "Source order is preserved; GenomeGuard does not rank by p-value.")));
      provenance.replaceChildren(
        h("h3", {}, "GWAS Catalog release provenance"),
        h("p", { class: "fine" }, "API: " + current.provenance.api
          + " · Version: " + current.provenance.api_version),
        h("p", { class: "fine" }, "Data release: " + display(current.provenance.data_release_date)
          + " · API release: " + display(current.provenance.api_release_date)),
        h("p", { class: "fine" }, "dbSNP build: " + display(current.provenance.dbsnp_build)
          + " · Gene build: " + display(current.provenance.gene_build)),
        h("p", { class: "fine" }, "EFO: " + display(current.provenance.efo_version)
          + " · Ensembl: " + display(current.provenance.ensembl_version)),
        h("p", { class: "fine" }, "Commit: " + display(current.provenance.commit_hash)
          + " · Retrieved at: " + current.provenance.retrieved_at),
        h("p", { class: "fine muted" }, "License: " + display(current.provenance.license)),
        h("p", { class: "fine muted" }, current.provenance.scope_note),
        h("div", { class: "source-links" },
          safeExternal(current.provenance.source_url, "GWAS Catalog API"),
          current.provenance.license_url
            ? safeExternal(current.provenance.license_url, "API license") : null));
    } else {
      provenance.replaceChildren(
        h("h3", {}, "GWAS Catalog release provenance"),
        h("p", { class: "fine muted" },
          "The API version, data release, gene build, ontology version, license, query parameters, and retrieval time appear here after a successful search."));
    }
    loadMore.hidden = !current || !current.has_more;
    loadMore.disabled = busy;
    exportJson.disabled = !current;
  }

  async function fetchPage(page, requestGeneration) {
    if (activeController) activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ ...activeQuery, page, size: PAGE_SIZE }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (requestGeneration !== generation) return null;
      if (!response.ok) {
        throw new Error(data.message || "GWAS Catalog returned HTTP " + response.status + ".");
      }
      if (!data || data.provider !== "GWAS Catalog" || !Array.isArray(data.records)
          || !data.provenance || !data.page) {
        throw new Error("GWAS Catalog returned an unexpected response.");
      }
      return data;
    } finally {
      clearTimeout(timeout);
    }
  }

  async function search(event) {
    event?.preventDefault();
    const geneSymbol = geneInput.value.trim().toUpperCase();
    const rsId = rsInput.value.trim().toLowerCase();
    const trait = traitInput.value.trim();
    if (!geneSymbol && !rsId && !trait) {
      status.textContent = "Enter at least one gene symbol, rsID, or trait.";
      geneInput.focus();
      return;
    }
    if (geneSymbol && !/^[A-Z][A-Z0-9.-]{0,19}$/.test(geneSymbol)) {
      status.textContent = "Enter a valid gene symbol.";
      geneInput.focus();
      return;
    }
    if (rsId && !/^rs[0-9]+$/.test(rsId)) {
      status.textContent = "Enter an rsID using rs followed by digits.";
      rsInput.focus();
      return;
    }
    if (trait && (trait.length < 2 || trait.length > 100 || /[\x00-\x1f]/.test(trait))) {
      status.textContent = "Trait search must contain 2 to 100 printable characters.";
      traitInput.focus();
      return;
    }
    if (activeController) activeController.abort();
    activeQuery = {
      gene_symbol: geneSymbol || null,
      rs_id: rsId || null,
      trait: trait || null,
      show_child_traits: Boolean(childInput.checked && trait),
    };
    generation += 1;
    const requestGeneration = generation;
    current = null;
    records = [];
    seenIds = new Set();
    busy = true;
    submit.disabled = true;
    submit.textContent = "Searching…";
    status.textContent = "Retrieving current GWAS Catalog v2 associations and release metadata…";
    renderAll();
    try {
      const data = await fetchPage(0, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      current = data;
      records = data.records.filter((record) => {
        if (!record?.association_id || seenIds.has(record.association_id)) return false;
        seenIds.add(record.association_id);
        return true;
      });
      status.textContent = records.length
        ? "Loaded " + records.length + " literature-curated GWAS associations."
        : "No GWAS Catalog associations matched this query.";
      renderAll();
    } catch (error) {
      if (requestGeneration === generation) {
        status.textContent = error.name === "AbortError"
          ? "GWAS Catalog search timed out. Please retry."
          : "GWAS Catalog records could not be retrieved. No sample or fabricated associations are shown. "
            + error.message;
      }
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        submit.disabled = false;
        submit.textContent = "Search GWAS Catalog";
        loadMore.disabled = false;
      }
    }
  }

  async function more() {
    if (busy || !current || !current.has_more || !activeQuery) return;
    busy = true;
    loadMore.disabled = true;
    const requestGeneration = generation;
    try {
      const data = await fetchPage(current.page.number + 1, requestGeneration);
      if (!data || requestGeneration !== generation) return;
      const fresh = data.records.filter((record) => {
        if (!record?.association_id || seenIds.has(record.association_id)) return false;
        seenIds.add(record.association_id);
        return true;
      });
      records.push(...fresh);
      current = data;
      if (!fresh.length && data.has_more) current.has_more = false;
      status.textContent = "Loaded " + records.length + " GWAS associations from the current Catalog release.";
      renderAll();
    } catch (error) {
      if (requestGeneration === generation) {
        status.textContent = error.name === "AbortError"
          ? "GWAS Catalog pagination timed out. Please retry."
          : "More GWAS associations could not be loaded. " + error.message;
      }
    } finally {
      if (requestGeneration === generation) {
        busy = false;
        loadMore.disabled = false;
      }
    }
  }

  function exportResults() {
    if (!current) return;
    const payload = {
      schema_version: "genomeguard.gwas-catalog-research-export.v1",
      generated_at: new Date().toISOString(),
      query: activeQuery,
      loaded_count: records.length,
      source_response: current,
      records,
      interpretation_limits: [
        "The GWAS Catalog REST API v2 provides literature-curated top associations and metadata.",
        "The API does not provide full genome-wide summary statistics.",
        "Association and p-values do not establish causation, clinical validity, or individual risk.",
        "Effect estimates, alleles, mapped genes, and traits are preserved as source-reported.",
      ],
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "genomeguard-gwas-" + (activeQuery.gene_symbol || activeQuery.rs_id || "trait") + ".json";
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
