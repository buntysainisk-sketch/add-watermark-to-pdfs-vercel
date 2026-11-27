const form = document.querySelector("#watermark-form");
const input = document.querySelector("#pdf-input");
const dropZone = document.querySelector("#drop-zone");
const fileSummary = document.querySelector("#file-summary");
const fileName = document.querySelector("#file-name");
const fileSize = document.querySelector("#file-size");
const removeFile = document.querySelector("#remove-file");
const processButton = document.querySelector("#process-button");
const processLabel = document.querySelector("#process-label");
const spinner = document.querySelector(".spinner");
const alertBox = document.querySelector("#alert");
const resultSection = document.querySelector("#result-section");
const viewer = document.querySelector("#pdf-viewer");
const downloadButton = document.querySelector("#download-button");
const newFileButton = document.querySelector("#new-file-button");
const intro = document.querySelector(".intro");
const headerActions = document.querySelector("#header-actions");
const adjustButton = document.querySelector("#adjust-button");
const adjustInput = document.querySelector("#adjust");
const editableSettings = document.querySelector("#editable-settings");
const editableInputs = [...editableSettings.querySelectorAll("input")];

adjustButton.addEventListener("click", () => {
  const isAdjusting = editableInputs[0].disabled;
  editableInputs.forEach(input => { input.disabled = !isAdjusting; });
  adjustInput.value = isAdjusting ? "true" : "false";
  adjustButton.textContent = isAdjusting ? "Use fixed settings" : "Adjust watermark";
});

function showError(message) {
  alertBox.textContent = message;
  alertBox.hidden = false;
  alertBox.scrollIntoView({ behavior: "smooth", block: "center" });
}

function clearError() {
  alertBox.hidden = true;
  alertBox.textContent = "";
}

function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function setFile(file) {
  clearError();
  if (!file) return;
  if (file.type !== "application/pdf" && !file.name.toLowerCase().endsWith(".pdf")) {
    showError("Only PDF files are accepted.");
    return;
  }
  if (file.size > 50 * 1024 * 1024) {
    showError("This file is larger than 50 MB. Please choose a smaller PDF.");
    return;
  }
  const transfer = new DataTransfer();
  transfer.items.add(file);
  input.files = transfer.files;
  fileName.textContent = file.name;
  fileSize.textContent = formatBytes(file.size);
  fileSummary.classList.add("visible");
  processButton.disabled = false;
}

function resetForm() {
  form.reset();
  input.value = "";
  dropZone.hidden = false;
  fileSummary.classList.remove("visible");
  processButton.disabled = true;
  resultSection.hidden = true;
  viewer.src = "";
  document.body.classList.remove("preview-mode");
  headerActions.hidden = true;
  intro.hidden = false;
  form.hidden = false;
  editableInputs.forEach(input => { input.disabled = true; });
  editableInputs.forEach(input => { input.disabled = true; });
  adjustInput.value = "false";
  adjustButton.textContent = "Adjust watermark";
  clearError();
}

input.addEventListener("change", () => setFile(input.files[0]));
removeFile.addEventListener("click", resetForm);
newFileButton.addEventListener("click", () => {
  resetForm();
  window.scrollTo({ top: 0, behavior: "smooth" });
});
["dragenter", "dragover"].forEach(eventName => dropZone.addEventListener(eventName, event => {
  event.preventDefault();
  dropZone.classList.add("dragging");
}));
["dragleave", "drop"].forEach(eventName => dropZone.addEventListener(eventName, event => {
  event.preventDefault();
  dropZone.classList.remove("dragging");
}));
dropZone.addEventListener("drop", event => setFile(event.dataTransfer.files[0]));

form.addEventListener("submit", async event => {
  event.preventDefault();
  clearError();
  if (!input.files[0]) return showError("Please choose a PDF before processing.");
  processButton.disabled = true;
  spinner.hidden = false;
  processLabel.textContent = "Applying Taxmann Watermark...";
  try {
    const formData = new FormData(form);
    formData.set("opacity", Number(formData.get("opacity")) / 100);
    const response = await fetch("/api/process", { method: "POST", body: formData });
    if (!response.ok) {
      const errorPayload = await response.json();
      throw new Error(errorPayload.error || "Unable to process the PDF.");
    }
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/pdf")) {
      const pdfBlob = await response.blob();
      const pdfUrl = URL.createObjectURL(pdfBlob);
      const contentDisposition = response.headers.get("content-disposition") || "";
      const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
      const filename = filenameMatch ? filenameMatch[1] : "watermarked.pdf";
      viewer.src = `${pdfUrl}#zoom=50&toolbar=1&navpanes=0`;
      downloadButton.href = pdfUrl;
      downloadButton.download = filename;
      document.body.classList.add("preview-mode");
      headerActions.hidden = false;
      intro.hidden = true;
      form.hidden = true;
      resultSection.hidden = false;
      return;
    }
    const payload = await response.json();
    const previewUrl = `${payload.preview_url}#zoom=50&toolbar=1&navpanes=0`;
    viewer.src = previewUrl;
    downloadButton.href = payload.download_url;
    document.body.classList.add("preview-mode");
    headerActions.hidden = false;
    intro.hidden = true;
    form.hidden = true;
    resultSection.hidden = false;
  } catch (error) {
    showError(error.message);
  } finally {
    processButton.disabled = false;
    spinner.hidden = true;
    processLabel.textContent = "Process PDF";
  }
});
