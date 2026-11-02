import { api, isSteward, state, uploadVcfQc } from "../api.js";
import { h, card, notice, errorText } from "../ui.js";

const fmt = (v) => v == null ? "Not recorded" : Number(v).toLocaleString("en-US");
const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;

function bytes(value) {
  if (value == null) return "Not recorded";
  const units = ["B", "KiB", "MiB", "GiB"];
  let size = Number(value), unit = 0;
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++; }
  return `${size.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${units[unit]}`;
}

function downloadFile(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = h("a", { href: url, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function safeExport(report) {
  const sourceStats = report.statistics || {};
  const numericFields = [
    "source_record_count", "split_variant_count", "genotype_cells", "called_genotype_cells",
    "fully_missing_genotype_cells", "partially_missing_genotype_cells", "missing_alleles",
    "total_alleles", "unknown_ploidy_genotype_cells", "called_alleles",
    "alternate_allele_copies",
  ];
  const nonNegativeInteger = (value) => Number.isSafeInteger(value) && value >= 0 ? value : null;
  const stats = Object.fromEntries(numericFields.map((key) => [key, nonNegativeInteger(sourceStats[key])]));
  const countMap = (source, allowedKeys) => Object.fromEntries(
    Object.entries(source || {}).filter(([key, value]) => allowedKeys.includes(key)
      && Number.isSafeInteger(value) && value >= 0),
  );
  stats.chromosome_variant_counts = countMap(sourceStats.chromosome_variant_counts,
    [...Array.from({ length: 22 }, (_, index) => String(index + 1)), "X", "Y", "MT"]);
  stats.variant_type_counts = countMap(sourceStats.variant_type_counts, ["SNP", "MNP", "INDEL"]);
  for (const key of ["fully_missing_genotype_cell_rate", "missing_allele_rate"]) {
    stats[key] = Number.isFinite(sourceStats[key]) && sourceStats[key] >= 0 && sourceStats[key] <= 1
      ? sourceStats[key] : null;
  }
  for (const [key, allowed] of [
    ["alternate_allele_frequency", ["minimum", "mean", "maximum", "measured_alternate_alleles"]],
    ["variant_quality_score", ["minimum", "mean", "maximum", "measured_split_variants", "missing_quality_count"]],
    ["genotype_quality_score", ["minimum", "mean", "maximum", "measured_genotype_cells", "missing_genotype_cells", "available"]],
  ]) {
    const source = sourceStats[key] || {};
    const frequency = key === "alternate_allele_frequency";
    const countFields = new Set(allowed.filter((field) => field.startsWith("measured_")
      || field.startsWith("missing_")));
    stats[key] = Object.fromEntries(allowed.map((field) => [field,
      field === "available" ? source[field] === true
        : countFields.has(field) ? nonNegativeInteger(source[field])
          : Number.isFinite(source[field]) && source[field] >= 0
            && (!frequency || source[field] <= 1) ? source[field] : null]));
  }
  const metadataSource = report.metadata && typeof report.metadata === "object" ? report.metadata : {};
  const metadata = Object.fromEntries([
    "sample_count", "metadata_line_count", "contig_definition_count",
    "info_definition_count", "format_definition_count", "filter_definition_count",
  ].map((key) => [key, nonNegativeInteger(metadataSource[key])]));
  metadata.vcf_version = /^VCFv4\.\d+$/.test(metadataSource.vcf_version || "")
    ? metadataSource.vcf_version : null;
  metadata.reference_declaration_present = metadataSource.reference_declaration_present === true;
  metadata.reference_declarations = (Array.isArray(metadataSource.reference_declarations)
    ? metadataSource.reference_declarations : [])
    .filter((value) => ["GRCh37", "GRCh38"].includes(value));
  const statuses = ["passed", "failed", "warning", "not_assessed", "insufficient_evidence"];
  const checkIds = new Set([
    "assembly_argument", "file_readable", "checksum", "header_and_assembly", "sample_columns",
    "metadata_completeness", "records_and_genotypes", "checksum_stability", "source_and_reuse_review",
  ]);
  const checks = Array.isArray(report.checks) ? report.checks : [];
  return {
    report_version: 1,
    generated_at: /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(report.generated_at || "")
      ? report.generated_at : null,
    status: ["PASSED", "PASSED_WITH_WARNINGS", "FAILED"].includes(report.status) ? report.status : "FAILED",
    import_eligibility: "NOT_ESTABLISHED",
    file: {
      name: "[redacted from export]",
      size_bytes: nonNegativeInteger(report.file?.size_bytes),
      sha256: /^[0-9a-f]{64}$/.test(report.file?.sha256 || "") ? report.file.sha256 : null,
    },
    reference_assembly: ["GRCh37", "GRCh38"].includes(report.reference_assembly)
      ? report.reference_assembly : null,
    metadata,
    checks: checks.map((check) => ({
      id: checkIds.has(check?.id) ? check.id : "unknown_check",
      status: statuses.includes(check?.status) ? check.status : "not_assessed",
    })),
    statistics: report.statistics && typeof report.statistics === "object"
      && !Array.isArray(report.statistics) ? stats : null,
    warning_count: nonNegativeInteger(report.warning_count)
      ?? (Array.isArray(report.warnings) ? report.warnings.length : 0),
    error_count: nonNegativeInteger(report.error_count)
      ?? (Array.isArray(report.errors) ? report.errors.length : 0),
    note: "This allowlisted export omits sample IDs, file paths, free-text parser details, and raw genotype records. Import eligibility is not established.",
  };
}

function normalizeImportedReport(report) {
  const normalized = safeExport(report);
  return {
    ...normalized,
    warnings: [],
    errors: [],
    recommendations: [
      "Details from unsigned reports are omitted. Verify source terms, permitted reuse, and provenance with a trusted steward.",
    ],
  };
}

function renderReport(report, parent, includeDetails = false) {
  const stats = report.statistics || {};
  const file = report.file || {};
  const importEligibility = "NOT_ESTABLISHED";
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const warningCount = Number.isSafeInteger(report.warning_count) ? report.warning_count
    : Array.isArray(report.warnings) ? report.warnings.length : 0;
  const errorCount = Number.isSafeInteger(report.error_count) ? report.error_count
    : Array.isArray(report.errors) ? report.errors.length : 0;
  const checksByStatus = checks.reduce((counts, check) => {
    counts[check.status] = (counts[check.status] || 0) + 1;
    return counts;
  }, {});
  const count = (value) => fmt(value);
  const metrics = [
    ["Source records", count(stats.source_record_count)],
    ["Split ALT variants", count(stats.split_variant_count)],
    ["Genotype cells", count(stats.genotype_cells)],
    ["Fully missing cells", count(stats.fully_missing_genotype_cells)],
    ["Fully missing cell rate", stats.fully_missing_genotype_cell_rate == null
      ? "Not measured" : `${(100 * stats.fully_missing_genotype_cell_rate).toLocaleString("en-US", { maximumFractionDigits: 4 })}%`],
    ["Partially missing cells", count(stats.partially_missing_genotype_cells)],
    ["Missing allele rate", stats.missing_allele_rate == null
      ? "Not measured" : `${(100 * stats.missing_allele_rate).toLocaleString("en-US", { maximumFractionDigits: 4 })}%`
        + ` · ${count(stats.unknown_ploidy_genotype_cells)} cells excluded (ploidy unknown)`],
    ["Variant classes", Object.entries(stats.variant_type_counts || {}).map(([type, value]) => `${type}: ${count(value)}`).join(" · ") || "Not measured"],
    ["Chromosome counts", Object.entries(stats.chromosome_variant_counts || {}).map(([chromosome, value]) => `${chromosome}: ${count(value)}`).join(" · ") || "Not measured"],
    ["ALT frequency min / mean / max", stats.alternate_allele_frequency?.minimum == null ? "Not measured"
      : [stats.alternate_allele_frequency.minimum, stats.alternate_allele_frequency.mean,
        stats.alternate_allele_frequency.maximum].map((value) =>
        `${(100 * value).toLocaleString("en-US", { maximumFractionDigits: 4 })}%`).join(" / ")],
    ["QUAL min / mean / max", stats.variant_quality_score?.minimum == null ? "Not measured"
      : [stats.variant_quality_score.minimum, stats.variant_quality_score.mean,
        stats.variant_quality_score.maximum].map((value) =>
        Number(value).toLocaleString("en-US", { maximumFractionDigits: 4 })).join(" / ")],
    ["GQ min / mean / max", !stats.genotype_quality_score?.available ? "Not present or not measured"
      : [stats.genotype_quality_score.minimum, stats.genotype_quality_score.mean,
        stats.genotype_quality_score.maximum].map((value) =>
        Number(value).toLocaleString("en-US", { maximumFractionDigits: 4 })).join(" / ")
        + ` · ${count(stats.genotype_quality_score.missing_genotype_cells)} missing`],
  ];
  const detail = h("section", { class: "qc-report stack", "aria-label": "Quality control results" },
    h("header", { class: "qc-report-head" },
      h("div", {}, h("p", { class: "eyebrow" }, "Executive summary"),
        h("h2", {}, `Validation ${String(report.status || "UNKNOWN").replaceAll("_", " ").toLowerCase()}`),
        h("p", { class: "muted" }, `${count(checksByStatus.passed || 0)} passed · ${count(checksByStatus.failed || 0)} failed · ${count(checksByStatus.warning || 0)} warnings · ${count(checksByStatus.insufficient_evidence || 0)} insufficient evidence`)),
      h("span", { class: "pill " + (report.status === "FAILED" ? "bad" : report.status === "PASSED" ? "good" : "warn") },
        String(report.status || "UNKNOWN").replaceAll("_", " "))),
    notice(report.status === "FAILED" ? "err" : report.status === "PASSED" ? "info" : "warn",
      `Import eligibility: ${importEligibility.replaceAll("_", " ")}. QC success never grants source permission or import approval.`),
    h("details", { class: "entry", open: true },
      h("summary", {}, "File and reference metadata"),
      h("dl", { class: "facts" },
        h("dt", {}, "File name"), h("dd", {}, includeDetails ? String(file.name || "Not recorded") : "[redacted from preview]"),
        h("dt", {}, "File size"), h("dd", {}, bytes(file.size_bytes)),
        h("dt", {}, "SHA-256"), h("dd", { class: "mono" }, String(file.sha256 || "Not calculated")),
        h("dt", {}, "Assembly"), h("dd", {}, String(report.reference_assembly || "Not established")),
        h("dt", {}, "VCF version"), h("dd", {}, String(report.metadata?.vcf_version || "Not established")),
        h("dt", {}, "Reference declaration"), h("dd", {}, (report.metadata?.reference_declarations || []).join(" · ") || "Not recorded"),
        h("dt", {}, "Sample columns"), h("dd", {}, count(report.metadata?.sample_count)),
        h("dt", {}, "Header metadata lines"), h("dd", {}, count(report.metadata?.metadata_line_count)),
        h("dt", {}, "INFO / FORMAT / FILTER / contig definitions"),
        h("dd", {}, ["info_definition_count", "format_definition_count", "filter_definition_count", "contig_definition_count"]
          .map((key) => count(report.metadata?.[key])).join(" / ")))),
    h("details", { class: "entry", open: true },
      h("summary", {}, "Measured aggregate metrics"),
      h("dl", { class: "facts" }, metrics.flatMap(([label, value]) => [h("dt", {}, label), h("dd", {}, value)]))),
    h("details", { class: "entry" },
      h("summary", {}, "Validation breakdown"),
      h("ul", { class: "qc-check-list" }, checks.map((check) =>
        h("li", { class: "qc-check-" + String(check.status || "unknown") },
          h("strong", {}, `${String(check.status || "unknown").replaceAll("_", " ")} · ${String(check.id || "check")}: `),
          includeDetails ? String(check.detail || "No further detail recorded.")
            : "Details are omitted for an unsigned imported report.")))),
    h("details", { class: "entry" },
      h("summary", {}, "Warnings and errors"),
      h("h3", {}, "Warnings"),
      includeDetails && (report.warnings || []).length
        ? h("ul", {}, report.warnings.map((message) => h("li", {}, String(message))))
        : h("p", { class: "muted" }, warningCount
          ? `${count(warningCount)} warning(s) recorded; details are omitted from this unsigned preview.`
          : "No warnings recorded."),
      h("h3", {}, "Errors"),
      includeDetails && (report.errors || []).length
        ? h("ul", {}, report.errors.map((message) => h("li", {}, String(message))))
        : h("p", { class: "muted" }, errorCount
          ? `${count(errorCount)} error(s) recorded; details are omitted from this unsigned preview.`
          : "No errors recorded.")),
    h("details", { class: "entry" },
      h("summary", {}, "Recommendations and technical notes"),
      h("ul", {}, (report.recommendations || []).map((message) => h("li", {}, String(message)))),
      h("p", { class: "fine" }, `Generated: ${String(report.generated_at || "Not recorded")}. Metrics count each split ALT as one variant; missingness is calculated per sample-by-split-ALT cell. Missing-allele rate excludes cells whose ploidy cannot be inferred. QUAL/GQ and ALT frequency summaries are unweighted across split ALT rows.`)));
  const exports = h("div", { class: "hero-actions" },
    h("button", { type: "button", onclick: () => {
      downloadFile("genomeguard-vcf-qc.json", JSON.stringify(safeExport(report), null, 2) + "\n", "application/json");
    } }, "Download JSON"),
    h("button", { type: "button", class: "ghost", onclick: () => {
      const lines = [
        "GenomeGuard VCF quality-control report",
        `Validation: ${report.status}`,
        `Import eligibility: ${importEligibility}`,
        `File size: ${bytes(file.size_bytes)}`,
        `SHA-256: ${file.sha256 || "Not calculated"}`,
        `Assembly: ${report.reference_assembly || "Not established"}`,
        `Warnings: ${warningCount}`,
        `Errors: ${errorCount}`,
        ...metrics.map(([label, value]) => `${label}: ${value}`),
        "",
        "Validation checks:",
        ...checks.map((check) => `- ${check.status}: ${check.id}`),
        "",
        "Check source terms, permitted reuse, and provenance with a trusted steward.",
        "",
        "Import eligibility is separate from QC and remains NOT_ESTABLISHED.",
      ];
      downloadFile("genomeguard-vcf-qc.txt", lines.join("\n") + "\n", "text/plain");
    } }, "Download human-readable report"));
  parent.replaceChildren(detail, exports,
    h("p", { class: "fine" }, "Report contains aggregate QC only and omits sample identifiers and raw genotype rows. The JSON is unsigned; verify its origin before relying on it."));
}

export async function render() {
  const root = h("div", { class: "stack" });
  root.append(h("section", { class: "card hero" }, h("h1", {}, "Dataset QC & import review"),
    h("p", { class: "lede" }, "Steward-only inspection of the active in-memory cohort, its provenance and measurable quality indicators. This is an inspection report, not a dataset approval or production-readiness certificate.")));
  if (!isSteward() && !state.adminKey) {
    root.append(notice("warn", "This page is restricted to an authenticated data steward."));
    return root;
  }

  const reportOutput = h("div", { "aria-live": "polite" });
  const uploadStatus = h("div", { role: "status", "aria-live": "polite" });
  const assemblySelect = h("select", { "aria-label": "Reference assembly" },
    h("option", { value: "" }, "Select assembly explicitly"),
    h("option", { value: "GRCh37" }, "GRCh37"),
    h("option", { value: "GRCh38" }, "GRCh38"));
  const expectedChecksum = h("input", {
    type: "text", inputmode: "text", autocomplete: "off", spellcheck: "false",
    placeholder: "Optional independently obtained SHA-256",
    "aria-label": "Optional expected SHA-256 checksum",
  });
  const uploadButton = h("button", { type: "submit", disabled: true }, "Run VCF QC");
  const cancelButton = h("button", { type: "button", class: "ghost", hidden: true }, "Cancel request");
  const uploadForm = h("form", { class: "qc-upload stack" });
  let selectedFile = null;
  let activeController = null;
  const clearOutput = (message) => {
    reportOutput.replaceChildren();
    uploadStatus.replaceChildren(message ? notice("warn", message) : "");
  };
  const reportFile = h("input", {
    type: "file", accept: ".json,application/json", "aria-label": "QC report JSON preview",
    onchange: async (event) => {
      const file = event.currentTarget.files?.[0];
      if (!file) return;
      try {
        if (file.size > 5 * 1024 * 1024) throw new TypeError("QC report exceeds the 5 MiB preview limit.");
        const report = JSON.parse(await file.text());
        if (report.report_version !== 1 || !Array.isArray(report.checks)
            || report.checks.length > 100
            || !["PASSED", "PASSED_WITH_WARNINGS", "FAILED"].includes(report.status)
            || !report.checks.every((check) => check && typeof check === "object")) {
          throw new TypeError("Unsupported or incomplete QC report format.");
        }
        renderReport(normalizeImportedReport(report), reportOutput);
      } catch (error) {
        reportOutput.replaceChildren(notice("err",
          "Could not read this QC report: " + (error instanceof Error ? error.message : "invalid JSON")));
      }
    },
  });
  const vcfFile = h("input", {
    type: "file", accept: ".vcf,.vcf.gz,text/plain,application/gzip",
    "aria-label": "Select VCF or gzip-compressed VCF",
    onchange: async (event) => {
      selectedFile = event.currentTarget.files?.[0] || null;
      uploadButton.disabled = true;
      if (!selectedFile) { clearOutput(); return; }
      if (selectedFile.size === 0) { clearOutput("The selected file is empty."); selectedFile = null; return; }
      if (selectedFile.size > MAX_UPLOAD_BYTES) {
        clearOutput("File exceeds the 100 MiB upload limit."); selectedFile = null; return;
      }
      if (!/\.vcf(?:\.gz)?$/i.test(selectedFile.name)) {
        clearOutput("Choose a .vcf or .vcf.gz file."); selectedFile = null; return;
      }
      const head = new Uint8Array(await selectedFile.slice(0, 2).arrayBuffer());
      const isGzip = head[0] === 0x1f && head[1] === 0x8b;
      if (isGzip !== /\.vcf\.gz$/i.test(selectedFile.name)) {
        clearOutput("The filename extension does not match the file compression."); selectedFile = null; return;
      }
      if (!assemblySelect.value) {
        clearOutput("Select the reference assembly explicitly; GenomeGuard will not guess it.");
        return;
      }
      uploadButton.disabled = false;
      clearOutput(`${selectedFile.name} · ${bytes(selectedFile.size)} selected. The checksum will be calculated by the QC service.`);
    },
  });
  assemblySelect.addEventListener("change", () => {
    uploadButton.disabled = !selectedFile || !assemblySelect.value || Boolean(activeController);
  });
  expectedChecksum.addEventListener("input", () => {
    const value = expectedChecksum.value.trim();
    expectedChecksum.setCustomValidity(!value || /^[0-9a-f]{64}$/.test(value)
      ? "" : "Enter 64 lowercase hexadecimal characters.");
  });
  cancelButton.addEventListener("click", () => activeController?.abort());
  uploadForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedFile || !assemblySelect.value || !uploadForm.reportValidity()) return;
    reportOutput.replaceChildren();
    activeController = new AbortController();
    uploadButton.disabled = true;
    cancelButton.hidden = false;
    uploadStatus.replaceChildren(h("p", { class: "muted" },
      "Uploading to this GenomeGuard server, then validating. Browser fetch does not expose upload-byte progress; no percentage is estimated."),
      h("progress", { "aria-label": "Upload and QC in progress" }));
    try {
      const result = await uploadVcfQc(selectedFile, assemblySelect.value,
        expectedChecksum.value.trim(), activeController.signal);
      if (!result.ok) {
        uploadStatus.replaceChildren(notice("err", errorText(result)));
        return;
      }
      renderReport(result.data, reportOutput, true);
      uploadStatus.replaceChildren(notice(result.data.status === "FAILED" ? "err" :
        result.data.status === "PASSED" ? "info" : "warn", "QC processing completed."));
    } catch (error) {
      uploadStatus.replaceChildren(notice("err",
        "QC could not be completed: " + (error instanceof Error ? error.message : "unexpected error")));
    } finally {
      activeController = null;
      cancelButton.hidden = true;
      uploadButton.disabled = !selectedFile || !assemblySelect.value;
    }
  });
  uploadForm.append(
    h("label", {}, "VCF file (maximum 100 MiB)", vcfFile),
    h("label", {}, "Reference assembly", assemblySelect),
    h("label", {}, "Expected checksum (optional, independently obtained)", expectedChecksum),
    h("div", { class: "hero-actions" }, uploadButton, cancelButton),
    uploadStatus,
    reportOutput,
  );
  root.append(card("Run a VCF quality-control workflow", "Steward-only · temporary processing",
    h("p", { class: "muted" }, "Choose a VCF or gzip-compressed VCF and explicitly select its reference assembly. The file is sent only to this GenomeGuard server for bounded, temporary processing; it is not sent to a commercial or other third-party API and is deleted after processing. Use only a server deployment you trust for genomic information."),
    h("p", { class: "fine" }, "Uploads are capped at 100 MiB compressed and 1 GiB decompressed, with 16 MiB per VCF line, up to 10,000 sample columns, and 10 million sample-by-split-ALT genotype cells. Cancelling closes the browser request but may not interrupt validation already running on the server; temporary files are cleaned up when request processing exits."),
    uploadForm));
  root.append(card("Preview an existing JSON QC report", "Local preview",
    h("p", { class: "muted" }, "Choose a locally generated report JSON to inspect it in this browser. The report is read locally, not uploaded; unsigned reports may have been edited."),
    h("label", { class: "qc-report-preview-label" }, "Choose QC report JSON (maximum 5 MiB)", reportFile),
    h("p", { class: "fine" }, "Downloads redact the source filename. Report content is aggregate-only and does not include participant rows.")));
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
  const chromosomeRows = Object.entries(d.chromosome_variant_counts || {})
    .sort((a,b) => a[0].localeCompare(b[0], undefined, { numeric: true }))
    .map(([chrom, count]) => h("tr", {}, h("th", {}, chrom), h("td", {}, fmt(count))));
  root.append(card("Chromosome coverage", "Variant records in active cohort",
    h("div", { class: "tablewrap" }, h("table", {},
      h("thead", {}, h("tr", {}, h("th", {}, "Chromosome"), h("th", {}, "Variants"))),
      h("tbody", {}, chromosomeRows)))));
  root.append(notice("info", d.missingness_note || "Missingness provenance unavailable."),
    h("p", { class: "fine" }, "Source-file missingness, source citation/reuse terms, file size, import timestamp and independent checksum verification are not exposed by the active service. Do not infer that unavailable checks passed."));
  return root;
}
