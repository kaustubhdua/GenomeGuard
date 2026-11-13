import { h } from "../ui.js";

const API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search";
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
      h("span", { class: "tag" }, article.isOpenAccess === "Y" ? "Open access" : "Publication record"),
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
        }, h("strong", {}, label), h("span", { class: "muted" }, "Browse publications →")))),
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
        h("div", { class: "hero-actions" },
          h("button", { class: "btn", type: "submit" }, "Search publications"),
          h("span", { class: "fine muted" }, "Source: Europe PMC · abstracts and metadata"))),
      h("div", { id: "research-status", class: "fine muted", role: "status", "aria-live": "polite" }),
      h("div", { id: "research-results", class: "stack", "aria-live": "polite" })),
    h("section", { class: "card" },
      h("h2", {}, "How to interpret these results"),
      h("p", { class: "muted" }, "This tool searches publication records and displays source-provided metadata and abstracts. It does not diagnose, rank treatment options, establish causality, or determine whether a paper is clinically applicable. Publication relevance is not evidence quality; review study design, population, limitations, and the original paper before drawing conclusions."),
      h("p", { class: "fine muted" }, "Search provider: Europe PMC, a public biomedical literature service. Search terms are sent to that provider. Do not enter personal health information.")));

  const form = root.querySelector(".research-search-form");
  const question = root.querySelector("#research-question");
  const department = root.querySelector("#research-department");
  const status = root.querySelector("#research-status");
  const results = root.querySelector("#research-results");
  const submitButton = form.querySelector('button[type="submit"]');
  let activeController = null;
  let activeQuery = "";
  let nextCursorMark = "*";
  let totalHits = 0;
  let loadedCount = 0;
  let hasMore = false;
  let requestGeneration = 0;

  if (DEPARTMENTS.some(([, slug]) => slug === initialDepartment)) department.value = initialDepartment;
  question.value = initialQuery.slice(0, 500);

  async function fetchPage(query, cursorMark) {
    if (activeController) activeController.abort();
    const controller = new AbortController();
    activeController = controller;
    const timeout = setTimeout(() => controller.abort(), 12000);
    const url = API + "?query=" + encodeURIComponent(query)
      + "&format=json&resultType=core&pageSize=" + PAGE_SIZE + "&cursorMark=" + encodeURIComponent(cursorMark)
      + "&synonym=true";
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("The literature service returned HTTP " + response.status + ".");
      return parseSearchResponse(await response.json());
    } finally {
      clearTimeout(timeout);
    }
  }

  function renderLoadMore() {
    const old = results.querySelector("#research-load-more");
    old?.remove();
    if (!hasMore || loadedCount >= totalHits || loadedCount === 0) return;
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
      const requestedCursor = nextCursorMark;
      const data = await fetchPage(activeQuery, requestedCursor);
      if (generation !== requestGeneration) return;
      if (data.papers.length) {
        results.insertBefore(
          h("div", { class: "research-paper-page" }, ...data.papers.map(paperCard)),
          button,
        );
      }
      loadedCount += data.papers.length;
      totalHits = data.hitCount;
      nextCursorMark = data.nextCursorMark;
      hasMore = Boolean(data.papers.length && nextCursorMark && nextCursorMark !== requestedCursor);
      status.textContent = data.papers.length
        ? "Showing " + loadedCount + " of " + totalHits
        : "No additional publication records were returned by Europe PMC.";
      if (data.papers.length) status.textContent = "Showing " + loadedCount + " of " + totalHits
        + " publication records returned by Europe PMC. Results are source-indexed, not clinical recommendations.";
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
    nextCursorMark = "*";
    loadedCount = 0;
    totalHits = 0;
    hasMore = false;
    status.textContent = "Searching Europe PMC for matching publication records…";
    results.replaceChildren();
    submitButton.disabled = true;
    submitButton.textContent = "Searching…";
    try {
      const data = await fetchPage(query, "*");
      if (generation !== requestGeneration) return;
      nextCursorMark = data.nextCursorMark;
      totalHits = data.hitCount;
      loadedCount = data.papers.length;
      hasMore = Boolean(data.papers.length && nextCursorMark && nextCursorMark !== "*");
      if (data.papers.length) {
        results.append(h("div", { class: "research-paper-page" }, ...data.papers.map(paperCard)));
        status.textContent = "Showing " + loadedCount + " of " + totalHits
          + " publication records returned by Europe PMC. Results are source-indexed, not clinical recommendations.";
      } else {
        status.textContent = "No publication records matched this search. Try broader terms or another department.";
      }
      renderLoadMore();
    } catch (error) {
      if (generation !== requestGeneration) return;
      status.textContent = error.name === "AbortError"
        ? "The literature search timed out. Please try again."
        : "The live literature service could not be reached. No sample or fabricated papers are shown. " + error.message;
    } finally {
      if (generation === requestGeneration) {
        submitButton.disabled = false;
        submitButton.textContent = "Search publications";
      }
    }
  }

  form.addEventListener("submit", search);
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
