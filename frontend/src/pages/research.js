import { h } from "../ui.js";
import { renderOpenTargetsPanel } from "./open-targets.js";
import { renderClinVarPanel } from "./clinvar.js";
import { renderGwasPanel } from "./gwas.js";

const API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search";
const PUBMED_API = "/literature/pubmed/search";
const PAGE_SIZE = 20;
const DEPARTMENTS = [
  ["Genetics & Genomics", "genetics", 'genetics OR genomics'],
  ["Oncology", "oncology", 'oncology OR cancer OR neoplasm'],
  ["Neurology", "neurology", 'neurology OR neurological OR neurodegenerative'],
  ["Cardiology", "cardiology", 'cardiology OR cardiovascular OR heart'],
  ["Immunology", "immunology", 'immunology OR immune OR immunological'],
  ["Rare Diseases", "rare-diseases", '"rare disease" OR orphan'],
  ["Bioinformatics", "bioinformatics", 'bioinformatics OR "computational biology"'],
  ["Pharmacogenomics", "pharmacogenomics", 'pharmacogenomics OR pharmacogenetics'],
];

function safeExternal(url, label, className = "source-link") {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: className }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

function articleUrl(article) {
  if (article.doi) return "https://doi.org/" + encodeURIComponent(article.doi);
  if (article.pmid) return "https://pubmed.ncbi.nlm.nih.gov/" + encodeURIComponent(article.pmid) + "/";
  if (article.pmcid) return "https://europepmc.org/articles/" + encodeURIComponent(article.pmcid);
  return "https://europepmc.org/search?query=" + encodeURIComponent(article.title || "");
}

function paperCard(article) {
  const authors = article.authorString || "Authors not supplied by source";
  const journal = [article.journalTitle || article.journalInfo?.journal?.title, article.firstPublicationDate?.slice(0, 4)]
    .filter(Boolean).join(" · ") || "Publication details unavailable";
  const identifiers = [
    article.pmid ? "PMID " + article.pmid : "",
    article.pmcid || "",
    article.doi ? "DOI " + article.doi : "",
  ].filter(Boolean).join(" · ");
  return h("article", { class: "card research-paper" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, article.source || "Europe PMC"),
      article.isOpenAccess === "Y" ? h("span", { class: "fine" }, "Open access") : null,
      h("span", { class: "fine" }, journal)),
    h("h3", {}, article.title || "Untitled publication"),
    h("p", { class: "muted" }, authors),
    identifiers ? h("p", { class: "fine" }, identifiers) : null,
    article.abstractText
      ? h("details", {}, h("summary", {}, "Read abstract"),
        h("p", { class: "research-abstract" }, article.abstractText))
      : h("p", { class: "fine muted" }, "No abstract is available in this record."),
    h("div", { class: "source-links" },
      safeExternal(articleUrl(article), "Open publication"),
      article.pmid ? safeExternal("https://pubmed.ncbi.nlm.nih.gov/" + encodeURIComponent(article.pmid) + "/", "PubMed") : null));
}

function buildQuery(question, department) {
  const terms = question.trim();
  const selected = DEPARTMENTS.find(([, slug]) => slug === department);
  const departmentQuery = selected?.[2] || "";
  if (departmentQuery && terms) return "(" + departmentQuery + ") AND (" + terms + ")";
  return departmentQuery || terms;
}

function parseSearchResponse(data) {
  if (!data || !data.resultList || !Array.isArray(data.resultList.result)
      || !Number.isFinite(Number(data.hitCount))) {
    throw new Error("The literature provider returned an unexpected response.");
  }
  return {
    papers: data.resultList.result.filter((paper) => paper && typeof paper === "object"),
    hitCount: Math.max(0, Number(data.hitCount)),
    nextCursorMark: typeof data.nextCursorMark === "string" ? data.nextCursorMark : "",
  };
}

