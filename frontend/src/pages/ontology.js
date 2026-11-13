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

function termCard(term, onUse) {
  const ontology = String(term.ontology || "").toLowerCase();
  const termUrl = "https://www.ebi.ac.uk/ols4/ontologies/" + encodeURIComponent(ontology)
    + "/classes?iri=" + encodeURIComponent(term.iri || "");
  const useButton = h("button", { class: "btn secondary", type: "button" },
    "Add term to publication query");
  useButton.addEventListener("click", () => onUse(term, false));
  const findButton = h("button", { class: "btn", type: "button" },
    "Find research papers for this term");
  findButton.addEventListener("click", () => onUse(term, true));
  return h("article", { class: "card research-paper ontology-term" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, String(term.ontology_prefix || ontology).toUpperCase()),
      h("span", { class: "fine" }, term.obo_id || term.iri || "Identifier not supplied"),
      term.is_obsolete ? h("span", { class: "fine" }, "Obsolete") : null),
    h("h3", {}, term.label || "Unnamed ontology term"),
    term.description ? h("p", { class: "muted" }, term.description) : null,
    Array.isArray(term.synonyms) && term.synonyms.length
      ? h("p", { class: "fine muted" }, "Synonyms: " + term.synonyms.join("; ")) : null,
    safeExternal(termUrl, "View source term"),
    h("div", { class: "hero-actions" }, useButton, findButton));
}

export function renderOntologyPanel() {
  const root = h("section", { class: "card stack ontology-panel", "aria-labelledby": "ontology-heading" },
    h("div", {},
      h("p", { class: "eyebrow" }, "SYMPTOM-TO-RESEARCH DISCOVERY · ONTOLOGY-ASSISTED SEARCH"),
      h("h2", { id: "ontology-heading" }, "Start with a symptom or phenotype"),
      h("p", { class: "muted" },
        "Describe a symptom in plain language. GenomeGuard searches official Human Phenotype Ontology terms, shows candidate matches and their synonyms, then searches live publication indexes when you choose a term. This is explainable terminology-assisted retrieval—not diagnosis or an AI-generated medical conclusion.")),
    h("form", { id: "ontology-search-form", class: "research-search-form" },
      h("label", { for: "ontology-query" }, "Symptom, disease, or phenotype"),
      h("input", { id: "ontology-query", type: "search", maxlength: "120",
        placeholder: "e.g. recurring headaches, muscle weakness, ataxia", required: true }),
      h("label", { for: "ontology-filter" }, "Terminology source"),
      h("select", { id: "ontology-filter" },
        h("option", { value: "hp", selected: true }, "HPO — Human Phenotype Ontology (recommended for symptoms)"),
        h("option", { value: "all" }, "All supported ontologies"),
        h("option", { value: "mondo" }, "MONDO — Disease Ontology"),
        h("option", { value: "doid" }, "DOID — Disease Ontology")),
      h("button", { class: "btn", type: "submit" }, "Find matching phenotype terms")),
    h("div", { id: "ontology-status", class: "fine muted", role: "status", "aria-live": "polite" },
      "Step 1: find source-backed phenotype terms. Step 2: choose a term to retrieve related research papers."),
    h("div", { id: "ontology-results", class: "stack", "aria-live": "polite" }),
    h("button", { id: "ontology-more", class: "btn secondary", type: "button", hidden: true },
      "Load more terms"),
    h("p", { class: "fine muted" },
      "Sources: EMBL-EBI OLS4, Europe PMC, and NCBI PubMed. Search text is sent to public research providers. Do not enter patient names, identifiers, records, or other private clinical information. Retrieved papers are research references, not diagnosis or treatment advice."));
  const form = root.querySelector("#ontology-search-form");
  const queryInput = root.querySelector("#ontology-query");
  const filter = root.querySelector("#ontology-filter");
  const status = root.querySelector("#ontology-status");
  const results = root.querySelector("#ontology-results");
  const more = root.querySelector("#ontology-more");
  let query = "";
  let ontology = "hp";
  let page = 0;
  let total = 0;
  let busy = false;
  let generation = 0;
  let seen = new Set();

  function useTerm(term, searchNow) {
    const literatureQuestion = document.getElementById("research-question");
    const literatureForm = document.querySelector(".research-search-form:not(#ontology-search-form)");
    if (!literatureQuestion || !literatureForm) {
      status.textContent = "The publication search panel is unavailable. Open Research discovery and try again.";
      return;
    }
    const phrases = [...new Set([term.label, ...(Array.isArray(term.synonyms) ? term.synonyms : [])]
      .filter((value) => typeof value === "string" && value.trim()))].slice(0, 4);
    if (!phrases.length) return;
    const expansion = "(" + phrases.map((value) => '"' + value.replace(/"/g, '\\"') + '"').join(" OR ") + ")";
    literatureQuestion.value = expansion;
    literatureQuestion.focus();
    if (searchNow) {
      status.textContent = "Searching Europe PMC and PubMed for publications matching the selected source phenotype and synonyms…";
      literatureForm.requestSubmit();
    } else {
      status.textContent = "Added the selected ontology label and source synonyms to the publication query. Review the query, then select Search publications.";
    }
  }

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
    status.textContent = "Searching official phenotype and disease terminology through OLS4…";
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
          results.append(termCard(term, useTerm));
        }
      }
      status.textContent = "Found " + seen.size + " candidate terms from " + (data.provider || "OLS4")
        + " · " + (data.retrieved_at || "retrieval time unavailable")
        + ". Select a term to search the publication databases.";
      if (!data.terms.length && page === 0) {
        results.append(h("p", { class: "muted" }, "No matching ontology terms were found. Try a broader symptom phrase or another terminology source."));
      }
    } catch (error) {
      if (current === generation) {
        status.textContent = "Phenotype term search unavailable. " + error.message;
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
