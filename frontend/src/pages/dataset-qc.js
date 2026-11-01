import { api, isSteward, state } from "../api.js";
import { h, card, notice, errorText } from "../ui.js";

const fmt = (v) => v == null ? "Not recorded" : Number(v).toLocaleString("en-US");
export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" }, h("h1", {}, "Dataset QC & import review"),
    h("p", { class: "lede" }, "Steward-only inspection of the active in-memory cohort, its provenance and measurable quality indicators. This is an inspection report, not a dataset approval or production-readiness certificate.")));
  if (!isSteward() && !state.adminKey) {
    root.append(notice("warn", "This page is restricted to an authenticated data steward."));
    return root;
  }
  const result = await api("/admin/dataset-qc");
  if (!result.ok) { root.append(notice("err", errorText(result))); return root; }
  const d = result.data || {}, maf = d.maf || {};
  root.append(h("div", { class: "grid g3" },
    card("Samples", fmt(d.sample_count), "Measured rows in active cohort"),
    card("Variants", fmt(d.variant_count), "Normalized variant columns"),
    card("Genotype calls", fmt(d.genotype_call_count), "Sample × variant matrix size")));
  root.append(card("Source & provenance", d.dataset_id || "Unknown dataset",
    h("dl", { class: "facts" },
      h("dt", {}, "Source"), h("dd", {}, d.source || "Unknown"),
      h("dt", {}, "Source SHA-256"), h("dd", { class: "mono" }, d.source_sha256 || "Unavailable"),
      h("dt", {}, "Reference assembly"), h("dd", {}, d.reference_assembly || "Not recorded"),
      h("dt", {}, "Consent basis"), h("dd", {}, d.consent_basis || "Unknown"),
      h("dt", {}, "Review status"), h("dd", {}, d.review_status))));
  root.append(card("Variant quality summary", "Observed minor-allele frequency",
    h("dl", { class: "facts" },
      h("dt", {}, "Minimum MAF"), h("dd", {}, fmt(maf.minimum)),
      h("dt", {}, "Median MAF"), h("dd", {}, fmt(maf.median)),
      h("dt", {}, "Maximum MAF"), h("dd", {}, fmt(maf.maximum)),
      h("dt", {}, "Below 1% MAF"), h("dd", {}, fmt(maf.below_1_percent)),
      h("dt", {}, "Monomorphic"), h("dd", {}, fmt(maf.monomorphic)))));
  root.append(card("Chromosome coverage", "Variant records in active cohort",
    h("div", { class: "tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Chromosome"), h("th", {}, "Variants"))),
      h("tbody", {}, Object.entries(d.chromosome_variant_counts || {}).sort((a,b) => a[0].localeCompare(b[0], undefined, {numeric:true})).map(([chrom,count]) =>
        h("tr", {}, h("th", {}, chrom), h("td", {}, fmt(count))))))));
  root.append(notice("info", d.missingness_note || "Missingness provenance unavailable."),
    h("p", { class: "fine" }, "Source-file missingness, source citation/reuse terms, file size, import timestamp and independent checksum verification are not exposed by the active service. Do not infer that unavailable checks passed."));
  return root;
}
