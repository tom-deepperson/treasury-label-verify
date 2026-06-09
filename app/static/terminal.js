function statusClass(status) {
  if (status === "PASS") return "pass";
  if (status === "FAIL") return "fail";
  return "review";
}

function appendLog(message) {
  const log = document.getElementById("batch-log");
  if (!log) return;
  log.textContent += message + "\n";
  log.scrollTop = log.scrollHeight;
}

function renderResult(result) {
  const container = document.getElementById("results");
  const rotation = result.rotation || {};
  let html = `<div class="panel"><h2>RESULT: ${result.filename} [${result.overall_status}]</h2>`;
  html += `<p class="${statusClass(result.overall_status)}">Rotation: ${rotation.detected_rotation_deg} deg | Upright: ${rotation.was_upright ? "YES" : "NO"}</p>`;
  if (rotation.note) html += `<p class="review">${rotation.note}</p>`;
  if (result.log_lines) {
    html += `<div class="log">${result.log_lines.join("\n")}</div>`;
  }
  html += `<table><thead><tr><th>Field</th><th>Application</th><th>Extracted</th><th>Status</th><th>Notes</th></tr></thead><tbody>`;
  for (const field of result.fields || []) {
    html += `<tr><td>${field.field_name}</td><td>${field.application_value}</td><td>${field.extracted_value}</td><td class="${statusClass(field.status)}">[${field.status}]</td><td>${field.notes || ""}</td></tr>`;
  }
  html += "</tbody></table></div>";
  container.innerHTML = html + container.innerHTML;
}

async function runVerify(event) {
  event.preventDefault();
  const form = document.getElementById("verify-form");
  const data = new FormData(form);
  appendLog("> RUN VERIFY...");
  const resp = await fetch("/api/verify", { method: "POST", body: data });
  const payload = await resp.json();
  if (!resp.ok) {
    appendLog(`> ERROR: ${payload.detail || resp.statusText}`);
    return;
  }
  renderResult(payload);
  refreshUsage();
}

async function runBatch(event) {
  event.preventDefault();
  const form = document.getElementById("batch-form");
  const imageInput = document.getElementById("batch_images");
  const appsField = document.getElementById("applications_json");
  let apps = [];
  try {
    apps = JSON.parse(appsField.value || "[]");
    if (!Array.isArray(apps)) throw new Error("applications_json must be a JSON array");
  } catch (err) {
    appendLog(`> ERROR: invalid applications JSON (${err.message})`);
    return;
  }
  const imageCount = imageInput.files ? imageInput.files.length : 0;
  if (imageCount === 0) {
    appendLog("> ERROR: select at least one label image");
    return;
  }
  if (apps.length === 0) {
    appendLog("> ERROR: click LOAD SAMPLE JSON or paste one application object per image");
    return;
  }
  if (imageCount !== apps.length) {
    appendLog(
      `> ERROR: ${imageCount} image(s) selected but ${apps.length} application record(s). Counts must match.`
    );
    return;
  }
  const data = new FormData(form);
  appendLog(`> BATCH START (${imageCount} label(s), sequential)...`);
  const resp = await fetch("/api/batch/stream", { method: "POST", body: data });
  if (!resp.ok) {
    const payload = await resp.json();
    appendLog(`> ERROR: ${payload.detail || resp.statusText}`);
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() || "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.type === "log") appendLog(payload.message);
      if (payload.type === "result") renderResult(payload.result);
      if (payload.type === "done") refreshUsage();
    }
  }
  appendLog("> BATCH COMPLETE");
}

async function refreshUsage() {
  const resp = await fetch("/api/usage");
  if (!resp.ok) return;
  const usage = await resp.json();
  const el = document.getElementById("usage-count");
  if (!el) return;
  if (usage.max_tests <= 0) {
    const role = el.dataset.role || "";
    el.textContent =
      role === "developer" ? "TESTS: unlimited (developer)" : "TESTS: unlimited (local)";
  } else {
    el.textContent = `TESTS: ${usage.used}/${usage.max_tests}`;
  }
}

async function loadSampleApplications() {
  const resp = await fetch("/samples/applications.json");
  if (!resp.ok) return;
  const apps = await resp.json();
  const cleaned = apps.map(({ sample_file, ...rest }) => rest);
  document.getElementById("applications_json").value = JSON.stringify(cleaned, null, 2);
  const names = apps.map((a) => a.sample_file).filter(Boolean).join(", ");
  appendLog(`> loaded ${cleaned.length} application(s) from samples/applications.json`);
  appendLog(`> upload ${cleaned.length} image(s) in this order: ${names || "same order as JSON array"}`);
}

document.addEventListener("DOMContentLoaded", () => {
  const verifyForm = document.getElementById("verify-form");
  const batchForm = document.getElementById("batch-form");
  const loadSamples = document.getElementById("load-samples");
  if (verifyForm) verifyForm.addEventListener("submit", runVerify);
  if (batchForm) batchForm.addEventListener("submit", runBatch);
  if (loadSamples) loadSamples.addEventListener("click", loadSampleApplications);
  refreshUsage();
});
