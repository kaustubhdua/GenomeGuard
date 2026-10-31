// Sample data for previewing the interface when a live source is empty or unreachable.
// Everything here is illustrative. Pages that use it must say so on screen (see sampleNotice in ui.js).
// Chromosome lengths are the public GRCh38 reference lengths; coverage and dataset records are invented.

const LENGTHS = [
  ["1", 248956422], ["2", 242193529], ["3", 198295559], ["4", 190214555], ["5", 181538259],
  ["6", 170805979], ["7", 159345973], ["8", 145138636], ["9", 138394717], ["10", 133797422],
  ["11", 135086622], ["12", 133275309], ["13", 114364328], ["14", 107043718], ["15", 101991189],
  ["16", 90338345], ["17", 83257441], ["18", 80373285], ["19", 58617616], ["20", 64444167],
  ["21", 46709983], ["22", 50818468], ["X", 156040895], ["Y", 57227415], ["MT", 16569],
];
const COVERAGE = {
  "21": { variant_data_loaded: true, variant_count: 640212, first_position: 5110000, last_position: 46600000 },
  "22": { variant_data_loaded: true, variant_count: 1073741, first_position: 10510000, last_position: 50800000 },
};

export function sampleChromosomes(assembly = "GRCh38") {
  return {
    reference_assembly: assembly,
    provenance_note: "Sample view. Chromosome lengths are the public GRCh38 reference lengths; the variant coverage shown is invented to preview the layout.",
    chromosomes: LENGTHS.map(([chromosome, length_bp]) => ({
      chromosome, length_bp,
      kind: chromosome === "X" || chromosome === "Y" ? "sex" : chromosome === "MT" ? "mitochondrial" : "autosome",
      data_coverage: COVERAGE[chromosome] || { variant_data_loaded: false, variant_count: 0, first_position: null, last_position: null },
    })),
  };
}

const hex = (seed) => {
  let x = seed >>> 0, out = "";
  for (let i = 0; i < 64; i++) { x = (Math.imul(x, 1664525) + 1013904223) >>> 0; out += (x >>> 28).toString(16); }
  return out;
};

export function sampleDatasets() {
  return {
    provenance_note: "Sample view. These dataset records are invented to preview the layout. They are not imports and carry no consent or authorization.",
    datasets: [
      { source_name: "Sample cohort A (illustrative)", dataset_key: "sample-cohort-a", source_release: "2026.1", reference_assembly: "GRCh38",
        source_url: "", file_sha256: hex(11), sample_count: 2504, variant_count: 1073741, genotype_call_count: 2688558264, imported_at: "2026-09-14T10:22:00Z" },
      { source_name: "Sample cohort B (illustrative)", dataset_key: "sample-cohort-b", source_release: "2026.1", reference_assembly: "GRCh38",
        source_url: "", file_sha256: hex(29), sample_count: 612, variant_count: 640212, genotype_call_count: 391808544, imported_at: "2026-09-21T16:05:00Z" },
      { source_name: "Sample cohort C (illustrative)", dataset_key: "sample-cohort-c", source_release: "2025.4", reference_assembly: "GRCh37",
        source_url: "", file_sha256: hex(47), sample_count: 188, variant_count: 214903, genotype_call_count: 40401764, imported_at: "2026-10-02T08:40:00Z" },
    ],
  };
}

// A request the way the pipeline draws it: protected release, one protection applied.
export function sampleStages() {
  return [
    { id: "consent", t: "Consent agent", short: "Consent", state: "ok", says: "Sample: 453 of 600 donors pass the permission rules." },
    { id: "risk", t: "Privacy risk agent", short: "Risk", state: "warn", says: "Sample: re-identification risk was high, low after protections." },
    { id: "protect", t: "Protection ladder", short: "Protect", state: "warn", says: "Sample: 1 protection applied, very rare variants dropped." },
    { id: "monitor", t: "Anomaly monitor", short: "Watch", state: "ok", says: "Sample: query pattern looked normal." },
    { id: "decide", t: "Access decision", short: "Decide", state: "warn", says: "Sample: approved with protections. Made by fixed rules, not by a model." },
    { id: "explain", t: "Explainer agent", short: "Explain", state: "ok", says: "Sample: wrote the plain-language reason." },
    { id: "audit", t: "Audit agent", short: "Record", state: "ok", says: "Sample: added the decision to the chain." },
  ];
}
