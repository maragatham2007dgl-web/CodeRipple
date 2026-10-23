const zipInput = document.getElementById("zipFile");
const analyseBtn = document.getElementById("analyseBtn");
const fileLabel = document.getElementById("fileLabel");
const uploadMessage = document.getElementById("uploadMessage");
const workspace = document.getElementById("workspace");
const changedFile = document.getElementById("changedFile");
const impactBtn = document.getElementById("impactBtn");
let projectId = null;
let graphEdges = [];

zipInput.addEventListener("change", () => {
  const file = zipInput.files[0];
  fileLabel.textContent = file ? file.name : "Choose your project ZIP";
  analyseBtn.disabled = !file;
  setMessage("", false);
});

analyseBtn.addEventListener("click", async () => {
  const file = zipInput.files[0];
  if (!file) return;
  analyseBtn.disabled = true;
  analyseBtn.textContent = "Analysing…";
  setMessage("Uploading and analysing Python files. Please wait.", false);
  try {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch("/api/analyse", { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Analysis failed.");
    showAnalysis(result);
    setMessage("Analysis completed successfully.", false);
    workspace.classList.remove("hidden");
    document.getElementById("impactCount").textContent = "—";
    document.getElementById("emptyState").classList.remove("hidden");
    document.getElementById("resultsArea").classList.add("hidden");
    document.getElementById("reportBadge").textContent = "Waiting for selection";
    workspace.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    setMessage(error.message || "Could not analyse this ZIP.", true);
  } finally {
    analyseBtn.disabled = !zipInput.files[0];
    analyseBtn.innerHTML = 'Analyse codebase <span>→</span>';
  }
});

function showAnalysis(result) {
  projectId = result.project_id;
  graphEdges = result.edges || [];
  document.getElementById("fileCount").textContent = result.file_count;
  document.getElementById("edgeCount").textContent = result.edge_count;
  changedFile.innerHTML = "";
  result.files.forEach(file => {
    const option = document.createElement("option");
    option.value = file.id;
    option.textContent = file.id;
    changedFile.appendChild(option);
  });
  renderGraph(result.files, graphEdges);
}

impactBtn.addEventListener("click", async () => {
  if (!projectId || !changedFile.value) return;
  impactBtn.disabled = true;
  impactBtn.textContent = "Checking…";
  try {
    const data = new FormData();
    data.append("project_id", projectId);
    data.append("changed_file", changedFile.value);
    const response = await fetch("/api/impact", { method: "POST", body: data });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Impact analysis failed.");
    renderImpact(result);
  } catch (error) {
    setMessage(error.message || "Could not calculate impact.", true);
  } finally {
    impactBtn.disabled = false;
    impactBtn.textContent = "Find impact →";
  }
});

function renderImpact(report) {
  document.getElementById("emptyState").classList.add("hidden");
  document.getElementById("resultsArea").classList.remove("hidden");
  document.getElementById("selectedName").textContent = report.changed_file;
  document.getElementById("impactCount").textContent = report.impact_count;
  document.getElementById("reportBadge").textContent = report.impact_count
    ? `${report.impact_count} possible impact${report.impact_count === 1 ? "" : "s"}`
    : "No linked files found";
  const list = document.getElementById("resultsList");
  list.innerHTML = "";
  if (!report.results.length) {
    const item = document.createElement("div");
    item.className = "result-item";
    item.textContent = "No other files were linked to this file by the current static analysis.";
    list.appendChild(item);
  }
  report.results.forEach(result => {
    const item = document.createElement("article");
    item.className = "result-item";
    const head = document.createElement("div");
    head.className = "result-head";
    const filename = document.createElement("strong");
    filename.className = "filename";
    filename.textContent = result.file;
    const risk = document.createElement("span");
    risk.className = `risk ${result.risk.toLowerCase()}`;
    risk.textContent = `${result.risk} · ${result.distance} STEP${result.distance === 1 ? "" : "S"}`;
    head.append(filename, risk);
    item.appendChild(head);
    const detail = document.createElement("p");
    const reasons = (result.reasons || []).map(r => `${r.from}: ${r.reason} (${r.evidence || "relationship"})`);
    detail.textContent = reasons.length ? reasons.join(" | ") : "Connected through the dependency graph.";
    item.appendChild(detail);
    if (result.functions && result.functions.length) {
      const functions = document.createElement("p");
      functions.textContent = `Detected definitions: ${result.functions.join(", ")}`;
      item.appendChild(functions);
    }
    list.appendChild(item);
  });
  document.getElementById("reportNote").textContent = report.note;
}

function renderGraph(files, edges) {
  const view = document.getElementById("graphView");
  view.innerHTML = "";
  if (!edges.length) {
    const note = document.createElement("p");
    note.className = "muted small";
    note.textContent = "No cross-file dependencies detected yet. Try the included sample project.";
    view.appendChild(note);
    return;
  }
  edges.slice(0, 80).forEach(edge => {
    const source = document.createElement("span");
    source.className = "graph-node";
    source.textContent = edge.source;
    source.title = edge.reason;
    const arrow = document.createElement("span");
    arrow.className = "graph-arrow";
    arrow.textContent = "→";
    arrow.title = `${edge.reason}: ${edge.evidence}`;
    const target = document.createElement("span");
    target.className = "graph-node";
    target.textContent = edge.target;
    target.title = edge.reason;
    view.append(source, arrow, target);
  });
  if (edges.length > 80) {
    const note = document.createElement("p");
    note.className = "muted small";
    note.textContent = `Showing first 80 of ${edges.length} dependency edges.`;
    view.appendChild(note);
  }
}

function setMessage(message, isError) {
  uploadMessage.textContent = message;
  uploadMessage.classList.toggle("error", isError);
}

// Sample ZIP is built on demand from the included sample files by the backend route below.
document.getElementById("sampleLink").addEventListener("click", async event => {
  event.preventDefault();
  try {
    const response = await fetch("/api/sample");
    if (!response.ok) throw new Error("Could not load sample project.");
    const blob = await response.blob();
    const file = new File([blob], "coderipple_sample.zip", { type: "application/zip" });
    const transfer = new DataTransfer();
    transfer.items.add(file);
    zipInput.files = transfer.files;
    fileLabel.textContent = file.name;
    analyseBtn.disabled = false;
    setMessage("Sample project loaded. Click Analyse codebase.", false);
  } catch (error) {
    setMessage(error.message, true);
  }
});
