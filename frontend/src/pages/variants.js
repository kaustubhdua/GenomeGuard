import { api, isSteward } from "../api.js";
import { h, card, notice, errorText } from "../ui.js";

const fmt = (v) => v == null ? "Not recorded" : Number(v).toLocaleString("en-US");
const fmtAf = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n.toPrecision(4) + " (" + (n * 100).toPrecision(4) + "%)" : "Not recorded";
};
const variantKey = (v) => [v.chromosome, v.position, v.reference_allele, v.alternate_allele].join(":");
const recognizedAssembly = (value) => ["GRCh37", "GRCh38"].includes(value);
const isSubstitution = (v) => String(v.reference_allele).length === String(v.alternate_allele).length;
const shortList = (values, limit = 6) => {
  const items = Array.isArray(values) ? values : [];
  const visible = items.slice(0, limit).join(", ");
  return items.length > limit ? visible + " +" + (items.length - limit) + " more" : (visible || "Not recorded");
};

export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" }, h("h1", {}, "Locus & variant inspector"),
    h("p", { class: "lede" }, "Inspect a cohort locus, compare it with a provenance-linked public population reference, and review aggregate ClinVar assertions. These evidence sources stay separate from participant data and governed cohort releases.")));
  const initialQuery = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
  const query = h("input", { type: "search", value: initialQuery, placeholder: "e.g. 22:105123:A:G or v42", "aria-label": "Variant coordinate or ID" });
  const assembly = h("select", { "aria-label": "Reference assembly" },
    h("option", { value: "" }, "Choose assembly"),
    h("option", { value: "GRCh38" }, "GRCh38"),
    h("option", { value: "GRCh37" }, "GRCh37"));
  const output = h("div", { "aria-live": "polite" });
  const button = h("button", { onclick: search }, "Search variant");
  let activeMatches = [];
  let frequencyResults = new Map();
  let clinicalResults = new Map();

  function frequencyPanel(v) {
    const result = frequencyResults.get(variantKey(v));
    if (!result) return null;
    if (result.status === "loading") return notice("info", "Looking up this exact locus in approved aggregate references…");
    if (result.status === "error") return notice("warn", result.message);
    if (result.status === "unavailable") {
      return notice("warn", result.message || "Approved aggregate population references are unavailable in this deployment.");
    }
    if (result.status === "empty") {
      return notice("info", "No approved, loaded population reference has a row for this exact variant and assembly.");
    }
    if (result.status !== "available" || !result.matches?.length) {
      return notice("info", "No approved population-frequency rows are available for this lookup.");
    }
    const table = h("div", { class: "table-wrap population-frequency-table" },
      h("table", {},
        h("thead", {}, h("tr", {},
          h("th", {}, "Reference source"), h("th", {}, "Population"),
          h("th", { class: "num" }, "AC"), h("th", { class: "num" }, "AN"),
          h("th", { class: "num" }, "AF"), h("th", { class: "num" }, "Homozygotes"))),
        h("tbody", {}, result.matches.map((m) => h("tr", {},
          h("td", {},
            h("a", { href: m.source_url, target: "_blank", rel: "noopener noreferrer" }, m.source_name),
            h("p", { class: "fine" }, m.source_release + " · " + m.reference_assembly),
            h("code", { class: "popfreq-checksum" }, "SHA256 " + (m.file_sha256 || "Not recorded"))),
          h("td", {}, m.population), h("td", { class: "num" }, fmt(m.allele_count)),
          h("td", { class: "num" }, fmt(m.allele_number)), h("td", { class: "num" }, fmtAf(m.allele_frequency)),
          h("td", { class: "num" }, fmt(m.homozygote_count))))));
    return h("div", { class: "population-frequency-results" },
      result.truncated ? notice("warn", "Showing the first 1,000 rows. Review the source manifest for additional loaded references.") : null,
      notice("info", "Aggregate reference evidence only. These frequencies are not GenomeGuard participant calls, cohort frequencies, or a governance release."),
      table);
  }

  function clinicalPanel(v) {
    const result = clinicalResults.get(variantKey(v));
    if (!result) return null;
    if (result.status === "loading") return notice("info", "Searching the approved ClinVar snapshot for this exact substitution…");
    if (result.status === "error") return notice("warn", result.message);
    if (result.status === "unavailable") {
      return notice("warn", result.message || "Approved ClinVar evidence is unavailable in this deployment.");
    }
    if (result.status === "empty") {
      return notice("info", "No approved, loaded ClinVar snapshot has an exact allele match for this assembly.");
    }
    if (result.status !== "available" || !result.matches?.length) {
      return notice("info", "No ClinVar assertions are available for this lookup.");
    }
    const records = result.matches.map((m) => {
      const classification = m.clinical_significance || "Not reported";
      const signals = (classification + " " + (m.review_status || "")).toLowerCase();
      const conflict = signals.includes("conflict");
      const uncertain = signals.includes("uncertain");
      const state = conflict ? "conflict" : uncertain ? "uncertain" : "reported";
      return h("article", { class: "clinvar-record" },
        h("div", { class: "clinvar-record-head" },
          h("a", { href: m.clinvar_record_url, target: "_blank", rel: "noopener noreferrer" },
            "ClinVar variation " + m.variation_id),
          h("span", { class: "clinvar-classification " + state }, classification)),
        conflict ? notice("warn", "ClinVar reports conflicting evidence. This record is not a single consensus verdict.")
          : uncertain ? notice("warn", "ClinVar reports uncertain significance; this is not a pathogenicity conclusion.")
            : notice("info", "ClinVar aggregate variant-level assertion; not a diagnosis or GenomeGuard prediction."),
        h("dl", { class: "clinvar-facts" },
          h("dt", {}, "Review status"), h("dd", {}, m.review_status || "Not recorded"),
          h("dt", {}, "Last evaluated"), h("dd", {}, m.last_evaluated || "Not recorded"),
          h("dt", {}, "Submitters"), h("dd", {}, fmt(m.submitter_count)),
          h("dt", {}, "Gene symbols"), h("dd", {}, shortList(m.gene_symbols))),
        h("p", { class: "fine" }, h("b", {}, "Associated conditions: "), shortList(m.conditions)),
        h("p", { class: "fine" }, "Conditions are associated metadata from the variant summary; this classification is not attributed separately to each listed condition."),
        h("p", { class: "fine" },
          "Snapshot: " + m.source_release + " · " + m.reference_assembly + " · SHA256 ",
          h("code", { class: "clinvar-checksum" }, m.file_sha256 || "Not recorded")));
    });
    return h("div", { class: "clinvar-results" },
      result.truncated ? notice("warn", "Showing the first 100 ClinVar records for this exact allele.") : null,
      records);
  }

  function renderMatches(assemblyChanged = false) {
    output.replaceChildren();
    if (assemblyChanged) output.append(notice("warn", "Reference assembly changed. Run the lookups again to replace the previous results."));
    output.append(...activeMatches.map((v) => {
      const current = frequencyResults.get(variantKey(v));
      const lookupButton = h("button", {
        class: "ghost", type: "button", disabled: !assembly.value || current?.status === "loading",
        onclick: () => lookupFrequencies(v),
      }, current?.status === "loading" ? "Looking up…" : "Find approved population frequencies");
      const clinicalCurrent = clinicalResults.get(variantKey(v));
      const clinvarButton = h("button", {
        class: "ghost", type: "button",
        disabled: !assembly.value || !isSubstitution(v) || clinicalCurrent?.status === "loading",
        title: !isSubstitution(v) ? "Indel normalization is not yet supported." : "",
        onclick: () => lookupClinVar(v),
      }, clinicalCurrent?.status === "loading" ? "Searching ClinVar…" : "Find ClinVar evidence");
      return card("Variant v" + v.variant_id,
        v.chromosome + ":" + fmt(v.position) + " " + v.reference_allele + ">" + v.alternate_allele,
        h("dl", { class: "facts" },
          h("dt", {}, "Reference assembly"), h("dd", {}, v.reference_assembly),
          h("dt", {}, "Chromosome"), h("dd", {}, v.chromosome),
          h("dt", {}, "Position"), h("dd", {}, fmt(v.position)),
          h("dt", {}, "Alleles"), h("dd", {}, v.reference_allele + ">" + v.alternate_allele),
          h("dt", {}, "Annotation"), h("dd", {}, "ClinVar evidence on demand"),
          h("dt", {}, "Cohort frequency"), h("dd", {}, "Available only through a governed aggregate release")),
        h("div", { class: "population-frequency-controls" },
          h("p", { class: "fine" }, "Compare against an approved public reference. Choose the assembly recorded for this variant."),
          lookupButton, frequencyPanel(v)),
        h("div", { class: "clinvar-controls" },
          h("p", { class: "fine" }, isSubstitution(v)
            ? "Review public variant-level evidence from a provenance-linked ClinVar snapshot."
            : "ClinVar evidence currently supports SNVs and MNV substitutions; indels are not normalized yet."),
          clinvarButton, clinicalPanel(v)));
    }));
    if (activeMatches.length) {
      output.append(h("p", { class: "fine" }, "The reference and ClinVar lookups do not read participant-level genotype calls or bypass the consent, privacy, or release workflow."));
      if (!isSteward()) output.append(h("p", { class: "fine" }, "Exact coordinates identify reference loci; this page does not expose raw genotype calls, donor identities, or unprotected cohort frequencies."));
    }
  }

  async function lookupFrequencies(v) {
    const selectedAssembly = assembly.value;
    if (!selectedAssembly) return;
    const key = variantKey(v);
    frequencyResults.set(key, { status: "loading", assembly: selectedAssembly });
    renderMatches();
    const params = new URLSearchParams({
      chromosome: String(v.chromosome).replace(/^chr/i, ""),
      position: String(v.position),
      reference_allele: v.reference_allele,
      alternate_allele: v.alternate_allele,
      assembly: selectedAssembly,
    });
    const result = await api("/variants/population-frequency?" + params.toString());
    if (assembly.value !== selectedAssembly) return;
    frequencyResults.set(key, result.ok ? result.data : { status: "error", message: errorText(result) });
    renderMatches();
  }

  async function lookupClinVar(v) {
    const selectedAssembly = assembly.value;
    if (!selectedAssembly || !isSubstitution(v)) return;
    const key = variantKey(v);
    clinicalResults.set(key, { status: "loading", assembly: selectedAssembly });
    renderMatches();
    const params = new URLSearchParams({
      chromosome: String(v.chromosome).replace(/^chr/i, ""),
      position: String(v.position),
      reference_allele: v.reference_allele,
      alternate_allele: v.alternate_allele,
      assembly: selectedAssembly,
    });
    const result = await api("/variants/clinical-annotations?" + params.toString());
    if (assembly.value !== selectedAssembly) return;
    clinicalResults.set(key, result.ok ? result.data : { status: "error", message: errorText(result) });
    renderMatches();
  }

  async function search() {
    if (!query.value.trim()) { output.replaceChildren(notice("warn", "Enter a coordinate or variant ID.")); return; }
    button.disabled = true;
    const result = await api("/variants/search?q=" + encodeURIComponent(query.value.trim()));
    button.disabled = false;
    if (!result.ok) { output.replaceChildren(notice("err", errorText(result))); return; }
    const data = result.data || {};
    if (!data.matches?.length) {
      activeMatches = [];
      frequencyResults.clear();
      clinicalResults.clear();
      output.replaceChildren(notice("info", "No exact variant match was found in the active cohort."));
      return;
    }
    activeMatches = data.matches;
    frequencyResults.clear();
    clinicalResults.clear();
    if (!assembly.value) {
      const declared = activeMatches.find((v) => recognizedAssembly(v.reference_assembly))?.reference_assembly;
      if (declared) assembly.value = declared;
    }
    renderMatches();
  }

  assembly.addEventListener("change", () => {
    const hadResults = frequencyResults.size > 0 || clinicalResults.size > 0;
    frequencyResults.clear();
    clinicalResults.clear();
    if (activeMatches.length) renderMatches(hadResults);
  });
  query.addEventListener("keydown", (event) => { if (event.key === "Enter") search(); });
  root.append(card("Search locus", "Exact coordinate (CHR:POS:REF:ALT) or vN identifier",
    h("div", { class: "form" }, query, h("label", {}, "Reference assembly", assembly), button),
    output));
  if (initialQuery) search();
  return root;
}

