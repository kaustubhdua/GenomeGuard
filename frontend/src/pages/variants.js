import { api, isSteward } from "../api.js";
import { h, card, notice, errorText } from "../ui.js";

const fmt = (v) => v == null ? "Not recorded" : Number(v).toLocaleString("en-US");
export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" }, h("h1", {}, "Locus & variant inspector"),
    h("p", { class: "lede" }, "Find a variant by exact coordinate or GenomeGuard variant ID. This lookup returns locus metadata only; cohort frequencies and carrier evidence remain behind governed aggregate releases.")));
  const initialQuery = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
  const query = h("input", { type: "search", value: initialQuery, placeholder: "e.g. 22:105123:A:G or v42", "aria-label": "Variant coordinate or ID" });
  const output = h("div", { "aria-live": "polite" });
  const button = h("button", { onclick: search }, "Search variant");
  async function search() {
    if (!query.value.trim()) { output.replaceChildren(notice("warn", "Enter a coordinate or variant ID.")); return; }
    button.disabled = true;
    const result = await api("/variants/search?q=" + encodeURIComponent(query.value.trim()));
    button.disabled = false;
    if (!result.ok) { output.replaceChildren(notice("err", errorText(result))); return; }
    const data = result.data || {};
    if (!data.matches?.length) { output.replaceChildren(notice("info", "No exact variant match was found in the active cohort.")); return; }
    output.replaceChildren(...data.matches.map((v) => card("Variant v" + v.variant_id,
      v.chromosome + ":" + fmt(v.position) + " " + v.reference_allele + ">" + v.alternate_allele,
      h("dl", { class: "facts" },
        h("dt", {}, "Reference assembly"), h("dd", {}, v.reference_assembly),
        h("dt", {}, "Chromosome"), h("dd", {}, v.chromosome),
        h("dt", {}, "Position"), h("dd", {}, fmt(v.position)),
        h("dt", {}, "Alleles"), h("dd", {}, v.reference_allele + ">" + v.alternate_allele),
        h("dt", {}, "Annotation"), h("dd", {}, "Not linked to an annotation source"),
        h("dt", {}, "Cohort frequency"), h("dd", {}, "Available only through an authorized, transformed request")))));
    output.append(h("p", { class: "fine" }, data.frequency_policy));
    if (!isSteward()) output.append(h("p", { class: "fine" }, "Exact coordinates identify public reference loci; this page does not expose raw genotype calls, donor identities, or unprotected allele frequencies."));
  }
  query.addEventListener("keydown", (event) => { if (event.key === "Enter") search(); });
  root.append(card("Search locus", "Exact coordinate (CHR:POS:REF:ALT) or vN identifier",
    h("div", { class: "form" }, query, button), output));
  if (initialQuery) search();
  return root;
}
