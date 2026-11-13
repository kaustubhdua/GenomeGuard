import { h } from "../ui.js";

const ENDPOINT = "/research/ensembl/gene";
const SOURCE = "https://rest.ensembl.org";

function safeExternal(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") throw new Error("unsafe");
    return h("a", { href: parsed.href, target: "_blank", rel: "noopener noreferrer", class: "source-link" }, label);
  } catch {
    return h("span", { class: "muted" }, label);
  }
}

export function renderEnsemblPanel() {
  const root = h("section", { class: "card stack ensembl-panel", "aria-labelledby": "ensembl-heading" },
    h("div", {},
      h("p", { class: "eyebrow" }, "GENE IDENTITY · ENSEMBL"),
      h("h2", { id: "ensembl-heading" }, "Resolve a gene symbol"),
      h("p", { class: "muted" },
        "Resolve an exact human gene symbol to its stable Ensembl identifier, reference assembly, genomic coordinates and transcript metadata."),
      h("p", { class: "fine muted" },
        "This is source-backed gene identity only. It does not establish disease association, pathogenicity, diagnosis or clinical significance.")),
    h("form", { id: "ensembl-search-form", class: "research-search-form" },
      h("label", { for: "ensembl-symbol" }, "Human gene symbol"),
      h("input", { id: "ensembl-symbol", name: "symbol", type: "text", maxlength: "20",
        placeholder: "BRCA2", autocomplete: "off", required: true }),
      h("div", { class: "hero-actions" },
        h("button", { class: "btn", type: "submit" }, "Resolve gene"),
        safeExternal(SOURCE, "Ensembl REST documentation"))),
    h("div", { id: "ensembl-status", class: "fine muted", role: "status", "aria-live": "polite" },
      "Enter a gene symbol such as BRCA2 or TP53."),
    h("div", { id: "ensembl-result", class: "stack", "aria-live": "polite" }));

  const form = root.querySelector("#ensembl-search-form");
  const input = root.querySelector("#ensembl-symbol");
  const status = root.querySelector("#ensembl-status");
  const result = root.querySelector("#ensembl-result");
  const submit = form.querySelector('button[type="submit"]');
  let generation = 0;

  function renderGene(data) {
    const gene = data.gene || {};
    const geneUrl = "https://www.ensembl.org/Homo_sapiens/Gene/Summary?g=" + encodeURIComponent(gene.stable_id || "");
    const transcriptRows = (Array.isArray(data.transcripts) ? data.transcripts : []).map((item) =>
      h("li", {}, (item.id || "Transcript") + (item.version ? "." + item.version : "")
        + " · " + (item.biotype || "biotype not supplied")
        + (item.is_canonical ? " · canonical" : "")));
    result.replaceChildren(
      h("article", { class: "card research-paper" },
        h("div", { class: "source-card-top" },
          h("span", { class: "tag" }, "Ensembl REST API"),
          h("span", { class: "fine" }, gene.assembly || "Assembly not supplied")),
        h("h3", {}, (gene.symbol || data.query_symbol || "Gene") + " · " + (gene.stable_id || "Stable ID unavailable")),
        h("p", { class: "fine" }, "Biotype: " + (gene.biotype || "Not supplied")
          + " · Gene version: " + (gene.gene_version ?? "Not supplied")),
        h("p", { class: "fine" }, "Location: " + (gene.chromosome || "Chr?") + ":"
          + (gene.start ?? "?") + "-" + (gene.end ?? "?")
          + " · Strand: " + (gene.strand === 1 ? "+" : gene.strand === -1 ? "-" : "not supplied")),
        h("p", { class: "fine muted" }, "Canonical transcript: " + (gene.canonical_transcript || "Not supplied")
          + " · Transcripts returned: " + String(data.transcript_count_returned ?? 0)),
        transcriptRows.length ? h("details", {},
          h("summary", {}, "View returned transcripts"),
          h("ul", { class: "fine" }, ...transcriptRows)) : null,
        h("div", { class: "source-links" }, safeExternal(geneUrl, "Open Ensembl gene record")),
        h("div", { class: "hero-actions" },
          h("button", { class: "btn secondary", id: "ensembl-use-target", type: "button" },
            "Use this ID in Open Targets"))));
    const useTarget = result.querySelector("#ensembl-use-target");
    useTarget.addEventListener("click", () => {
      const targetInput = document.querySelector("#ot-ensembl-id");
      if (!targetInput || !gene.stable_id) {
        status.textContent = "The Open Targets panel is not available on this page.";
        return;
      }
      targetInput.value = gene.stable_id;
      targetInput.focus();
      targetInput.scrollIntoView({ behavior: "smooth", block: "center" });
      status.textContent = "Ensembl gene ID copied into the Open Targets panel. Review the ID and run its search.";
    });
  }

  async function search(event) {
    event.preventDefault();
    const symbol = input.value.trim();
    if (!/^[A-Za-z][A-Za-z0-9.-]{0,19}$/.test(symbol)) {
      status.textContent = "Enter a valid gene symbol containing 1 to 20 letters, digits, dots or hyphens.";
      return;
    }
    const current = ++generation;
    status.textContent = "Resolving gene identity from Ensembl…";
    result.replaceChildren();
    submit.disabled = true;
    try {
      const response = await fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ symbol }),
        cache: "no-store",
      });
      const data = await response.json();
      if (current !== generation) return;
      if (!response.ok) {
        throw new Error(data.message || "Ensembl gene lookup failed.");
      }
      renderGene(data);
      status.textContent = "Resolved " + (data.gene?.symbol || symbol)
        + " from Ensembl. Reference coordinates are release/assembly-specific.";
    } catch (error) {
      if (current !== generation) return;
      status.textContent = error.message || "Ensembl is temporarily unavailable.";
    } finally {
      if (current === generation) submit.disabled = false;
    }
  }

  form.addEventListener("submit", search);
  return root;
}
