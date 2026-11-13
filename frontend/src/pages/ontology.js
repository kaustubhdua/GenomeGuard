import { h } from "../ui.js";

const API = "/research/ontology/search";
const PAGE_SIZE = 10;

function safeExternal(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || parsed.hostname !== "www.ebi.ac.uk") throw new Error("unsafe");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "source-link" }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

function termCard(term) {
  const ontology = String(term.ontology || "").toLowerCase();
  const termUrl = "https://www.ebi.ac.uk/ols4/ontologies/" + encodeURIComponent(ontology)
    + "/classes?iri=" + encodeURIComponent(term.iri || "");
  return h("article", { class: "card research-paper ontology-term" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, String(term.ontology_prefix || ontology).toUpperCase()),
      h("span", { class: "fine" }, term.obo_id || term.iri || "Identifier not supplied"),
      term.is_obsolete ? h("span", { class: "fine" }, "Obsolete") : null),
    h("h3", {}, term.label || "Unnamed ontology term"),
    term.description ? h("p", { class: "muted" }, term.description) : null,
    Array.isArray(term.synonyms) && term.synonyms.length
      ? h("p", { class: "fine muted" }, "Synonyms: " + term.synonyms.join("; ")) : null,
    safeExternal(termUrl, "View source term"));
}

export function renderOntologyPanel() {
  const root = h("section", { class: "card stack ontology-panel", "aria-labelledby": "ontology-heading" },
    h("div", {},
      h("p", { class: "eyebrow" }, "BIOMEDICAL ONTOLOGIES · SOURCE-BACKED TERM DISCOVERY"),
      h("h2", { id: "ontology-heading" }, "Disease and phenotype terminology"),
      h("p", { class: "muted" },
        "Search MONDO disease concepts, Human Phenotype Ontology terms, and Disease Ontology concepts. Results are candidate annotations; similar labels do not establish equivalence or diagnosis.")),
    h("form", { id: "ontology-search-form", class: "research-search-form" },
      h("label", { for: "ontology-query" }, "Disease or phenotype term"),
      h("input", { id: "ontology-query", type: "search", maxlength: "120",
        placeholder: "e.g. breast cancer, ataxia, developmental delay", required: true }),
      h("label", { for: "ontology-filter" }, "Ontology"),
      h("select", { id: "ontology-filter" },
        h("option", { value: "all" }, "All supported ontologies"),
        h("option", { value: "mondo" }, "MONDO — Disease Ontology"),
        h("option", { value: "hp" }, "HPO — Human Phenotype Ontology"),
        h("option", { value: "doid" }, "DOID — Disease Ontology")),
      h("button", { class: "btn", type: "submit" }, "Search ontology terms")),
    h("div", { id: "ontology-status", class: "fine muted", role: "status", "aria-live": "polite" },
      "Search official ontology terms and inspect their source identifiers."),
    h("div", { id: "ontology-results", class: "stack", "aria-live": "polite" }),
    h("button", { id: "ontology-more", class: "btn secondary", type: "button", hidden: true },
      "Load more terms"),
    h("p", { class: "fine muted" },
      "Source: EMBL-EBI Ontology Lookup Service (OLS4). Query text is sent to this public provider. Do not enter patient identifiers or private clinical information."));
  const form = root.querySelector("#ontology-search-form");
  const queryInput = root.querySelector("#ontology-query");
  const filter = root.querySelector("#ontology-filter");
  const status = root.querySelector("#ontology-status");
  const results = root.querySelector("#ontology-results");
  const more = root.querySelector("#ontology-more");
  let query = "";
  let ontology = "all";
  let page = 0;
  let total = 0;
  let busy = false;
  let generation = 0;
  let seen = new Set();

  function renderMore() {
    more.hidden = !query || (page + 1) * PAGE_SIZE >= total;
    more.disabled = busy;
  }

  async function load(reset) {
    if (busy) return;
    if (reset) {
      query = queryInput.value.trim();
      ontology = filter.value;
      page = 0;
      total = 0;
      seen = new Set();
      results.replaceChildren();
    }
    if (!query) {
      status.textContent = "Enter at least two characters.";
      return;
    }
    const current = ++generation;
    busy = true;
    renderMore();
    status.textContent = "Searching MONDO, HPO and Disease Ontology through OLS4…";
    try {
      const response = await fetch(API, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        cache: "no-store",
        body: JSON.stringify({ query, ontology, page, size: PAGE_SIZE }),
      });
      const data = await response.json();
      if (current !== generation) return;
      if (!response.ok) throw new Error(data.message || "Ontology search failed.");
      if (!Array.isArray(data.terms) || !Number.isFinite(Number(data.total))) {
        throw new Error("The ontology provider returned an unexpected response.");
      }
      total = Math.max(0, Number(data.total));
      for (const term of data.terms) {
        const key = String(term.ontology) + "|" + String(term.obo_id || term.iri);
        if (!seen.has(key)) {
          seen.add(key);
          results.append(termCard(term));
        }
      }
      status.textContent = "Loaded " + seen.size + " of " + total
        + " matching terms · " + (data.provider || "OLS4")
        + " · retrieved " + (data.retrieved_at || "time not supplied") + ".";
      if (!data.terms.length && page === 0) {
        results.append(h("p", { class: "muted" }, "No matching ontology terms were found."));
      }
    } catch (error) {
      if (current === generation) {
        status.textContent = "Ontology search unavailable. " + error.message;
      }
    } finally {
      if (current === generation) {
        busy = false;
        renderMore();
      }
    }
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    load(true);
  });
  more.addEventListener("click", () => {
    if (!busy && (page + 1) * PAGE_SIZE < total) {
      page += 1;
      load(false);
    }
  });
  return root;
}
