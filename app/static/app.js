const form = document.querySelector("#humanizer-form");
const sourceText = document.querySelector("#source-text");
const audience = document.querySelector("#audience");
const tone = document.querySelector("#tone");
const submitButton = document.querySelector("#submit-button");
const resetButton = document.querySelector("#reset-button");
const exampleButton = document.querySelector("#example-button");
const copyButton = document.querySelector("#copy-button");
const characterCount = document.querySelector("#character-count");
const wordCount = document.querySelector("#word-count");
const servicePill = document.querySelector("#service-pill");
const serviceStatus = document.querySelector("#service-status");

const states = {
  empty: document.querySelector("#empty-state"),
  loading: document.querySelector("#loading-state"),
  error: document.querySelector("#error-state"),
  result: document.querySelector("#result-state"),
};

const resultCopy = document.querySelector("#result-copy");
const scoreRing = document.querySelector("#score-ring");
const scoreValue = document.querySelector("#score-value");
const scoreLabel = document.querySelector("#score-label");
const passesValue = document.querySelector("#passes-value");
const modelValue = document.querySelector("#model-value");
const resultWordCount = document.querySelector("#result-word-count");
const errorMessage = document.querySelector("#error-message");
const loadingMessage = document.querySelector("#loading-message");

const loadingMessages = [
  "Reworking structure and phrasing",
  "Checking clarity and sentence rhythm",
  "Reviewing the draft against your voice",
];

const exampleText =
  "Furthermore, it is important to note that the implementation of this innovative solution " +
  "will enable organizations to leverage enhanced efficiencies and drive meaningful outcomes " +
  "across their operational ecosystem.";

let loadingTimer;
let busy = false;
let config = null;
const scenario = document.querySelector("#scenario");
const byId = (id) => document.getElementById(id);

function countWords(value) {
  const trimmed = value.trim();
  return trimmed ? trimmed.split(/\s+/).length : 0;
}

function updateInputCounts() {
  const words = countWords(sourceText.value);
  wordCount.textContent = `${words} ${words === 1 ? "word" : "words"}`;
  characterCount.textContent = `${sourceText.value.length.toLocaleString()} / ${(config?.max_input_chars || 12000).toLocaleString()}`;
}

function showState(name) {
  Object.entries(states).forEach(([key, element]) => {
    element.classList.toggle("is-hidden", key !== name);
  });
}

function setLoading(isLoading) {
  busy = isLoading;
  scenario.disabled = isLoading || !config?.scenarios_enabled;
  submitButton.disabled = isLoading;
  resetButton.disabled = isLoading;
  exampleButton.disabled = isLoading;
  submitButton.querySelector(".button-label").textContent = isLoading
    ? "Humanizing…"
    : "Humanize text";

  window.clearInterval(loadingTimer);
  if (!isLoading) return;

  let messageIndex = 0;
  loadingMessage.textContent = loadingMessages[messageIndex];
  loadingTimer = window.setInterval(() => {
    messageIndex = (messageIndex + 1) % loadingMessages.length;
    loadingMessage.textContent = loadingMessages[messageIndex];
  }, 2600);
}

async function loadConfig() {
  try {
    const response = await fetch("/api/config");
    if (!response.ok) throw new Error("Configuration unavailable");
    config = await response.json();
    byId("config-mode").textContent = `${config.mode === "demo" ? "Rehearsal" : "Live model"} · ${config.environment}`;
    byId("config-model").textContent = config.model;
    byId("config-tracing").textContent = config.tracing.status;
    byId("config-project").textContent = config.tracing.project;
    byId("access-field").classList.toggle("is-hidden", !config.access_token_required);
    scenario.disabled = !config.scenarios_enabled;
    sourceText.maxLength = config.max_input_chars;
    byId("score-kind").textContent = config.mode === "demo" ? "Synthetic demo score" : "Model review score";
    byId("mode-banner").textContent = (config.mode === "demo"
      ? "REHEARSAL MODE · Deterministic edits and synthetic review scores. No LLM calls or token charges."
      : "LIVE MODEL · Real OpenAI calls. Review scores are model opinions, not an AI detector or a guarantee of factual accuracy.")
      + (config.tracing.enabled ? " LangSmith tracing is configured; use fictional classroom text." : " LangSmith tracing is off.")
      + ` The graph stops at ${config.score_threshold}/100 or ${config.max_passes} passes.`;
    updateInputCounts();
  } catch (_error) { byId("mode-banner").textContent = "Unable to load lab configuration. Refresh once the server is running."; }
}

async function checkService() {
  try {
    const response = await fetch("/ready", { headers: { Accept: "application/json" } });
    if (response.ok) {
      servicePill.dataset.state = "ready";
      serviceStatus.textContent = "Ready";
      return;
    }
    servicePill.dataset.state = "warning";
    serviceStatus.textContent = "API key needed";
  } catch (_error) {
    servicePill.dataset.state = "warning";
    serviceStatus.textContent = "Service unavailable";
  }
}

