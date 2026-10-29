import { api } from "../api.js";
import { h, card, notice } from "../ui.js";

const fmt = (value) => Number(value || 0).toLocaleString("en-US");
const shortHash = (value) => typeof value === "string" && /^[a-f0-9]{64}$/.test(value)
  ? value.slice(0, 12) + "…" + value.slice(-8) : "Unavailable";

export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" },
    h("p", { class: "eyebrow" }, "DATA PROVENANCE"),
    h("h1", {}, "Dataset catalogue"),
    h("p", { class: "lede" }, "Datasets appear here only after source review, checksum validation, genotype import, and count reconciliation. Reference metadata is not evidence that genotype data has been loaded.")));

  const response = await api("/datasets");
  if (!response.ok) {
    root.append(notice("warn",
      h("strong", {}, "Verified dataset catalogue is not reachable from this deployment."),
      h("p", { class: "muted" }, "No placeholder datasets are shown. The Supabase API route must be connected and reachable before this catalogue can display live manifest entries."),
      h("p", { class: "fine" }, "Technical status: HTTP " + (response.status || "network error"))));
    root.append(card("What qualifies for this catalogue", "Verified import only",
      h("ul", {},
        h("li", {}, "Reviewed public-research data-use status and source citation."),
        h("li", {}, "Exact source release, reference assembly and SHA-256 checksum."),
        h("li", {}, "Measured sample, normalized variant and called genotype counts."),
        h("li", {}, "Import status marked loaded only after database reconciliation."))));
    return root;
  }

  const data = response.data || {};
  const datasets = Array.isArray(data.datasets) ? data.datasets : [];
  root.append(h("div", { class: "grid g3" },
    card("Verified datasets", fmt(datasets.length), h("p", { class: "muted" }, "Eligible for public-research catalogue display")),
    card("Imported samples", fmt(datasets.reduce((sum, d) => sum + Number(d.sample_count || 0), 0)),
      h("p", { class: "muted" }, "Measured source samples across listed datasets")),
    card("Normalized variants", fmt(datasets.reduce((sum, d) => sum + Number(d.variant_count || 0), 0)),
      h("p", { class: "muted" }, "Split alternate-allele records; not clinical interpretation"))));

  root.append(notice("info", data.provenance_note ||
    "Dataset-level public-research approval is not participant-specific consent or clinical authorization."));
  if (!datasets.length) {
    root.append(card("No verified datasets available", "No data has passed the import gate",
      h("p", { class: "muted" }, "This is an honest empty state. The chromosome reference catalogue can exist while the genotype dataset catalogue remains empty."),
      h("a", { class: "btn ghost", href: "#/chromosomes" }, "View chromosome reference metadata")));
    return root;
  }

  const table = h("table", {},
    h("thead", {}, h("tr", {}, ...[
      "Dataset", "Source release", "Assembly", "SHA-256", "Samples", "Variants", "Genotype calls", "Imported"
    ].map((label) => h("th", {}, label)))),
    h("tbody", {}, datasets.map((d) => h("tr", {},
      h("th", { scope: "row" }, d.source_name || d.dataset_key || "Unnamed dataset"),
      h("td", {}, d.source_release || "Unknown"),
      h("td", {}, d.reference_assembly || "Unknown"),
      h("td", { class: "mono", title: d.file_sha256 || "" }, shortHash(d.file_sha256)),
      h("td", { class: "mono" }, fmt(d.sample_count)),
      h("td", { class: "mono" }, fmt(d.variant_count)),
      h("td", { class: "mono" }, fmt(d.genotype_call_count)),
      h("td", {}, d.imported_at ? new Date(d.imported_at).toLocaleString() : "Unknown")
    ))));
  root.append(card("Verified public-research datasets", "Source provenance and measured counts", table));
  return root;
}
