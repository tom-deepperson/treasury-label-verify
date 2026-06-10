function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

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

function setVerifyStatus(message, kind = "info") {
  const el = document.getElementById("verify-status");
  if (!el) return;
  el.className = `verify-status verify-status-${kind}`;
  el.innerHTML = message;
}

function setVerifyLoading(isLoading) {
  const button = document.getElementById("verify-submit");
  if (button) {
    button.disabled = isLoading;
    button.textContent = isLoading ? "VERIFYING… PLEASE WAIT" : "VERIFY LABEL";
  }
}

function showImagePreview(url) {
  const wrap = document.getElementById("image-preview");
  const img = document.getElementById("image-preview-img");
  if (!wrap || !img) return;
  if (!url) {
    wrap.hidden = true;
    img.removeAttribute("src");
    return;
  }
  img.src = url;
  wrap.hidden = false;
}

function verdictBanner(status) {
  if (status === "PASS") {
    return `<div class="verdict verdict-pass" role="status">
      <span class="verdict-icon" aria-hidden="true">✓</span>
      <div>
        <strong>ALL CHECKS PASSED</strong>
        <p>Every field on the label matches the application.</p>
      </div>
    </div>`;
  }
  if (status === "FAIL") {
    return `<div class="verdict verdict-fail" role="status">
      <span class="verdict-icon" aria-hidden="true">✗</span>
      <div>
        <strong>ISSUES FOUND</strong>
        <p>One or more fields do not match. Red rows below show what failed.</p>
      </div>
    </div>`;
  }
  return `<div class="verdict verdict-review" role="status">
    <span class="verdict-icon" aria-hidden="true">!</span>
    <div>
      <strong>NEEDS MANUAL REVIEW</strong>
      <p>Some fields could not be read clearly. Check the comparison below.</p>
    </div>
  </div>`;
}

function isDeveloperView() {
  const el = document.getElementById("usage-count");
  return el?.dataset.role === "developer";
}

function rotationNoteHtml(rotation) {
  if (
    rotation.was_upright !== false &&
    !rotation.skew_correction_deg &&
    !rotation.detected_rotation_deg &&
    !rotation.brand_inverted &&
    !rotation.per_sticker
  ) {
    return "";
  }
  if (rotation.note) {
    return `<p class="review-plain">${escapeHtml(rotation.note)}</p>`;
  }
  if (rotation.per_sticker) {
    const brandPart =
      rotation.brand_rotation_deg === 0 ? "upright" : `rotated ${rotation.brand_rotation_deg}°`;
    const warningPart =
      rotation.warning_rotation_deg === 0 ? "upright" : `rotated ${rotation.warning_rotation_deg}°`;
    return `<p class="review-plain">Brand sticker ${brandPart}; government warning strip ${warningPart}. Each sticker was read with its own orientation correction.</p>`;
  }
  if (rotation.brand_inverted) {
    return `<p class="review-plain">Brand sticker is upside down while the government warning strip is upright. Each sticker was corrected independently before reading.</p>`;
  }
  if (rotation.was_upright === false || rotation.skew_correction_deg || rotation.detected_rotation_deg) {
    return `<p class="review-plain">This label was photographed at an angle. Text was adjusted before reading.</p>`;
  }
  return "";
}

function rotationMetaHtml(rotation) {
  const parts = [];
  if (rotation.per_sticker) {
    parts.push(`Brand sticker: ${rotation.brand_rotation_deg || 0}°`);
    parts.push(`Warning strip: ${rotation.warning_rotation_deg || 0}°`);
    parts.push("Per-sticker correction");
  } else {
    if (rotation.detected_rotation_deg) {
      parts.push(`Turned ${rotation.detected_rotation_deg}°`);
    }
    if (rotation.skew_correction_deg) {
      const skew = rotation.skew_correction_deg;
      const direction = skew > 0 ? "clockwise" : "counter-clockwise";
      parts.push(`Straightened ${Math.abs(skew)}° ${direction}`);
    }
    if (rotation.brand_inverted) {
      parts.push("Brand sticker inverted");
    }
    if (!parts.length) {
      parts.push("No image rotation");
    }
  }
  parts.push(`Upright: ${rotation.was_upright ? "Yes" : "No"}`);
  return parts.join(" · ");
}

function failedFieldNames(fields) {
  return (fields || []).filter((f) => f.status === "FAIL").map((f) => f.field_name);
}

function reviewFieldNames(fields) {
  return (fields || []).filter((f) => f.status === "REVIEW").map((f) => f.field_name);
}

