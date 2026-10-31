import { h, card, notice, sampleNotice } from "../ui.js";
import { sampleChromosomes } from "../sample-data.js";
import { loadPublicCatalogue } from "../catalogue-api.js";

const format = (value) => Number(value || 0).toLocaleString("en-US");
const KIND = { autosome: "Autosome", sex: "Sex chromosome", mitochondrial: "Mitochondrial" };

export async function render() {
  return renderAssembly("GRCh38");
}

async function renderAssembly(assembly, sample = false) {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" }, h("div", { class: "hero-copy" },
    h("h1", {}, "Chromosome explorer"),
    h("p", { class: "lede" }, `Browse the ${assembly} human reference chromosomes and see where verified variant records are actually available. Reference coordinates are not genotype data, and an empty chromosome is never treated as analysed.`))));

  const response = sample ? { ok: true, status: 200, data: sampleChromosomes(assembly) } : await loadPublicCatalogue("chromosomes", { assembly });
  const showSample = async () => root.replaceWith(await renderAssembly(assembly, true));
  if (!response.ok) {
    root.append(notice("warn",
      h("strong", {}, "Chromosome coverage service is not reachable from this deployment."),
      h("p", { class: "muted" }, "The live Supabase chromosome catalogue could not be loaded. Check the connection and try again; no placeholder counts are shown."),
      h("p", { class: "fine" }, "Technical status: HTTP " + (response.status || "network error")),
      h("button", { onclick: showSample }, "Preview with sample data")));
    root.append(card("What this page will show", "No simulated records",
      h("ul", {},
        h("li", {}, "Reference assembly and chromosome length from the Genome Reference Consortium."),
        h("li", {}, "Actual stored variant count and observed coordinate range from the local database."),
        h("li", {}, "A clear unavailable state until verified variant records and source provenance exist."))));
    return root;
  }

  const data = response.data || {};
  if (sample) root.append(sampleNotice("The lengths are the public GRCh38 reference lengths. The variant coverage is invented to show the layout.", async () => root.replaceWith(await renderAssembly(assembly))));
  const rows = Array.isArray(data.chromosomes) ? data.chromosomes : [];
  const loaded = rows.filter((r) => r.data_coverage?.variant_data_loaded === true).length;
  root.append(h("div", { class: "grid g3" },
    card("Reference assembly", data.reference_assembly || "Unknown", h("p", { class: "muted" }, "Reference metadata only")),
    card("Chromosomes catalogued", format(rows.length), h("p", { class: "muted" }, "Autosomes, sex chromosomes and mitochondrial reference")),
    card("With variant records", format(loaded), h("p", { class: "muted" }, "Only non-empty coverage counts as loaded"))));

  if (data.provenance_note && !sample) root.append(notice("info", data.provenance_note));
  const assemblySelect = h("select", { id: "assembly-filter", "aria-label": "Reference assembly" },
    h("option", { value: "GRCh38" }, "GRCh38"),
    h("option", { value: "GRCh37" }, "GRCh37"));
  assemblySelect.value = assembly;
  assemblySelect.addEventListener("change", async () => {
    const next = await renderAssembly(assemblySelect.value, sample);
    root.replaceWith(next);
  });
  const search = h("input", { type: "search", placeholder: "Filter chromosomes (e.g. 22, X, MT)", "aria-label": "Filter chromosomes" });
  const onlyLoaded = h("input", { type: "checkbox", id: "only-loaded" });
  const list = h("div", { class: "table-wrap" });
  const longest = Math.max(1, ...rows.map((r) => Number(r.length_bp) || 0));
  // Bar length is the chromosome length relative to the longest one; the dark span is where stored variants were observed.
  const coverageBar = (r, cov) => {
    const len = Number(r.length_bp) || 0;
    const outer = h("span", { class: "cov", style: `width:${Math.max(2, (len / longest) * 100).toFixed(1)}%`, role: "img",
      "aria-label": cov.first_position == null ? "No variants observed" : `Variants observed from ${format(cov.first_position)} to ${format(cov.last_position)} of ${format(len)} base pairs` });
    if (cov.first_position != null && len > 0) {
      const left = (cov.first_position / len) * 100;
      const width = Math.max(0.6, ((cov.last_position - cov.first_position) / len) * 100);
      outer.append(h("i", { style: `left:${left.toFixed(2)}%;width:${width.toFixed(2)}%` }));
    }
    return outer;
  };
  const paint = () => {
    const q = search.value.trim().toUpperCase().replace(/^CHR/, "");
    const filtered = rows.filter((r) => {
      const chrom = String(r.chromosome || "").toUpperCase().replace(/^CHR/, "");
      return (!q || chrom.includes(q)) && (!onlyLoaded.checked || r.data_coverage?.variant_data_loaded === true);
    });
    const table = h("table", {},
      h("thead", {}, h("tr", {},
        ...["Chromosome", "Type", "Reference length", "Variant records", "Where variants sit", "Status"].map((v) => h("th", {}, v)))),
      h("tbody", {}, filtered.map((r) => {
        const cov = r.data_coverage || {};
        const hasData = cov.variant_data_loaded === true;
                return h("tr", {},
          h("th", { scope: "row" }, String(r.chromosome)),
          h("td", {}, KIND[r.kind] || r.kind || "Unknown"),
          h("td", { class: "mono" }, format(r.length_bp) + " bp"),
          h("td", { class: "mono" }, format(cov.variant_count)),
          h("td", { class: "cov-cell" }, coverageBar(r, cov),
            cov.first_position == null ? null : h("span", { class: "fine mono" }, format(cov.first_position) + " to " + format(cov.last_position))),
          h("td", {}, h("span", { class: "tag" + (hasData ? " on" : "") }, hasData ? "Variants loaded" : "No variants loaded")));
      })));
    list.replaceChildren(table);
    if (!filtered.length) list.append(h("p", { class: "muted" }, "No chromosomes match this filter."));
  };
  search.addEventListener("input", paint);
  onlyLoaded.addEventListener("change", paint);
  root.append(card("Chromosome coverage", sample ? "Sample values, not read from a database" : "Live database counts, not inferred from the reference catalogue",
    h("div", { class: "explorer-bar" },
      h("label", { for: "assembly-filter" }, "Reference assembly", assemblySelect),
      search,
      h("label", { for: "only-loaded" }, onlyLoaded, "Only chromosomes with variants")),
    list));
  paint();
  return root;
}