function renderResult(data) {
  const roundedScore = Math.round(data.score);
  resultCopy.textContent = data.text;
  scoreValue.textContent = roundedScore;
  scoreRing.style.setProperty("--score-angle", `${Math.min(roundedScore, 100) * 3.6}deg`);
  scoreLabel.textContent = roundedScore >= 90 ? "Natural" : roundedScore >= 80 ? "Polished" : "Refined";
  passesValue.textContent = data.passes;
  modelValue.textContent = data.model;
  modelValue.title = data.model;
  resultWordCount.textContent = countWords(data.text);
  copyButton.disabled = false;
  showState("result");
}

async function humanize(event) {
  event.preventDefault();
  if (busy) return;
  const text = sourceText.value.trim();
  if (!text) {
    sourceText.focus();
    return;
  }

  setLoading(true);
  copyButton.disabled = true;
  showState("loading");
  resetTelemetry("Running…");

  try {
    const response = await fetch("/humanize", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json",
        "X-Class-Token": byId("access-token").value },
      body: JSON.stringify({
        text,
        audience: audience.value.trim() || "general readers",
        tone: tone.value,
        scenario: scenario.value,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      if (data.detail?.request_id) renderTelemetry(data.detail);
      const message = typeof data.detail === "string" ? data.detail : data.detail?.message;
      throw new Error(message || (response.status === 422 ? "Check your text length and writing preferences." : "The request could not be completed."));
    }
    renderResult(data);
    renderTelemetry(data);
  } catch (error) {
    errorMessage.textContent = error.message || "Check your connection and try again.";
    showState("error");
    if (byId("metric-trace").textContent === "Running…") resetTelemetry("Request failed");
  } finally {
    setLoading(false);
  }
}

async function copyResult() {
  if (!resultCopy.textContent) return;
  try {
    await navigator.clipboard.writeText(resultCopy.textContent);
    copyButton.querySelector("span").textContent = "Copied";
    window.setTimeout(() => {
      copyButton.querySelector("span").textContent = "Copy";
    }, 1600);
  } catch (_error) {
    copyButton.querySelector("span").textContent = "Select text to copy";
  }
}

function resetWorkspace() {
  form.reset();
  resetTelemetry();
  sourceText.value = "";
  audience.value = "general readers";
  resultCopy.textContent = "";
  copyButton.disabled = true;
  updateInputCounts();
  showState("empty");
  sourceText.focus();
}

sourceText.addEventListener("input", updateInputCounts);
sourceText.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
    form.requestSubmit();
  }
});
form.addEventListener("submit", humanize);
resetButton.addEventListener("click", resetWorkspace);
copyButton.addEventListener("click", copyResult);
exampleButton.addEventListener("click", () => {
  sourceText.value = exampleText;
  updateInputCounts();
  sourceText.focus();
});

updateInputCounts();
checkService();
loadConfig();

function resetTelemetry(status = "Awaiting a run") {
  ["metric-latency", "metric-calls", "metric-tokens"].forEach(id => byId(id).textContent = "—");
  byId("metric-trace").textContent = status;
  byId("request-id").textContent = "—";
  byId("run-timeline").replaceChildren();
  byId("trace-link").classList.add("is-hidden");
  byId("trace-link").removeAttribute("href");
  byId("telemetry-note").textContent = "Open LangSmith for the full nested trace. Delivery is verified in LangSmith, not by a local success response.";
}

function renderTelemetry(data) {
  byId("metric-latency").textContent = `${(data.duration_ms / 1000).toFixed(2)} s`;
  byId("metric-calls").textContent = data.usage ? data.usage.llm_calls : (data.mode === "demo" ? "0 · rehearsal" : "—");
  byId("metric-tokens").textContent = data.usage ? `${data.usage.input_tokens} / ${data.usage.output_tokens}` : "Not measured";
  byId("metric-trace").textContent = data.trace?.status || "off";
  byId("request-id").textContent = data.request_id;
  const link = byId("trace-link");
  try {
    const url = new URL(data.trace?.url);
    if (url.protocol === "https:" && (url.hostname === "smith.langchain.com" || url.hostname.endsWith(".smith.langchain.com"))) {
      link.href = url.href;
      link.classList.remove("is-hidden");
    }
  } catch (_) { /* No authenticated trace URL is available. */ }
  byId("run-timeline").replaceChildren();
  for (const step of data.steps || []) {
    const card = document.createElement("div"); card.className = "run-step";
    const label = document.createElement("strong"); label.textContent = `${step.name} · pass ${step.pass}`;
    const detail = document.createElement("span");
    detail.textContent = `${step.duration_ms.toFixed(0)} ms${step.score !== undefined ? ` · score ${step.score}` : ""}`;
    card.append(label, detail); byId("run-timeline").append(card);
  }
  byId("telemetry-note").textContent = data.mode === "demo"
    ? "Timings are measured. Demo scores are synthetic; token usage and cost are not fabricated. LangSmith ingestion is asynchronous—refresh its project to verify delivery."
    : "Tokens come from provider usage. Inspect the LLM child runs in LangSmith for prompts, responses, and supported model cost estimates. Queued does not prove delivery.";
}
