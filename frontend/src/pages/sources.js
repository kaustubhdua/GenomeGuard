import { h, card, notice } from "../ui.js";
import { loadPublicCatalogue } from "../catalogue-api.js";

const LIFECYCLE_STAGES = [
  ["discovered", "Discovered"],
  ["metadata_registered", "Metadata registered"],
  ["downloaded", "Downloaded"],
  ["checksum_verified", "Checksum verified"],
  ["qc_validated", "QC validated"],
  ["steward_approved", "Steward approved"],
  ["imported", "Imported"],
  ["available_for_research", "Available for permitted research"],
];
const LIFECYCLE_LABELS = {
  complete: "Complete",
  not_started: "Not started",
  pending: "Pending exact-artifact review",
  not_imported: "Not imported",
  not_available: "Not available",
};

function externalLink(url, label) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:") return h("span", { class: "muted" }, "Link unavailable");
    return h("a", {
      href: parsed.href,
      target: "_blank",
      rel: "noopener noreferrer",
      class: "source-link",
    }, label);
  } catch {
    return h("span", { class: "muted" }, "Link unavailable");
  }
}

function sourceCard(source) {
  const lifecycle = source.lifecycle_status || {};
  return h("article", { class: "card source-card" },
    h("div", { class: "source-card-top" },
      h("span", { class: "tag" }, source.data_type || "Data source"),
      h("span", { class: "source-status" }, "Not imported")),
    h("h2", {}, source.name || "Unnamed source"),
    h("p", { class: "muted" }, source.provider || "Provider not recorded"),
    h("dl", { class: "source-facts" },
      h("div", {}, h("dt", {}, "Release"), h("dd", {}, source.release || "Not pinned")),
      h("div", {}, h("dt", {}, "Assembly"), h("dd", {}, source.assembly || "Verify artifact")),
      h("div", {}, h("dt", {}, "Terms review"), h("dd", {}, "Pending exact-artifact review"))),
    h("p", {}, source.summary || "Source description unavailable."),
    h("p", { class: "source-review-note" }, source.reuse_review || "Review applicable source terms before use."),
    h("p", { class: "fine" }, source.workflow || "No local workflow recorded."),
    h("details", { class: "source-lifecycle" },
      h("summary", {}, "Dataset lifecycle status"),
      h("ol", { class: "source-lifecycle-list" },
        ...LIFECYCLE_STAGES.map(([key, label]) => {
          const status = lifecycle[key] || "not_started";
          return h("li", {},
            h("span", {}, label),
            h("span", { class: "source-lifecycle-state" }, LIFECYCLE_LABELS[status] || "Not recorded"));
        }))),
    h("div", { class: "source-links" },
      externalLink(source.source_url, "Open source"),
      externalLink(source.terms_url, "Review terms and policy")));
}

async function renderCatalogue() {
  const root = h("div", { class: "stack source-page" },
    h("section", { class: "card hero source-hero" },
      h("div", { class: "hero-copy" },
        h("h1", {}, "Public source discovery"),
        h("p", { class: "lede" }, "Find source-backed genomic references and the local workflows that can process them. This is a discovery index, not an import or approval record."),
        h("div", { class: "dataset-hero-meta" },
          h("span", { class: "status-dot" }, "Source references only"),
          h("span", { class: "muted" }, "No source data is downloaded by this page")))));

  const response = await loadPublicCatalogue("sources");
  if (!response.ok) {
    const retry = h("button", {
      class: "btn",
      onclick: async () => {
        retry.disabled = true;
        retry.textContent = "Checking…";
        root.replaceWith(await renderCatalogue());
      },
    }, "Retry connection");
    root.append(notice("warn",
      h("strong", {}, "Source discovery could not be reached."),
      h("p", { class: "muted" }, "No source records are shown. Check the connection and try again."),
      h("div", { class: "hero-actions" }, retry)));
    return root;
  }

  const data = response.data || {};
  const sources = Array.isArray(data.sources) ? data.sources : [];
  root.append(notice("warn",
    h("strong", {}, "Public availability is not approval."),
    h("p", { class: "muted" }, data.provenance_note ||
      "Review the exact artifact, source terms, assembly, and intended use before any import. Listing a source does not establish participant-specific consent.")));

  if (!sources.length) {
    root.append(card("No source records are available", "The discovery index is empty."));
  } else {
    root.append(h("section", { class: "grid g2 source-grid", "aria-label": "Public genomic sources" },
      ...sources.map(sourceCard)));
  }

  root.append(card("Discovery is separate from imported data", "Import remains steward-controlled",
    h("p", { class: "muted" }, "These records do not appear in the verified dataset catalogue, variant explorer, or research releases. A steward must review the exact release and reuse statement, verify the artifact checksum and assembly, and complete the applicable import and count reconciliation steps."),
    h("div", { class: "hero-actions" },
      h("a", { class: "btn ghost", href: "#/datasets" }, "View imported datasets"),
      h("a", { class: "btn ghost", href: "#/dataset-qc" }, "Open dataset QC"))));
  return root;
}

export async function render() {
  return renderCatalogue();
}
