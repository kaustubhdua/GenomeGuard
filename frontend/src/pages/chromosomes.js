import { api } from "../api.js";
import { h, card, notice } from "../ui.js";

const format = (value) => Number(value || 0).toLocaleString("en-US");
const KIND = { autosome: "Autosome", sex: "Sex chromosome", mitochondrial: "Mitochondrial" };

export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" },
    h("p", { class: "eyebrow" }, "REFERENCE & DATA COVERAGE"),
    h("h1", {}, "Chromosome explorer"),
    h("p", { class: "lede" }, "Browse the GRCh38 human reference chromosomes and see where verified variant records are actually available. Reference coordinates are not genotype data, and an empty chromosome is never treated as analysed.")));

  const response = await api("/chromosomes");
  if (!response.ok) {
    root.append(notice("warn",
      h("strong", {}, "Chromosome coverage service is not reachable from this deployment."),
      h("p", { class: "muted" }, "The Supabase catalogue API must be routed to this page before live coverage can be displayed. No placeholder counts are shown."),
      h("p", { class: "fine" }, "Technical status: HTTP " + (response.status || "network error"))));
    root.append(card("What this page will show", "No simulated records",
      h("ul", {},
        h("li", {}, "Reference assembly and chromosome length from the Genome Reference Consortium."),
        h("li", {}, "Actual stored variant count and observed coordinate range from Supabase."),
        h("li", {}, "A clear unavailable state until verified variant records and source provenance exist."))));
    return root;
  }

  const data = response.data || {};
  const rows = Array.isArray(data.chromosomes) ? data.chromosomes : [];
  const loaded = rows.filter((r) => r.data_coverage?.variant_data_loaded === true).length;
  root.append(h("div", { class: "grid g3" },
    card("Reference assembly", data.reference_assembly || "Unknown", h("p", { class: "muted" }, "Reference metadata only")),
    card("Chromosomes catalogued", format(rows.length), h("p", { class: "muted" }, "Autosomes, sex chromosomes and mitochondrial reference")),
    card("With variant records", format(loaded), h("p", { class: "muted" }, "Only non-empty coverage counts as loaded"))));

  if (data.provenance_note) root.append(notice("info", data.provenance_note));
  const search = h("input", { type: "search", placeholder: "Filter chromosomes (e.g. 22, X, MT)", "aria-label": "Filter chromosomes" });
  const onlyLoaded = h("input", { type: "checkbox", id: "only-loaded" });
  const list = h("div", { class: "table-wrap" });
  const paint = () => {
    const q = search.value.trim().toUpperCase().replace(/^CHR/, "");
    const filtered = rows.filter((r) => {
      const chrom = String(r.chromosome || "").toUpperCase().replace(/^CHR/, "");
      return (!q || chrom.includes(q)) && (!onlyLoaded.checked || r.data_coverage?.variant_data_loaded === true);
    });
    const table = h("table", {},
      h("thead", {}, h("tr", {},
        ...["Chromosome", "Type", "Reference length", "Variant records", "Observed position range", "Status"].map((v) => h("th", {}, v)))),
      h("tbody", {}, filtered.map((r) => {
        const cov = r.data_coverage || {};
        const hasData = cov.variant_data_loaded === true;
        const range = cov.first_position == null ? "—" : format(cov.first_position) + "–" + format(cov.last_position);
        return h("tr", {},
          h("th", { scope: "row" }, String(r.chromosome)),
          h("td", {}, KIND[r.kind] || r.kind || "Unknown"),
          h("td", { class: "mono" }, format(r.length_bp) + " bp"),
          h("td", { class: "mono" }, format(cov.variant_count)),
          h("td", { class: "mono" }, range),
          h("td", {}, h("span", { class: "tag" }, hasData ? "Variants loaded" : "No variants loaded")));
      })));
    list.replaceChildren(table);
    if (!filtered.length) list.append(h("p", { class: "muted" }, "No chromosomes match this filter."));
  };
  search.addEventListener("input", paint);
  onlyLoaded.addEventListener("change", paint);
  root.append(card("Chromosome coverage", "Live database counts — not inferred from the reference catalogue",
    h("div", { class: "form-row", style: "display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px" },
      search,
      h("label", { for: "only-loaded", style: "display:flex;align-items:center;gap:8px" }, onlyLoaded, "Only chromosomes with variants")),
    list));
  paint();
  return root;
}