function overallSummaryHtml(result, developer) {
  const rotation = result.rotation || {};
  const status = result.overall_status;
  const failed = failedFieldNames(result.fields);
  const review = reviewFieldNames(result.fields);

  let html = `<p class="result-meta ${statusClass(status)}">Overall${developer ? "" : " result"}: <strong>${escapeHtml(status)}</strong></p>`;

  if (failed.length) {
    html += `<p class="result-issue-list fail">Failed: ${failed.map((name) => escapeHtml(name)).join(", ")}</p>`;
  }
  if (review.length && status !== "PASS") {
    html += `<p class="result-issue-list review">Needs review: ${review.map((name) => escapeHtml(name)).join(", ")}</p>`;
  }

  if (developer) {
    html += `<p class="result-meta-secondary">${rotationMetaHtml(rotation)}</p>`;
    if (rotation.note) {
      html += `<p class="review">${escapeHtml(rotation.note)}</p>`;
    }
  } else {
    html += rotationNoteHtml(rotation);
  }

  return html;
}

function debugPanelHtml(result, ocrText) {
  const rotation = result.rotation || {};
  const logLines = (result.log_lines || []).join("\n");
  return `<details class="debug-panel">
    <summary>Debug (developer)</summary>
    <div class="compare-layout debug-compare">
      <div class="compare-pane">
        <h3>Raw OCR text</h3>
        <pre class="ocr-text">${escapeHtml(ocrText)}</pre>
      </div>
      <div class="compare-pane">
        <h3>Pipeline log</h3>
        <pre class="ocr-text">${escapeHtml(logLines || "(no log)")}</pre>
      </div>
    </div>
    <p class="debug-meta">${rotationMetaHtml(rotation)} · Model: ${escapeHtml(result.llm_model || "—")}</p>
  </details>`;
}

function renderResult(result, imageUrl) {
  const container = document.getElementById("results");
  if (!container) return;

  const developer = isDeveloperView();
  const ocrText = result.ocr_text || result.ocr_text_preview || "(no text detected)";
  const imageBlock = imageUrl
    ? `<img src="${escapeHtml(imageUrl)}" alt="Uploaded label image">`
    : `<p class="muted">Image preview not available for this result.</p>`;

  let rows = "";
  for (const field of result.fields || []) {
    const rowClass = field.status === "FAIL" ? "row-fail" : field.status === "PASS" ? "row-pass" : "row-review";
    rows += `<tr class="${rowClass}">
      <td>${escapeHtml(field.field_name)}</td>
      <td>${escapeHtml(field.application_value)}</td>
      <td class="${statusClass(field.status)}">${escapeHtml(field.extracted_value || "—")}</td>
      <td class="${statusClass(field.status)}"><strong>${escapeHtml(field.status)}</strong></td>
      <td>${escapeHtml(field.notes || "")}</td>
    </tr>`;
  }

  const imageSection = developer
    ? `<div class="compare-layout">
        <div class="compare-pane">
          <h3>Original label</h3>
          <div class="label-frame">${imageBlock}</div>
        </div>
        <div class="compare-pane">
          <h3>Text read from label (OCR)</h3>
          <pre class="ocr-text">${escapeHtml(ocrText)}</pre>
        </div>
      </div>`
    : `<div class="label-only">
        <h3 class="fields-heading">Label submitted</h3>
        <div class="label-frame label-frame-large">${imageBlock}</div>
      </div>`;

  const metaLine = overallSummaryHtml(result, developer);

  const html = `<div class="panel result-panel">
    ${verdictBanner(result.overall_status)}
    <h2 class="result-title">${escapeHtml(result.filename)}</h2>
    ${metaLine}
    ${imageSection}
    <h3 class="fields-heading">Field comparison</h3>
    <table class="fields-table">
      <thead>
        <tr>
          <th>Field</th>
          <th>Application</th>
          <th>Read from label</th>
          <th>Result</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>
    ${developer ? debugPanelHtml(result, ocrText) : ""}
  </div>`;

  container.innerHTML = html + container.innerHTML;
  const panel = container.firstElementChild;
  if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
}

function findBatchImageUrl(filename) {
  const input = document.getElementById("batch_images");
  if (!input || !input.files) return null;
  for (const file of input.files) {
    if (file.name === filename) return URL.createObjectURL(file);
  }
  return null;
}

async function readResponsePayload(resp) {
  const raw = await resp.text();
  if (!raw) return {};
  try {
    return JSON.parse(raw);
  } catch {
    const snippet = raw.replace(/\s+/g, " ").trim().slice(0, 180);
    throw new Error(`Server returned ${resp.status} ${resp.statusText}${snippet ? `: ${snippet}` : ""}`);
  }
}

