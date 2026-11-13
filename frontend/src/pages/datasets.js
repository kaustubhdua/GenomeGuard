import { h, card, notice, bands, sampleNotice } from "../ui.js";
import { sampleDatasets } from "../sample-data.js";
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

function sourceLink(url, label = "Open source (new tab)") {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return h("span", { class: "muted" }, "Source link unavailable");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "dataset-source-link" }, label);
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
      ["04", "Counts reconciled", "Measured individuals, variants and genotype calls must reconcile."],
    ].map(([n, title, detail]) => h("article", { class: "dataset-check" },
      h("span", { class: "dataset-check-number", "aria-hidden": "true" }, n),
      h("div", {}, h("h3", {}, title), h("p", {}, detail)))));
}

export async function render() {
  return renderCatalogue(false);
}

// The router passes its own argument to render(), so the sample switch lives on a separate function.
async function renderCatalogue(sample, force = false) {
  const root = h("div", { class: "stack dataset-page" });
  root.append(h("section", { class: "card hero dataset-hero" }, h("div", { class: "hero-copy" },
    h("h1", {}, "Dataset catalogue"),
    h("p", { class: "lede" }, "The research datasets that have passed the import gate, with counts read from stored records. Nothing here comes from demo fixtures or reference metadata."),
    h("div", { class: "dataset-hero-meta" },
      h("span", { class: "status-dot" }, "Verified records only"),
      h("span", { class: "muted" }, "Public research data. Not for clinical use.")))));

  const response = sample ? { ok: true, status: 200, data: sampleDatasets() } : await loadPublicCatalogue("datasets", { force });
  const showSample = async () => root.replaceWith(await renderCatalogue(true));
  if (!response.ok) {
    const retry = h("button", { class: "btn", onclick: async () => {
      retry.disabled = true;
      retry.textContent = "Checking…";
      const next = await renderCatalogue(false, true);
      root.replaceWith(next);
    } }, "Retry connection");
    root.append(notice("warn",
      h("strong", {}, "The catalogue could not be reached."),
      h("p", { class: "muted" }, "No placeholder data is shown. Check the connection and try again; the rest of the workspace remains available."),
      h("p", { class: "fine" }, "Connection status: " + (response.status || "network unavailable")),
      h("div", { class: "hero-actions" }, retry, h("button", { class: "ghost", onclick: showSample }, "View illustrative preview"))));
    root.append(card("What qualifies for this catalogue", "Four checks before a dataset appears", provenanceChecklist()));
    return root;
  }

  const data = response.data || {};
  if (sample) root.append(sampleNotice("These records are invented to show the layout. They are not imports and carry no consent or authorization.", async () => root.replaceWith(await renderCatalogue(false))));
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];
  const totals = datasets.reduce((acc, d) => ({
    samples: acc.samples + Number(d.sample_count || 0),
    variants: acc.variants + Number(d.variant_count || 0),
    calls: acc.calls + Number(d.genotype_call_count || 0),
  }), { samples: 0, variants: 0, calls: 0 });

  root.append(h("section", { class: "grid g3 dataset-metrics", "aria-label": "Verified catalogue totals" },
    card("Verified datasets", fmt(datasets.length), h("p", { class: "muted" }, "Eligible catalogue entries")),
    card("Individuals imported", fmt(totals.samples), h("p", { class: "muted" }, "Measured individuals in source")),
    card("Normalized variants", fmt(totals.variants), h("p", { class: "muted" }, "Split alternate-allele records"))));

  root.append(sample ? "" : notice("info", data.provenance_note ||
    "Dataset-level public-research approval is not participant-specific consent or clinical authorization."));

  if (!datasets.length) {
    root.append(h("section", { class: "card dataset-empty" },
      h("h2", {}, "No dataset has been verified yet."),
      h("p", { class: "muted" }, "No dataset has completed the source-review, checksum, assembly, import and count-reconciliation process. That is different from having no chromosome reference metadata."),
      h("div", { class: "hero-actions" },
        h("a", { class: "btn", href: "#/chromosomes" }, "Explore chromosome reference metadata"),
        h("button", { class: "ghost", onclick: showSample }, "View illustrative preview"))));
    root.append(card("How a dataset becomes available", "A transparent, reproducible import gate", provenanceChecklist()));
    root.append(h("p", { class: "fine dataset-footnote" }, "A dataset appears only after its source, checksum, assembly and imported counts have been verified."));
    return root;
  }

  const search = h("input", {
    class: "dataset-search", type: "search", placeholder: "Search name, release, citation or assembly…",
    "aria-label": "Search verified datasets",
  });
  const sourceValues = [...new Set(datasets.map((d) => String(d.source_name || "").trim()).filter(Boolean))].sort();
  const assemblyValues = [...new Set(datasets.map((d) => String(d.reference_assembly || "").trim()).filter(Boolean))].sort();
  const sourceFilter = h("select", { class: "dataset-filter", "aria-label": "Filter by source" },
    h("option", { value: "" }, "All sources"),
    ...sourceValues.map((value) => h("option", { value }, value)));
  const assemblyFilter = h("select", { class: "dataset-filter", "aria-label": "Filter by reference assembly" },
    h("option", { value: "" }, "All assemblies"),
    ...assemblyValues.map((value) => h("option", { value }, value)));
  const sortBy = h("select", { class: "dataset-filter", "aria-label": "Sort datasets" },
    h("option", { value: "newest" }, "Newest imports"),
    h("option", { value: "oldest" }, "Oldest imports"),
    h("option", { value: "samples" }, "Most individuals"),
    h("option", { value: "variants" }, "Most variants"));
  const count = h("span", { class: "dataset-result-count", "aria-live": "polite" }, datasets.length + " datasets");
  const exportStatus = h("span", { class: "fine muted", role: "status", "aria-live": "polite" });
  const exportButton = h("button", { class: "btn secondary", type: "button" }, "Export filtered CSV");
  const body = h("tbody", {});
  const table = h("table", { class: "dataset-table" },
    h("thead", {}, h("tr", {}, ...[
      "Dataset", "Source release", "Assembly", "SHA-256", "Individuals", "Variants", "Genotype calls", "Imported",
    ].map((label) => h("th", { scope: "col" }, label)))),
    body);

  function filteredDatasets() {
    const q = search.value.trim().toLowerCase();
    const filtered = datasets.filter((d) => {
      const matchesText = [
        d.source_name, d.dataset_key, d.source_release, d.reference_assembly,
        d.citation, d.policy_description,
      ].some((v) => String(v || "").toLowerCase().includes(q));
      return matchesText
        && (!sourceFilter.value || String(d.source_name || "") === sourceFilter.value)
        && (!assemblyFilter.value || String(d.reference_assembly || "") === assemblyFilter.value);
    });
    const timestamp = (value) => {
      const parsed = Date.parse(value || "");
      return Number.isFinite(parsed) ? parsed : 0;
    };
    return filtered.sort((a, b) => {
      if (sortBy.value === "samples") return Number(b.sample_count || 0) - Number(a.sample_count || 0);
      if (sortBy.value === "variants") return Number(b.variant_count || 0) - Number(a.variant_count || 0);
      return sortBy.value === "oldest"
        ? timestamp(a.imported_at) - timestamp(b.imported_at)
        : timestamp(b.imported_at) - timestamp(a.imported_at);
    });
  }

  function csvCell(value) {
    let text = value == null ? "" : String(value);
    // Prevent spreadsheet formula execution when source-controlled text is opened in Excel/Sheets.
    if (/^[\\s]*[=+@-]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function exportCsv() {
    const rows = filteredDatasets();
    if (!rows.length) {
      exportStatus.textContent = "There are no matching datasets to export.";
      return;
    }
    const columns = [
      ["dataset_key", "Dataset key"], ["source_name", "Source name"],
      ["source_release", "Source release"], ["reference_assembly", "Reference assembly"],
      ["file_sha256", "SHA-256"], ["sample_count", "Individuals"],
      ["variant_count", "Variants"], ["genotype_call_count", "Genotype calls"],
      ["imported_at", "Imported at"], ["source_url", "Source URL"],
      ["reuse_statement_url", "Reuse terms URL"], ["citation", "Citation"],
      ["policy_description", "Policy description"],
    ];
    const csv = [columns.map(([, label]) => csvCell(label)).join(","),
      ...rows.map((dataset) => columns.map(([key]) => csvCell(dataset[key])).join(","))].join("\r\n");
    const blob = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = h("a", { href: url, download: "genomeguard-dataset-catalogue.csv" });
    document.body.append(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    exportStatus.textContent = "Exported " + rows.length + " filtered dataset records.";
  }

  function paintRows() {
    const filtered = filteredDatasets();
    count.textContent = filtered.length + " of " + datasets.length + " datasets";
    body.replaceChildren(...filtered.map((d) => h("tr", {},
      h("th", { scope: "row" },
        h("span", { class: "dataset-name" }, d.source_name || d.dataset_key || "Unnamed dataset"),
        h("div", { class: "fine" }, d.dataset_key || "No dataset key"),
        sourceLink(d.source_url),
        sourceLink(d.reuse_statement_url, "Read reuse terms"),
        h("div", { class: "fine" }, d.policy_description || "Dataset-level policy; no participant consent records are implied."),
        d.citation ? h("div", { class: "fine", title: d.citation }, d.citation) : null),
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
      }, shortHash(d.file_sha256), bands(d.file_sha256, { width: 128, height: 10, label: "Banded fingerprint of the file checksum" }))),
      h("td", { class: "mono" }, fmt(d.sample_count)),
      h("td", { class: "mono" }, fmt(d.variant_count)),
      h("td", { class: "mono" }, fmt(d.genotype_call_count)),
      h("td", {}, date(d.imported_at)))));
    if (!filtered.length) body.append(h("tr", {}, h("td", { colSpan: "8", class: "dataset-no-results" }, "No datasets match this search.")));
  }
  for (const control of [search, sourceFilter, assemblyFilter, sortBy]) {
    control.addEventListener(control === search ? "input" : "change", paintRows);
  }
  exportButton.addEventListener("click", exportCsv);
  paintRows();

  root.append(card("Verified public-research datasets", "Filter, compare and export source-backed records",
    h("div", { class: "dataset-toolbar dataset-toolbar-expanded" },
      h("div", { class: "dataset-filter-row" }, search, sourceFilter, assemblyFilter, sortBy),
      h("div", { class: "dataset-toolbar-actions" }, count, exportButton)),
    exportStatus,
    h("div", { class: "tablewrap" }, table)));
  root.append(h("p", { class: "fine dataset-footnote" }, "Counts are measured at import time. Genotype calls are not clinical interpretations, and catalogue inclusion does not authorize participant-specific release."));
  return root;
}