export async function render() {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const initialDepartment = params.get("department") || "";
  const initialQuery = params.get("q") || "";
  const root = h("div", { class: "stack source-page research-discovery" },
    h("section", { class: "card hero source-hero" },
      h("div", { class: "hero-copy" },
        h("p", { class: "eyebrow" }, "SCIENTIFIC LITERATURE · PUBLICATION SEARCH"),
        h("h1", {}, "Research discovery"),
        h("p", { class: "lede" }, "Explore biomedical literature by department, symptom description, or research question. Results come from a live scientific publication index—not generated citations."),
        h("div", { class: "dataset-hero-meta" },
          h("span", { class: "status-dot" }, "Live Europe PMC index"),
          h("span", { class: "muted" }, "Research discovery only · Not clinical advice")))),
    h("section", { class: "card stack" },
      h("div", {},
        h("h2", {}, "Explore by department"),
        h("p", { class: "muted" }, "Choose a department to immediately open its publication results, then refine the search with a research question.")),
      h("div", { class: "grid g2 research-departments", "aria-label": "Research departments" },
        ...DEPARTMENTS.map(([label, slug]) => h("a", {
          class: "research-department",
          href: "#/research?department=" + encodeURIComponent(slug),
          "aria-current": initialDepartment === slug ? "true" : "false",
        }, h("strong", {}, label), h("span", { class: "muted" }, "Browse publications →"))))),
    h("section", { class: "card stack" },
      h("div", {},
        h("h2", {}, "Search research literature"),
        h("p", { class: "muted" }, "Describe a symptom, biological process, condition, gene, or research question. Avoid names, contact details, or other identifying patient information.")),
      h("form", { class: "research-search-form" },
        h("label", { for: "research-question" }, "Research question or symptom description"),
        h("textarea", { id: "research-question", name: "q", rows: "3", maxlength: "500",
          placeholder: "e.g. published research on BRCA1 variants and ovarian cancer risk" }),
        h("label", { for: "research-department" }, "Research department"),
        h("select", { id: "research-department", name: "department" },
          h("option", { value: "" }, "All biomedical fields"),
          ...DEPARTMENTS.map(([label, slug]) => h("option", { value: slug }, label))),
        h("label", { for: "research-source" }, "Publication sources"),
        h("select", { id: "research-source", name: "source" },
          h("option", { value: "both" }, "Europe PMC + PubMed"),
          h("option", { value: "europe-pmc" }, "Europe PMC only"),
          h("option", { value: "pubmed" }, "PubMed only")),
        h("div", { class: "hero-actions" },
          h("button", { class: "btn", type: "submit" }, "Search publications"),
          h("span", { class: "fine muted" }, "Sources: Europe PMC and NCBI PubMed · source metadata"))),
      h("div", { id: "research-status", class: "fine muted", role: "status", "aria-live": "polite" }),
      h("div", { id: "research-results", class: "stack", "aria-live": "polite" })),
    renderOpenTargetsPanel(),
    renderClinVarPanel(),
    renderGwasPanel(),
    h("section", { class: "card" },
      h("h2", {}, "How to interpret these results"),
      h("p", { class: "muted" }, "This tool searches publication records and displays source-provided metadata and abstracts. It does not diagnose, rank treatment options, establish causality, or determine whether a paper is clinically applicable. Publication relevance is not evidence quality; review study design, population, limitations, and the original paper before drawing conclusions."),
      h("p", { class: "fine muted" }, "Search providers: Europe PMC and NCBI PubMed. Search terms are sent to the selected public providers. Do not enter personal health information.")));

  const form = root.querySelector(".research-search-form");
  const question = root.querySelector("#research-question");
  const department = root.querySelector("#research-department");
  const sourceFilter = root.querySelector("#research-source");
  const status = root.querySelector("#research-status");
  const results = root.querySelector("#research-results");
  const submitButton = form.querySelector('button[type="submit"]');
  let activeController = null;
  let activeQuery = "";
  let nextCursors = { europe: "*", pubmed: 0 };
  let providerHasMore = { europe: false, pubmed: false };
  let totalHits = 0;
  let loadedCount = 0;
  let hasMore = false;
  let requestGeneration = 0;
  let seenKeys = new Set();

  if (DEPARTMENTS.some(([, slug]) => slug === initialDepartment)) department.value = initialDepartment;
  question.value = initialQuery.slice(0, 500);

  function dedupeKey(paper) {
    const pmid = String(paper.pmid || "").trim();
    if (pmid) return "pmid:" + pmid;
    const doi = String(paper.doi || "").trim().toLowerCase();
    if (doi) return "doi:" + doi;
    const pmcid = String(paper.pmcid || "").trim().toLowerCase();
    if (pmcid) return "pmcid:" + pmcid;
    return "title:" + String(paper.title || "").trim().toLowerCase().replace(/\\s+/g, " ");
  }

  function normalizePubMed(paper) {
    return {
      ...paper,
      source: "PubMed",
      authorString: Array.isArray(paper.authors) ? paper.authors.join(", ") : "",
      journalTitle: paper.journal || "",
      firstPublicationDate: paper.publication_date || "",
      abstractText: paper.abstract || "",
      isOpenAccess: "N",
    };
  }

  async function fetchEuropePMC(query, cursorMark, signal) {
    const url = API + "?query=" + encodeURIComponent(query)
      + "&format=json&resultType=core&pageSize=" + PAGE_SIZE
      + "&cursorMark=" + encodeURIComponent(cursorMark) + "&synonym=true";
    const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
    if (!response.ok) throw new Error("Europe PMC returned HTTP " + response.status + ".");
    const data = parseSearchResponse(await response.json());
    return {
      provider: "Europe PMC",
      papers: data.papers.map((paper) => ({ ...paper, source: "Europe PMC" })),
      total: data.hitCount,
      nextCursor: data.nextCursorMark,
      hasMore: Boolean(data.papers.length && data.nextCursorMark && data.nextCursorMark !== cursorMark),
    };
  }

  async function fetchPubMed(query, retstart, signal) {
    const response = await fetch(PUBMED_API, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ q: query, retstart, retmax: PAGE_SIZE }),
      signal,
    });
    if (!response.ok) {
      let detail = "PubMed returned HTTP " + response.status + ".";
      if (response.status === 429) detail = "PubMed is busy; wait briefly and retry.";
      throw new Error(detail);
    }
    const data = await response.json();
    if (!data || data.provider !== "PubMed" || !Array.isArray(data.papers)
        || !Number.isFinite(Number(data.count)) || !Number.isFinite(Number(data.returned))) {
      throw new Error("PubMed returned an unexpected response.");
    }
    return {
      provider: "PubMed",
      papers: data.papers.map(normalizePubMed),
      total: Number(data.count),
      nextCursor: Number(retstart) + Number(data.returned),
      hasMore: Boolean(data.has_more && data.returned > 0),
    };
  }

  async function fetchPage(query, cursors) {
    if (activeController) activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    const selected = sourceFilter.value;
    const requested = [];
    if (selected === "both" || selected === "europe-pmc") {
      requested.push(fetchEuropePMC(query, cursors.europe, controller.signal));
    }
    if (selected === "both" || selected === "pubmed") {
      requested.push(fetchPubMed(query, cursors.pubmed, controller.signal));
    }
    try {
      const settled = await Promise.allSettled(requested);
      const successful = settled.filter((item) => item.status === "fulfilled").map((item) => item.value);
      const errors = settled.filter((item) => item.status === "rejected").map((item) => item.reason);
      if (!successful.length) throw new Error(errors.map((error) => error.message).join(" "));
      const papers = [];
      for (const provider of successful) {
        for (const paper of provider.papers) {
          const key = dedupeKey(paper);
          if (!seenKeys.has(key)) {
            seenKeys.add(key);
            papers.push(paper);
          }
        }
      }
      const next = { ...cursors };
      const more = { europe: false, pubmed: false };
      for (const provider of successful) {
        if (provider.provider === "Europe PMC") {
          next.europe = provider.nextCursor || cursors.europe;
          more.europe = provider.hasMore;
        } else {
          next.pubmed = provider.nextCursor;
          more.pubmed = provider.hasMore;
        }
      }
      const total = successful.reduce((sum, provider) => sum + provider.total, 0);
      return {
        papers,
        total,
        nextCursors: next,
        providerHasMore: more,
        hasMore: Object.values(more).some(Boolean),
        errors,
        providers: successful.map((provider) => provider.provider),
      };
    } finally {
      clearTimeout(timeout);
    }
  }

  function renderLoadMore() {
    const old = results.querySelector("#research-load-more");
    old?.remove();
    if (!hasMore || loadedCount === 0) return;
    const button = h("button", { id: "research-load-more", class: "btn secondary", type: "button" },
      "Load more publications");
    button.addEventListener("click", loadMore);
    results.append(button);
  }

  async function loadMore() {
    const button = results.querySelector("#research-load-more");
    if (!button || !activeQuery) return;
    button.disabled = true;
    button.textContent = "Loading…";
    const generation = requestGeneration;
    try {
      const data = await fetchPage(activeQuery, nextCursors);
      if (generation !== requestGeneration) return;
      if (data.papers.length) {
        results.insertBefore(
          h("div", { class: "research-paper-page" }, ...data.papers.map(paperCard)),
          button,
        );
      }
      loadedCount += data.papers.length;
      totalHits = data.total;
      nextCursors = data.nextCursors;
      providerHasMore = data.providerHasMore;
      hasMore = data.hasMore;
      const providerText = data.providers.join(" + ");
      status.textContent = data.papers.length
        ? "Showing " + loadedCount + " records from " + providerText + ". Results are source-indexed, not clinical recommendations."
        : "No additional unique records were returned by the selected sources.";
      if (data.errors.length) status.textContent += " One source was unavailable: " + data.errors.map((e) => e.message).join(" ");
      renderLoadMore();
    } catch (error) {
      if (generation !== requestGeneration) return;
      status.textContent = error.name === "AbortError"
        ? "The literature search timed out. Please try again."
        : "More results could not be loaded. " + error.message;
      button.disabled = false;
      button.textContent = "Retry loading more";
    }
  }

  async function search(event) {
    event?.preventDefault();
    const text = question.value.trim();
    if (text.length > 500) {
      status.textContent = "Keep the search under 500 characters.";
      return;
    }
    if (text.length < 3 && !department.value) {
      status.textContent = "Enter at least 3 characters or choose a research department.";
      question.focus();
      return;
    }
    const query = buildQuery(text, department.value);
    if (!query.trim()) {
      status.textContent = "Choose a department or enter a research question.";
      return;
    }
    const generation = ++requestGeneration;
    activeQuery = query;
    nextCursors = { europe: "*", pubmed: 0 };
    providerHasMore = { europe: false, pubmed: false };
    loadedCount = 0;
    totalHits = 0;
    hasMore = false;
    seenKeys = new Set();
    status.textContent = "Searching selected publication sources…";
    results.replaceChildren();
    submitButton.disabled = true;
    submitButton.textContent = "Searching…";
    try {
      const data = await fetchPage(query, nextCursors);
      if (generation !== requestGeneration) return;
      nextCursors = data.nextCursors;
      totalHits = data.total;
      loadedCount = data.papers.length;
      providerHasMore = data.providerHasMore;
      hasMore = data.hasMore;
      if (data.papers.length) {
        results.append(h("div", { class: "research-paper-page" }, ...data.papers.map(paperCard)));
        status.textContent = "Showing " + loadedCount + " unique publications from "
          + data.providers.join(" + ") + ". Results are source-indexed, not clinical recommendations.";
      } else {
        status.textContent = "No publication records matched this search. Try broader terms or another department.";
      }
      if (data.errors.length) status.textContent += " One source was unavailable: " + data.errors.map((e) => e.message).join(" ");
      renderLoadMore();
    } catch (error) {
      if (generation !== requestGeneration) return;
      status.textContent = error.name === "AbortError"
        ? "The literature search timed out. Please try again."
        : "The live literature sources could not be reached. No sample or fabricated papers are shown. " + error.message;
    } finally {
      if (generation === requestGeneration) {
        submitButton.disabled = false;
        submitButton.textContent = "Search publications";
      }
    }
  }

  form.addEventListener("submit", search);
  sourceFilter.addEventListener("change", () => { if (activeQuery) search(); });
  if (initialDepartment || initialQuery) {
    if (!question.value && !initialDepartment) {
      status.textContent = "Enter a research question or select a department to begin.";
    } else {
      // Department links are useful on their own: opening one performs a real, source-backed search.
      search();
    }
  }
  return root;
}
