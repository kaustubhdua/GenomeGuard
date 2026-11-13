import { h } from "../ui.js";

const API = "https://www.ebi.ac.uk/europepmc/webservices/rest/search";
const DEPARTMENTS = [
  ["Genetics & Genomics", "genetics"],
  ["Oncology", "oncology"],
  ["Neurology", "neurology"],
  ["Cardiology", "cardiology"],
  ["Immunology", "immunology"],
  ["Rare Diseases", "rare disease"],
  ["Bioinformatics", "bioinformatics"],
  ["Pharmacogenomics", "pharmacogenomics"],
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
  const journal = [article.journalTitle, article.firstPublicationDate?.slice(0, 4)]
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
  if (!department) return terms;
  return '"' + department.replaceAll('"', "") + '" AND (' + terms + ')';
}

export async function render() {
  const params = new URLSearchParams(location.hash.split("?")[1] || "");
  const initialDepartment = params.get("department") || "";
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
        h("p", { class: "muted" }, "Choose a field to open a focused literature search. You can refine the query below.")),
      h("div", { class: "grid g2 research-departments", "aria-label": "Research departments" },
        ...DEPARTMENTS.map(([label, term]) => h("a", {
          class: "research-department",
          href: "#/research?department=" + encodeURIComponent(term),
          "aria-current": initialDepartment === term ? "true" : "false",
        }, h("strong", {}, label), h("span", { class: "muted" }, "Explore publications →"))))),
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
          ...DEPARTMENTS.map(([label, term]) => h("option", { value: term }, label))),
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
  if (DEPARTMENTS.some(([, term]) => term === initialDepartment)) department.value = initialDepartment;

  async function search(event) {
    event?.preventDefault();
    const text = question.value.trim();
    if (text.length < 3) {
      status.textContent = "Enter at least 3 characters to search.";
      question.focus();
      return;
    }
    if (text.length > 500) {
      status.textContent = "Keep the search under 500 characters.";
      return;
    }
    const query = buildQuery(text, department.value);
    status.textContent = "Searching Europe PMC for matching publication records…";
    results.replaceChildren();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Searching…";
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
      const url = API + "?query=" + encodeURIComponent(query)
        + "&format=json&resultType=core&pageSize=20&sort_date:y";
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error("The literature service returned HTTP " + response.status + ".");
      const data = await response.json();
      const papers = Array.isArray(data.resultList?.result) ? data.resultList.result : [];
      status.textContent = papers.length
        ? papers.length + " publication records returned by Europe PMC. Results are source-indexed, not clinical recommendations."
        : "No publication records matched this search. Try broader terms or another department.";
      if (papers.length) results.replaceChildren(...papers.map(paperCard));
    } catch (error) {
      status.textContent = error.name === "AbortError"
        ? "The literature search timed out. Please try again."
        : "The live literature service could not be reached. No sample or fabricated papers are shown. " + error.message;
    } finally {
      clearTimeout(timeout);
      button.disabled = false;
      button.textContent = "Search publications";
    }
  }

  form.addEventListener("submit", search);
  if (initialDepartment) {
    question.value = "";
    status.textContent = "Department selected. Add a question or symptom description to search this field.";
  }
  return root;
}
