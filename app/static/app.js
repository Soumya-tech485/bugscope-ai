let editor;
let currentProjectId = null;
let currentSuspect = null;
let currentFilePath = null;
let suspects = [];

require.config({
  paths: {
    vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.45.0/min/vs",
  },
});

require(["vs/editor/editor.main"], function () {
  editor = monaco.editor.create(document.getElementById("editor"), {
    value: "# Upload a project, analyze it, then open a suspect file.",
    language: "python",
    theme: "vs-dark",
    automaticLayout: true,
  });
});

function setStatus(message) {
  document.getElementById("status").textContent = message;
}

async function uploadZip() {
  const input = document.getElementById("zipInput");

  if (!input.files.length) {
    alert("Choose a ZIP file first.");
    return;
  }

  const formData = new FormData();
  formData.append("file", input.files[0]);

  setStatus("Uploading project...");

  const response = await fetch("/api/projects/upload", {
    method: "POST",
    body: formData,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
  }

  currentProjectId = data.project_id;
  document.getElementById("projectLabel").textContent =
    "Project ID: " + currentProjectId;

  setStatus("Project uploaded.");
}

async function analyzeProject() {
  if (!currentProjectId) {
    alert("Upload a project first.");
    return;
  }

  const payload = {
    project_id: currentProjectId,
    bug_report: document.getElementById("bugReport").value,
    error_trace: document.getElementById("errorTrace").value,
    top_n: 8,
  };

  setStatus("Analyzing project...");

  const response = await fetch("/api/projects/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || response.statusText);
  }

  renderSuspects(data.suspects || []);
  setStatus("Analysis complete.");
}

function renderSuspects(list) {
  suspects = list;
  const container = document.getElementById("suspects");
  container.innerHTML = "";

  if (!suspects.length) {
    container.textContent = "No suspects found.";
    return;
  }

  suspects.forEach((suspect, index) => {
    const card = document.createElement("div");
    card.className = "card";

    const title = document.createElement("h3");
    title.textContent = `#${index + 1} ${suspect.name} | score ${suspect.score}`;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = `${suspect.file}:${suspect.start_line}-${suspect.end_line} (${suspect.kind})`;

    card.appendChild(title);
    card.appendChild(meta);

    if (suspect.root_cause) {
      const rootCause = document.createElement("p");
      rootCause.textContent = "Root cause: " + suspect.root_cause;
      card.appendChild(rootCause);
    }

    const reasonList = document.createElement("ul");

    (suspect.reasons || []).forEach((reason) => {
      const item = document.createElement("li");
      item.textContent = reason;
      reasonList.appendChild(item);
    });

    card.appendChild(reasonList);

    const openButton = document.createElement("button");
    openButton.textContent = "Open & Select";
    openButton.onclick = () => {
      currentSuspect = suspect;
      openSuspectFile(suspect);
    };

    card.appendChild(openButton);
    container.appendChild(card);
  });
}

async function openSuspectFile(suspect) {
  if (!currentProjectId) {
    alert("No project selected.");
    return;
  }

  currentFilePath = suspect.file;

  const url =
    `/api/projects/${currentProjectId}/file?path=` +
    encodeURIComponent(suspect.file);

  const response = await fetch(url);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    alert(data.detail || "Could not open file.");
    return;
  }

  editor.setValue(data.content || "");
  monaco.editor.setModelLanguage(editor.getModel(), "python");

  document.getElementById("fileInfo").textContent =
    `Selected: ${suspect.name} in ${suspect.file}:${suspect.start_line}-${suspect.end_line}`;

  setStatus(`Opened ${suspect.file}`);
}

async function autoFix() {
  if (!currentProjectId) {
    alert("Upload and analyze a project first.");
    return;
  }

  if (!currentSuspect) {
    alert("Select a suspect by clicking Open & Select.");
    return;
  }

  const instructions =
    document.getElementById("fixInstructions").value ||
    document.getElementById("bugReport").value ||
    "Fix the root cause.";

  const payload = {
    project_id: currentProjectId,
    suspect_id: currentSuspect.id,
    instructions: instructions,
    apply_fix: true,
  };

  setStatus("Generating and applying AI fix...");

  const response = await fetch("/api/projects/fix", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    setStatus("Fix failed.");
    alert(data.detail || "Fix failed.");
    return;
  }

  alert(
    "Fix applied.\n\nExplanation:\n" +
      (data.explanation || "No explanation returned.") +
      "\n\nValidation:\n" +
      (data.validation || "Unknown")
  );

  await openSuspectFile(currentSuspect);
  setStatus("Fix applied. Re-analyze if needed.");
}

async function saveFile() {
  if (!currentProjectId || !currentFilePath) {
    alert("Open a file first.");
    return;
  }

  const payload = {
    path: currentFilePath,
    content: editor.getValue(),
  };

  setStatus("Saving file...");

  const response = await fetch(`/api/projects/${currentProjectId}/file`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    setStatus("Save failed.");
    alert(data.detail || "Save failed.");
    return;
  }

  if (data.syntax_ok === false) {
    setStatus("Saved with syntax errors.");
    alert("Saved, but syntax error:\n" + data.error);
    return;
  }

  setStatus("File saved.");
}

async function runTests() {
  if (!currentProjectId) {
    alert("Upload a project first.");
    return;
  }

  setStatus("Running tests...");

  const response = await fetch(
    `/api/projects/${currentProjectId}/run-tests`,
    {
      method: "POST",
    }
  );

  const data = await response.json().catch(() => ({}));

  document.getElementById("testOutput").textContent =
    JSON.stringify(data, null, 2);

  setStatus("Tests finished.");
}

document.getElementById("uploadBtn").addEventListener("click", async () => {
  try {
    await uploadZip();
  } catch (error) {
    setStatus("Upload failed: " + error.message);
  }
});

document.getElementById("analyzeBtn").addEventListener("click", async () => {
  try {
    await analyzeProject();
  } catch (error) {
    setStatus("Analysis failed: " + error.message);
  }
});

document.getElementById("fixBtn").addEventListener("click", async () => {
  try {
    await autoFix();
  } catch (error) {
    setStatus("Fix failed: " + error.message);
  }
});

document.getElementById("saveBtn").addEventListener("click", async () => {
  try {
    await saveFile();
  } catch (error) {
    setStatus("Save failed: " + error.message);
  }
});

document.getElementById("testBtn").addEventListener("click", async () => {
  try {
    await runTests();
  } catch (error) {
    setStatus("Test run failed: " + error.message);
  }
});
