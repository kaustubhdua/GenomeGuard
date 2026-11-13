import { h } from "../ui.js";

const ENDPOINT = "/research/uniprot/search";
const SOURCE = "https://www.uniprot.org";

function safeExternal(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "source-link" }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

export function renderUniProtPanel() {
  const root = h("section", { class: "card stack uniprot-panel", "aria-labelledby": "uniprot-heading" },
    h("div", {},
      h("p", { class: "eyebrow" }, "PROTEIN ANNOTATION · UNIPROTKB"),
      h("h2", { id: "uniprot-heading" }, "Find reviewed human proteins"),
      h("p", { class: "muted" },
        "Search reviewed UniProtKB records by exact human gene symbol. Results include stable protein accessions, protein names, gene aliases, length and source-provided function annotations."),
      h("p", { class: "fine muted" },
        "Protein identity and function annotations are not variant interpretations, disease-causality evidence or clinical recommendations.")),
    h("form", { id: "uniprot-search-form", class: "research-search-form" },
      h("label", { for: "uniprot-symbol" }, "Human gene symbol"),
      h("input", { id: "uniprot-symbol", name: "symbol", type: "text", maxlength: "20",
        placeholder: "BRCA2", autocomplete: "off", required: true }),
      h("div", { class: "hero-actions" },
        h("button", { class: "btn", type: "submit" }, "Find proteins"),
        safeExternal(SOURCE, "UniProtKB"))),
    h("div", { id: "uniprot-status", class: "fine muted", role: "status", "aria-live": "polite" },
      "Enter a gene symbol such as BRCA2 or TP53."),
    h("div", { id: "uniprot-results", class: "stack", "aria-live": "polite" }));

  const form = root.querySelector("#uniprot-search-form");
  const input = root.querySelector("#uniprot-symbol");
  const status = root.querySelector("#uniprot-status");
  const results = root.querySelector("#uniprot-results");
  const submit = form.querySelector('button[type="submit"]');
  let generation = 0;

  function renderProteins(data) {
    const proteins = Array.isArray(data.proteins) ? data.proteins : [];
    if (!proteins.length) {
      results.replaceChildren(h("p", { class: "muted" }, "No reviewed human UniProtKB records matched this exact gene symbol."));
      return;
    }
    results.replaceChildren(...proteins.map((protein) => {
      const crossrefs = Array.isArray(protein.ensembl_cross_references)
        ? protein.ensembl_cross_references : [];
      const firstGeneId = crossrefs.find((item) => /^ENSG[0-9]{11}$/.test(item.gene_id || ""))?.gene_id;
      const actions = [
        safeExternal(protein.source_url, "Open UniProtKB record"),
      ];
      if (firstGeneId) {
        actions.push(h("button", {
          class: "btn secondary", type: "button",
          onclick: () => {
            const target = document.querySelector("#ot-ensembl-id");
            if (!target) {
              status.textContent = "The Open Targets panel is not available on this page.";
              return;
            }
            target.value = firstGeneId;
            target.focus();
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            status.textContent = "Ensembl gene ID transferred to Open Targets. Review it and run the search.";
          },
        }, "Use Ensembl gene ID in Open Targets"));
      }
      return h("article", { class: "card research-paper uniprot-record" },
        h("div", { class: "source-card-top" },
          h("span", { class: "tag" }, protein.reviewed ? "Reviewed · Swiss-Prot" : "Unreviewed"),
          h("span", { class: "fine" }, protein.organism || "Organism not supplied")),
        h("h3", {}, (protein.protein_name || "Protein name not supplied") + " · " + (protein.accession || "Accession unavailable")),
        h("p", { class: "fine" }, "Entry: " + (protein.entry_name || "Not supplied")
          + " · Gene names: " + ((protein.gene_names || []).join(", ") || "Not supplied")
          + " · Length: " + (protein.length_aa == null ? "Not supplied" : protein.length_aa + " aa")),
        protein.function ? h("p", { class: "fine" }, protein.function) : null,
        firstGeneId ? h("p", { class: "fine muted" }, "Ensembl gene cross-reference: " + firstGeneId) : null,
        h("div", { class: "source-links" }, ...actions));
    }));
  }

  async function search(event) {
    event.preventDefault();
    const symbol = input.value.trim();
    if (!/^[A-Za-z][A-Za-z0-9.-]{0,19}$/.test(symbol)) {
      status.textContent = "Enter a valid gene symbol containing 1 to 20 letters, digits, dots or hyphens.";
      return;
    }
    const current = ++generation;
    status.textContent = "Searching reviewed UniProtKB records…";
    results.replaceChildren();
    submit.disabled = true;
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ symbol, size: 5 }),
        cache: "no-store",
      });
      const data = await response.json();
      if (current !== generation) return;
      if (!response.ok) throw new Error(data.message || "UniProtKB search failed.");
      renderProteins(data);
      status.textContent = "UniProtKB release " + (data.release || "not supplied")
        + " · " + String(data.total_results ?? data.returned ?? 0) + " matching reviewed records.";
    } catch (error) {
      if (current !== generation) return;
      status.textContent = error.message || "UniProtKB is temporarily unavailable.";
    } finally {
      if (current === generation) submit.disabled = false;
    }
  }

  form.addEventListener("submit", search);
  return root;
}
