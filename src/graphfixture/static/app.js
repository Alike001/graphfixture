import { renderEvidence } from "/static/render.js";

const initial = JSON.parse(document.querySelector("#initial-proof").textContent);
const elements = {
  connection: document.querySelector("#connection-status"),
  mode: document.querySelector("#mode-badge"),
  runId: document.querySelector("#run-id"),
  seed: document.querySelector("#run-seed"),
  status: document.querySelector("#run-status"),
  pipeline: document.querySelector("#pipeline"),
  banner: document.querySelector("#result-banner"),
  evidence: document.querySelector("#stage-evidence"),
  digest: document.querySelector("#receipt-digest"),
  footer: document.querySelector("#footer-note"),
  form: document.querySelector("#run-form"),
  button: document.querySelector("#run-button"),
  variant: document.querySelector("#variant"),
  source: document.querySelector("#source"),
  download: document.querySelector("#download-button"),
  toast: document.querySelector("#toast"),
};

let proof = initial;
let selected = "verification";

const stageIcon = (status) => ({ passed: "✓", failed: "×", unavailable: "−", pending: "·" })[status];

function renderPipeline() {
  elements.pipeline.replaceChildren();
  proof.stages.forEach((stage) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `stage ${stage.status}${stage.key === selected ? " selected" : ""}`;
    button.setAttribute("aria-pressed", String(stage.key === selected));
    button.setAttribute("aria-label", `${stage.label}: ${stage.status}`);
    const icon = document.createElement("span");
    icon.className = "stage-icon";
    icon.textContent = stageIcon(stage.status);
    const label = document.createElement("span");
    label.className = "stage-label";
    label.textContent = stage.label;
    button.append(icon, label);
    button.addEventListener("click", () => {
      selected = stage.key;
      render();
    });
    elements.pipeline.append(button);
  });
}

function render() {
  const live = proof.source === "live";
  elements.connection.className = `connection${live ? " live" : ""}`;
  elements.connection.textContent = live ? "DataHub connected" : "DataHub offline";
  elements.mode.className = `mode-badge${live ? " live" : ""}`;
  elements.mode.textContent = live ? "Live context" : "Captured evidence";
  elements.runId.textContent = `GF-${proof.run_id}`;
  elements.seed.textContent = String(proof.seed);
  elements.status.className = `status ${proof.passed ? "pass" : "fail"}`;
  elements.status.textContent = `${proof.passed ? "✓ PASS" : "× FAIL"}`;
  elements.variant.value = proof.variant;
  elements.source.value = proof.source;
  elements.banner.className = `result-banner ${proof.passed ? "pass" : "fail"}`;
  elements.banner.textContent = proof.summary;
  elements.digest.textContent = `Receipt: sha256:${proof.digest}`;
  elements.footer.textContent = live ? "DataHub read-back verified" : "Offline replay available";
  renderPipeline();
  renderEvidence(elements.evidence, proof, selected);
}

function downloadEvidence() {
  const blob = new Blob([`${JSON.stringify(proof.evidence, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `graphfixture-${proof.run_id.toLowerCase()}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  elements.button.disabled = true;
  elements.button.textContent = "Running…";
  elements.toast.hidden = true;
  try {
    const response = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ variant: elements.variant.value, source: elements.source.value, seed: 42 }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail ?? "Verification failed to run");
    proof = result;
    selected = "verification";
    render();
  } catch (error) {
    elements.toast.textContent = error.message;
    elements.toast.hidden = false;
  } finally {
    elements.button.disabled = false;
    elements.button.textContent = "Run verification";
  }
});

elements.download.addEventListener("click", downloadEvidence);
render();
