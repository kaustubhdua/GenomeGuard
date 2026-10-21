import { api } from "../api.js";
import { h, row, notice, errorText } from "../ui.js";

export async function render() {
  const root = h("div", {});
  root.dataset.title = "Federated analysis";
  root.append(h("h1", {}, "Federated analysis"),
    h("p", { class: "lede" }, "Hospitals keep their own genomes. They combine results using secret sharing, so no site, and not even the coordinator, sees another site's numbers. Only the total is revealed."));
  const res = await api("/federated/demo");
  if (!res.ok) { root.append(notice("err", errorText(res))); return root; }
  const d = res.data, lr = d.logistic_regression, af = d.allele_frequency;
  root.append(notice("warn", h("b", {}, "Simulated hospitals on synthetic data. "), "This is secure aggregation, not homomorphic encryption or a secure enclave."));
  const ledger = h("div", { class: "ledger" });
  ledger.append(row("Sites", "Each cohort plays one hospital",
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Hospital"), h("th", { class: "num" }, "Donors kept on site"))),
      h("tbody", {}, Object.entries(d.sites).map(([k, v]) => h("tr", {}, h("td", {}, k), h("td", { class: "num" }, v))))))));
  ledger.append(row("Allele frequencies", `${af.variants} variants`,
    h("p", { style: "margin:0 0 8px" }, "Pooled frequencies computed without any site sharing its rows. Largest difference from the pooled-data answer: ",
      h("b", {}, af.max_abs_error_vs_pooled.toExponential(1)), "."),
    h("p", { class: "muted", style: "margin:0 0 6px" }, "What a curious site actually receives from another site is one random-looking share:"),
    h("code", { class: "hash" }, af.a_share_one_site_saw.join("  "))));
  ledger.append(row("Model training", `Logistic regression, ${lr.features} features`,
    h("dl", { class: "facts" }, h("dt", {}, "AUC, federated"), h("dd", {}, String(lr.auc_federated)), h("dt", {}, "AUC, pooled data"), h("dd", {}, String(lr.auc_centralised)),
      h("dt", {}, "Largest weight difference"), h("dd", {}, lr.max_weight_difference_vs_centralised.toExponential(1))),
    h("p", { class: "muted" }, "Same model as training on pooled data, without pooling it. The phenotype is simulated from a few variants so there is a real signal.")));
  ledger.append(row("Limits", "Read before quoting", h("ul", { class: "plain" }, d.limits.map((t) => h("li", {}, t)))));
  root.append(ledger);
  return root;
}
