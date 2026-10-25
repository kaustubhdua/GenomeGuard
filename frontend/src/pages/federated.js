import { api, state } from "../api.js";
import { h, row, notice, errorText } from "../ui.js";

export async function render() {
  const root = h("div", {});
  root.dataset.title = "Federated analysis";
  if (!state.demo) {
    root.append(h("h1", {}, "Federated analysis"),
      notice("warn", "The current multi-site and homomorphic-encryption walkthrough uses simulated sites and is disabled in the public-data research instance. It is not a deployed multi-organization federation."));
    return root;
  }
  root.append(h("h1", {}, "Federated analysis"),
    h("p", { class: "lede" }, "This experiment illustrates how sites could combine selected statistics using secret sharing without pooling their input rows. It uses simulated sites and does not represent a hardened multi-organization deployment."));
  const res = await api("/federated/demo");
  if (!res.ok) { root.append(notice("err", errorText(res))); return root; }
  const d = res.data, lr = d.logistic_regression, af = d.allele_frequency;
  root.append(notice("warn", h("b", {}, "Simulated hospitals on synthetic data. "), "The secret-sharing and Paillier sections are educational implementations using synthetic data; they are not independently audited security controls."));
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
  const he = h("div", { class: "ledger", style: "margin-top:14px" }, row("Homomorphic encryption", "Paillier, computing on encrypted counts", h("div", { class: "skeleton", style: "height:80px" })));
  root.append(he);
  api("/federated/he").then((r) => {
    if (!r.ok) { he.replaceChildren(row("Homomorphic encryption", "", notice("err", errorText(r)))); return; }
    const x = r.data;
    he.replaceChildren(row("Homomorphic encryption", `${x.key_bits}-bit key, ${x.variants} variants`,
      h("p", { style: "margin:0 0 8px" }, "Each hospital encrypts its allele counts. An aggregator adds the ciphertexts without being able to read any of them. Only the total is decrypted."),
      h("dl", { class: "facts" }, h("dt", {}, "Decrypted totals"), h("dd", {}, x.totals.join(", ")),
        h("dt", {}, "Equals plain sum"), h("dd", {}, x.matches_plaintext ? "yes, exactly" : "NO"),
        h("dt", {}, "Plaintexts the aggregator saw"), h("dd", {}, x.aggregator_saw.plaintexts)),
      h("p", { class: "muted", style: "margin:8px 0 4px" }, "What the aggregator actually holds (start of one ciphertext):"),
      h("code", { class: "hash" }, x.aggregator_saw.first_ciphertext_hex_prefix),
      h("ul", { class: "plain" }, x.limits.map((t) => h("li", {}, t)))));
  });
  return root;
}
