import { h, card, notice } from "../ui.js";
import { loadPublicCatalogue } from "../catalogue-api.js";

const fmt = (value) => Number(value || 0).toLocaleString("en-US");
const shortHash = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)
  ? value.slice(0, 12) + "…" + value.slice(-8) : "Unavailable";
const date = (value) => {
  if (!value) return "Not recorded";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? "Invalid timestamp" : new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium", timeStyle: "short",
  }).format(parsed);
};

function sourceLink(url) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return h("span", { class: "muted" }, "Source link unavailable");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "dataset-source-link" }, "Open source", h("span", { "aria-hidden": "true" }, " ↗"));
  } catch {
    return h("span", { class: "muted" }, "Source link unavailable");
  }
}

function provenanceChecklist() {
  return h("div", { class: "dataset-checklist" },
    ...[
      ["01", "Source reviewed", "The exact collection and its reuse terms must be reviewed."],
      ["02", "File verified", "The imported artifact is tied to a SHA-256 checksum."],
      ["03", "Assembly checked", "Reference assembly and genomic coordinates must agree."],
      ["04", "Counts reconciled", "Measured samples, variants and genotype calls must reconcile."],
    ].map(([n, title, detail]) => h("article", { class: "dataset-check" },
      h("span", { class: "dataset-check-number", "aria-hidden": "true" }, n),
      h("div", {}, h("h3", {}, title), h("p", {}, detail)))));
}

export async function render() {
  const root = h("div", { class: "stack dataset-page" });
  root.append(h("section", { class: "card hero dataset-hero" },
    h("div", { class: "dataset-hero-mark", "aria-hidden": "true" }, "⌘"),
    h("div", {},
      h("p", { class: "eyebrow" }, "RESEARCH DATA · PROVENANCE"),
      h("h1", {}, "Dataset catalogue"),
      h("p", { class: "lede" }, "A source-of-truth view of research datasets that have passed the import gate. Counts come from persisted records—not demo fixtures or reference metadata."),
      h("div", { class: "dataset-hero-meta" },
        h("span", { class: "status-dot" }, "Verified records only"),
        h("span", { class: "muted" }, "Public research · Not clinical use")))));

  const response = await loadPublicCatalogue("datasets");
  if (!response.ok) {
    const retry = h("button", { class: "btn", onclick: async () => {
      retry.disabled = true;
      retry.textContent = "Checking…";
      const next = await render();
      root.replaceWith(next);
    } }, "Retry connection");
    root.append(notice("warn",
      h("strong", {}, "The catalogue could not be reached."),
      h("p", { class: "muted" }, "No placeholder data is shown. Check the connection and try again; the rest of the workspace remains available."),
      h("p", { class: "fine" }, "Connection status: " + (response.status || "network unavailable")),
      retry));
    root.append(card("What qualifies for this catalogue", "Four checks before a dataset appears", provenanceChecklist()));
    return root;
  }

  const data = response.data || {};
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];
  const totals = datasets.reduce((acc, d) => ({
    samples: acc.samples + Number(d.sample_count || 0),
    variants: acc.variants + Number(d.variant_count || 0),
    calls: acc.calls + Number(d.genotype_call_count || 0),
  }), { samples: 0, variants: 0, calls: 0 });

  root.append(h("section", { class: "grid g3 dataset-metrics", "aria-label": "Verified catalogue totals" },
    card("Verified datasets", fmt(datasets.length), h("p", { class: "muted" }, "Eligible catalogue entries")),
    card("Imported samples", fmt(totals.samples), h("p", { class: "muted" }, "Measured source samples")),
    card("Normalized variants", fmt(totals.variants), h("p", { class: "muted" }, "Split alternate-allele records"))));

  root.append(notice("info", data.provenance_note ||
    "Dataset-level public-research approval is not participant-specific consent or clinical authorization."));

  if (!datasets.length) {
    root.append(h("section", { class: "card dataset-empty" },
      h("div", { class: "dataset-empty-symbol", "aria-hidden": "true" }, "∅"),
      h("p", { class: "eyebrow" }, "NO VERIFIED IMPORTS"),
      h("h2", {}, "The catalogue is empty—for now."),
      h("p", { class: "muted" }, "No dataset has completed the source-review, checksum, assembly, import and count-reconciliation process. That is different from having no chromosome reference metadata."),
      h("a", { class: "btn", href: "#/chromosomes" }, "Explore chromosome reference metadata", h("span", { "aria-hidden": "true" }, " →"))));
    root.append(card("How a dataset becomes available", "A transparent, reproducible import gate", provenanceChecklist()));
    root.append(h("p", { class: "fine dataset-footnote" }, "Nothing here is synthetic. A dataset will appear only after a real import has been verified."));
    return root;
  }

  const search = h("input", {
    class: "dataset-search", type: "search", placeholder: "Search name, release or assembly…",
    "aria-label": "Search verified datasets",
  });
  const count = h("span", { class: "dataset-result-count", "aria-live": "polite" }, datasets.length + " datasets");
  const body = h("tbody", {});
  const table = h("table", { class: "dataset-table" },
    h("thead", {}, h("tr", {}, ...[
      "Dataset", "Source release", "Assembly", "SHA-256", "Samples", "Variants", "Genotype calls", "Imported",
    ].map((label) => h("th", { scope: "col" }, label)))),
    body);

  function paintRows() {
    const q = search.value.trim().toLowerCase();
    const filtered = datasets.filter((d) =>
      [d.source_name, d.dataset_key, d.source_release, d.reference_assembly]
        .some((v) => String(v || "").toLowerCase().includes(q)));
    count.textContent = filtered.length + " of " + datasets.length + " datasets";
    body.replaceChildren(...filtered.map((d) => h("tr", {},
      h("th", { scope: "row" },
        h("span", { class: "dataset-name" }, d.source_name || d.dataset_key || "Unnamed dataset"),
        h("div", { class: "fine" }, d.dataset_key || "No dataset key"),
        sourceLink(d.source_url)),
      h("td", {}, d.source_release || "Unknown"),
      h("td", {}, h("span", { class: "dataset-assembly" }, d.reference_assembly || "Unknown")),
      h("td", {}, h("button", {
        class: "dataset-hash", title: d.file_sha256 || "Checksum unavailable",
        onclick: async (event) => {
          if (!d.file_sha256 || !navigator.clipboard?.writeText) return;
          const button = event.currentTarget;
          try { await navigator.clipboard.writeText(d.file_sha256); button.textContent = "Copied"; }
          catch { button.textContent = "Copy unavailable"; }
        },
      }, shortHash(d.file_sha256))),
      h("td", { class: "mono" }, fmt(d.sample_count)),
      h("td", { class: "mono" }, fmt(d.variant_count)),
      h("td", { class: "mono" }, fmt(d.genotype_call_count)),
      h("td", {}, date(d.imported_at)))));
    if (!filtered.length) body.append(h("tr", {}, h("td", { colSpan: "8", class: "dataset-no-results" }, "No datasets match this search.")));
  }
  search.addEventListener("input", paintRows);
  paintRows();

  root.append(card("Verified public-research datasets", "Provenance and measured counts",
    h("div", { class: "dataset-toolbar" }, search, count),
    h("div", { class: "tablewrap" }, table)));
  root.append(h("p", { class: "fine dataset-footnote" }, "Counts are measured at import time. Genotype calls are not clinical interpretations, and catalogue inclusion does not authorize participant-specific release."));
  return root;
}