async function runVerify(event) {
  event.preventDefault();
  const form = document.getElementById("verify-form");
  const imageInput = document.getElementById("image");
  if (!form || !imageInput?.files?.length) {
    setVerifyStatus("<strong>Please choose a label image before verifying.</strong>", "error");
    return;
  }

  const previewUrl = URL.createObjectURL(imageInput.files[0]);
  const startedAt = Date.now();
  let timerId = null;
  setVerifyLoading(true);
  setVerifyStatus(
    `<strong>Verifying label…</strong> Reading the image and comparing fields. On the hosted demo this often takes 45–90 seconds.`,
    "loading"
  );
  timerId = window.setInterval(() => {
    const elapsed = Math.floor((Date.now() - startedAt) / 1000);
    setVerifyStatus(
      `<strong>Verifying label…</strong> Still working (${elapsed}s elapsed). OCR and model extraction can take up to about 90 seconds on the hosted demo.`,
      "loading"
    );
  }, 5000);

  try {
    const data = new FormData(form);
    const resp = await fetch("/api/verify", { method: "POST", body: data });
    const payload = await readResponsePayload(resp);

    if (!resp.ok) {
      setVerifyStatus(`<strong>Verification failed:</strong> ${escapeHtml(payload.detail || resp.statusText)}`, "error");
      return;
    }

    renderResult(payload, previewUrl);
    if (payload.overall_status === "PASS") {
      setVerifyStatus("<strong>Done.</strong> All checks passed — see the green result below.", "success");
    } else if (payload.overall_status === "FAIL") {
      setVerifyStatus("<strong>Done.</strong> Issues found — see red highlighted rows below.", "error");
    } else {
      setVerifyStatus("<strong>Done.</strong> Manual review recommended — see results below.", "review");
    }
    refreshUsage();
  } catch (err) {
    setVerifyStatus(`<strong>Could not verify:</strong> ${escapeHtml(err.message || "Network error")}`, "error");
  } finally {
    if (timerId !== null) window.clearInterval(timerId);
    setVerifyLoading(false);
  }
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
    const payload = await readResponsePayload(resp);
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
      if (payload.type === "result") {
        renderResult(payload.result, findBatchImageUrl(payload.result.filename));
      }
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

let sampleApplications = [];

async function loadSampleApplications(options = {}) {
  const { log = true } = options;
  const resp = await fetch("/samples/applications.json");
  if (!resp.ok) return;
  const apps = await resp.json();
  sampleApplications = apps;
  const cleaned = apps.map(({ sample_file, ...rest }) => rest);
  document.getElementById("applications_json").value = JSON.stringify(cleaned, null, 2);
  populateSampleSelect(apps);
  if (log) {
    const names = apps.map((a) => a.sample_file).filter(Boolean).join(", ");
    appendLog(`> loaded ${cleaned.length} application(s) from samples/applications.json`);
    appendLog(`> upload ${cleaned.length} image(s) in this order: ${names || "same order as JSON array"}`);
  }
}

function populateSampleSelect(apps) {
  const select = document.getElementById("sample-select");
  if (!select) return;
  select.innerHTML = '<option value="">— choose a sample —</option>';
  apps.forEach((app, index) => {
    const option = document.createElement("option");
    option.value = String(index);
    option.textContent = app.sample_file || `Sample ${index + 1}`;
    select.appendChild(option);
  });
}

async function loadSampleIntoSingleForm() {
  const select = document.getElementById("sample-select");
  if (!select || select.value === "") {
    setVerifyStatus("<strong>Choose a sample from the list first.</strong>", "error");
    return;
  }
  if (!sampleApplications.length) {
    await loadSampleApplications();
  }
  const index = Number(select.value);
  const app = sampleApplications[index];
  if (!app) return;

  document.getElementById("brand_name").value = app.brand_name;
  document.getElementById("class_type").value = app.class_type;
  document.getElementById("alcohol_content").value = app.alcohol_content;
  document.getElementById("net_contents").value = app.net_contents;
  document.getElementById("government_warning").value = app.government_warning;

  if (app.sample_file) {
    const imgResp = await fetch(`/samples/labels/${encodeURIComponent(app.sample_file)}`);
    if (!imgResp.ok) {
      setVerifyStatus("<strong>Sample image not found.</strong> Run scripts/generate_samples.py first.", "error");
      return;
    }
    const blob = await imgResp.blob();
    const file = new File([blob], app.sample_file, { type: blob.type || "image/png" });
    const dt = new DataTransfer();
    dt.items.add(file);
    document.getElementById("image").files = dt.files;
    showImagePreview(URL.createObjectURL(blob));
  }

  setVerifyStatus(`<strong>Loaded sample:</strong> ${escapeHtml(app.sample_file || `Sample ${index + 1}`)}. Click VERIFY LABEL when ready.`, "info");
}

document.addEventListener("DOMContentLoaded", () => {
  const verifyForm = document.getElementById("verify-form");
  const batchForm = document.getElementById("batch-form");
  const loadSamples = document.getElementById("load-samples");
  const loadSampleSingle = document.getElementById("load-sample-single");
  const imageInput = document.getElementById("image");

  if (verifyForm) verifyForm.addEventListener("submit", runVerify);
  if (batchForm) batchForm.addEventListener("submit", runBatch);
  if (loadSamples) loadSamples.addEventListener("click", () => loadSampleApplications({ log: true }));
  if (loadSampleSingle) loadSampleSingle.addEventListener("click", loadSampleIntoSingleForm);
  if (imageInput) {
    imageInput.addEventListener("change", () => {
      const file = imageInput.files?.[0];
      showImagePreview(file ? URL.createObjectURL(file) : null);
    });
  }

  loadSampleApplications({ log: false });
  refreshUsage();
});
