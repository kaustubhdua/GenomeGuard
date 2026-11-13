// Researcher-facing product walkthrough. It deliberately uses no privileged credentials,
 // creates no requests, and never changes the active identity.
import { state } from "./api.js";
import { h } from "./ui.js";

const STEPS = [
  {
    title: "Welcome to GenomeGuard",
    hash: "#/overview",
    text: "GenomeGuard brings public biomedical literature discovery together with a governed research workspace. Public demo mode uses synthetic records only; it is not an institutional identity or consent system.",
  },
  {
    title: "Discover biomedical literature",
    hash: "#/research",
    text: "Search by department, symptom description, gene, disease or research question. Publication records come from Europe PMC and PubMed, and each result links back to its source. Search is for research discovery, not diagnosis.",
  },
  {
    title: "Explore datasets and provenance",
    hash: "#/datasets",
    text: "Review dataset metadata, source declarations and provenance before using a dataset. A public catalogue entry does not mean participant-level consent or controlled access has been established.",
  },
  {
    title: "Understand research governance",
    hash: "#/requests",
    text: "The synthetic workspace illustrates purpose-bound research requests and policy checks. Example decisions and synthetic consent are demonstrations only; real approvals require an institution's authorized reviewers and verified consent evidence.",
  },
  {
    title: "Participant transparency",
    hash: "#/donor",
    last: true,
    text: "The participant view demonstrates the kind of consent and data-use transparency a real deployment must provide. This synthetic record does not change real-world consent or authorize access to real genomic data.",
  },
];

let index = 0;
let dialog = null;
let returnFocus = null;

function close() {
  if (dialog) dialog.remove();
  dialog = null;
  document.body.classList.remove("tour-open");
  document.removeEventListener("keydown", onKey);
  const target = returnFocus && returnFocus.isConnected ? returnFocus : document.getElementById("open-cmdk");
  returnFocus = null;
  target?.focus();
}
function onKey(event) {
  if (event.key === "Escape") {
    close();
    return;
  }
  if (event.key !== "Tab" || !dialog) return;
  const focusable = Array.from(dialog.querySelectorAll("button:not([disabled])"));
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  const heading = dialog.querySelector("h2");
  const active = document.activeElement;
  if (!dialog.contains(active)) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  } else if (event.shiftKey && (active === first || active === heading)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (active === last || active === heading)) {
    event.preventDefault();
    first.focus();
  }
}
async function show(next) {
  index = Math.max(0, Math.min(STEPS.length - 1, next));
  const step = STEPS[index];
  if (!dialog) {
    returnFocus = document.getElementById("open-cmdk") || document.activeElement;
    dialog = h("section", {
      class: "tour",
      role: "dialog",
      "aria-label": "Guided tour",
      "aria-modal": "true",
      "aria-live": "polite",
    });
    document.body.append(dialog);
    document.body.classList.add("tour-open");
    document.addEventListener("keydown", onKey);
  }
  const heading = h("h2", { tabindex: "-1" }, step.title);
  const nextButton = h("button", {
    class: step.last ? "" : "",
    onclick: () => step.last ? close() : show(index + 1),
  }, step.last ? "Finish" : "Next");
  dialog.replaceChildren(
    h("div", { class: "tour-top" },
      h("span", { class: "tour-step" }, `Step ${index + 1} of ${STEPS.length}`),
      h("button", { class: "ghost tour-x", "aria-label": "Close the tour", onclick: close }, "Close")),
    h("div", { class: "tour-bar", role: "img", "aria-label": `Progress: step ${index + 1} of ${STEPS.length}` },
      h("i", { style: `width:${((index + 1) / STEPS.length) * 100}%` })),
    heading,
    h("p", {}, step.text),
    h("div", { class: "tour-btns" },
      index > 0 ? h("button", { class: "ghost", onclick: () => show(index - 1) }, "Back") : null,
      nextButton),
  );
  if (location.hash !== step.hash) location.hash = step.hash;
  heading.focus({ preventScroll: true });
}

export const tourAvailable = () => !!state.demo;

export function startTour() {
  if (!tourAvailable()) return;
  index = 0;
  show(0);
}
