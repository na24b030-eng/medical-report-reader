const $ = (id) => document.getElementById(id);
let mode = "text",
  selectedFile = null,
  previewUrl = null,
  lastResult = null,
  busy = false,
  serverConfigured = false;
fetch("/health")
  .then((r) => r.json())
  .then((data) => {
    serverConfigured = data.gemini_configured;
  })
  .catch(() => {
    serverConfigured = false;
  });
$("clear-key").addEventListener("click", () => {
  $("api-key").value = "";
  $("api-key").focus();
});
window.addEventListener("pagehide", () => {
  $("api-key").value = "";
});
function switchTab(next) {
  mode = next;
  for (const tab of ["text", "image"]) {
    const active = tab === mode;
    $(tab + "-tab").classList.toggle("active", active);
    $(tab + "-tab").setAttribute("aria-selected", String(active));
    $(tab + "-tab").tabIndex = active ? 0 : -1;
    $(tab + "-panel").hidden = !active;
  }
  $("error").hidden = true;
}
for (const tab of ["text", "image"]) {
  $(tab + "-tab").addEventListener("click", () => switchTab(tab));
  $(tab + "-tab").addEventListener("keydown", (e) => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      const next =
        e.key === "Home"
          ? "text"
          : e.key === "End"
            ? "image"
            : mode === "text"
              ? "image"
              : "text";
      switchTab(next);
      $(next + "-tab").focus();
    }
  });
}
$("report-text").addEventListener("input", () => {
  $("char-count").textContent =
    `${$("report-text").value.length.toLocaleString()} / 20,000`;
});
function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
}
function chooseFile(file) {
  selectedFile = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  $("image-preview").hidden = true;
  $("file-label").textContent = "Choose a report image";
  if (!file) return;
  if (
    !["image/png", "image/jpeg", "image/webp"].includes(file.type) ||
    file.size > 5 * 1024 * 1024
  ) {
    showError("Choose a PNG, JPEG, or WebP image under 5 MB.");
    $("report-image").value = "";
    return;
  }
  selectedFile = file;
  $("error").hidden = true;
  $("file-label").textContent = file.name;
  previewUrl = URL.createObjectURL(file);
  $("image-preview").src = previewUrl;
  $("image-preview").hidden = false;
}
$("report-image").addEventListener("change", (e) =>
  chooseFile(e.target.files[0]),
);
for (const event of ["dragover", "dragleave", "drop"])
  $("drop-zone").addEventListener(event, (e) => {
    e.preventDefault();
    $("drop-zone").classList.toggle("dragging", event === "dragover");
    if (event === "drop") chooseFile(e.dataTransfer.files[0]);
  });
function setBusy(value) {
  busy = value;
  for (const id of [
    "submit-button",
    "demo-button",
    "text-tab",
    "image-tab",
    "report-text",
    "report-image",
    "api-key",
    "clear-key",
  ])
    $(id).disabled = value;
  $("output-panel").setAttribute("aria-busy", String(value));
  $("loading-state").hidden = !value;
  $("empty-state").hidden = value || !!lastResult;
  $("results").hidden = value || !lastResult;
  if (value) {
    $("error").hidden = true;
    $("result-badge").textContent = "Reading & validating";
  }
}
function element(tag, text, className) {
  const el = document.createElement(tag);
  el.textContent = text;
  if (className) el.className = className;
  return el;
}
function render(data) {
  lastResult = data;
  $("summary").textContent = data.summary;
  $("test-list").replaceChildren();
  for (const test of data.tests) {
    const card = element("article", "", "test-card"),
      top = element("div", "", "test-top");
    top.append(
      element("h3", test.name),
      element("span", test.status, "status " + test.status),
    );
    const value = element("p", test.value.toLocaleString(), "test-value");
    value.append(element("span", test.unit));
    card.append(
      top,
      value,
      element(
        "div",
        test.ref_range
          ? `Report reference: ${test.ref_range.low.toLocaleString()}–${test.ref_range.high.toLocaleString()} ${test.unit}`
          : "Reference range not supplied",
        "test-range",
      ),
      element(
        "p",
        data.explanations.find((e) => e.name === test.name)?.text || "",
      ),
    );
    $("test-list").append(card);
  }
  $("result-note").textContent =
    (data.metadata.mode === "demo"
      ? "Sample demo - fixed example, no Gemini request. "
      : "") +
    (data.metadata.language?.status === "fallback"
      ? data.metadata.language.reason + " "
      : "") +
    data.metadata.note;
  $("source-text").textContent = data.metadata.source_text;
  $("json-output").textContent = JSON.stringify(data, null, 2);
  $("result-badge").textContent =
    data.metadata.mode === "demo"
      ? "Sample demo"
      : data.metadata.language?.provider === "gemini"
        ? "Verified · Gemini wording"
        : "Verified · Standard wording";
}
async function request(url, options) {
  if (busy) return;
  lastResult = null;
  setBusy(true);
  try {
    const response = await fetch(url, {
      ...options,
      signal: AbortSignal.timeout(110000),
    });
    const data = await response.json();
    if (!response.ok)
      throw new Error(data.reason || "Unable to process this report.");
    render(data);
  } catch (error) {
    showError(
      error.name === "TimeoutError"
        ? "This request took too long. Please try again."
        : error.message,
    );
    $("result-badge").textContent = "Needs review";
  } finally {
    setBusy(false);
  }
}
$("report-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const key = $("api-key").value.trim();
  const headers = key ? { "x-gemini-api-key": key } : {};
  if (mode === "text") {
    const text = $("report-text").value.trim();
    if (!text) {
      showError("Paste your test results first, or try the sample report.");
      return;
    }
    request("/reports/simplify/text", {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
  } else {
    if (!selectedFile) {
      showError("Choose a report image first.");
      return;
    }
    const body = new FormData();
    body.append("image", selectedFile);
    request("/reports/simplify/image", { method: "POST", headers, body });
  }
});
$("demo-button").addEventListener("click", async () => {
  switchTab("text");
  await request("/api/demo");
  if (lastResult) {
    $("report-text").value = lastResult.metadata.source_text;
    $("report-text").dispatchEvent(new Event("input"));
  }
});
$("download-button").addEventListener("click", () => {
  if (!lastResult) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(lastResult, null, 2)], {
      type: "application/json",
    }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = "plum-report.json";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
