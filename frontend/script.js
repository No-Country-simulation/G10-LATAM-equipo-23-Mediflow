"use strict";

const PAGE_HOSTNAME = window.location.hostname;
const IS_LOCAL_FRONTEND =
  !PAGE_HOSTNAME || ["localhost", "127.0.0.1"].includes(PAGE_HOSTNAME);
const LOCAL_DEMO_MODE = true;
const PRODUCTION_API_URL =
  window.MEDIFLOW_API_URL || "https://mediflow-backend-eq23.onrender.com";
const API_ORIGIN = IS_LOCAL_FRONTEND
  ? "http://127.0.0.1:8000"
  : PRODUCTION_API_URL.replace(/\/+$/, "").replace(/\/api\/v1$/, "");
const API_BASE_URL = `${API_ORIGIN}/api/v1`;

const applicationShell = document.querySelector("#application-shell");
const skipLink = document.querySelector(".skip-link");
const triageForm = document.querySelector("#triage-form");
const clinicalText = document.querySelector("#clinical-text");
const documentFile = document.querySelector("#document-file");
const formError = document.querySelector("#form-error");
const resultStatus = document.querySelector("#result-status");
const emptyState = document.querySelector("#empty-state");
const resultContent = document.querySelector("#result-content");
const priorityCard = document.querySelector("#priority-card");
const filePreview = document.querySelector("#attachment-preview");
const fileName = document.querySelector("#attachment-name");
const fileDetails = document.querySelector("#attachment-details");
const removeFile = document.querySelector("#remove-attachment");

function setFormError(element, message) {
  if (!element) return;
  element.textContent = message;
  element.hidden = !message;
}

function showApplication() {
  if (applicationShell) applicationShell.hidden = false;
  if (skipLink) skipLink.hidden = false;
}

async function readApiResponse(response) {
  const body = await response.text();
  let result = {};
  if (body) {
    try {
      result = JSON.parse(body);
    } catch {
      result = { detail: body.slice(0, 500) };
    }
  }
  if (!response.ok) {
    const detail = result.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : response.statusText || "A API recusou a solicitação.";
    throw new Error(`HTTP ${response.status}: ${message}`);
  }
  return result;
}

async function apiFetch(url, options = {}) {
  try {
    return await fetch(url, options);
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error(
        `A ligação à API em ${new URL(url).origin} falhou antes de receber uma resposta. ` +
          "Aguarde 30 segundos enquanto o servidor no Render inicia e tente novamente.",
      );
    }
    throw error;
  }
}

async function authorizedFetch(url, options = {}) {
  return apiFetch(url, options);
}

function renderResult(result) {
  const data = result.dados_extraidos || {};
  const classification = data.classificacao || {};
  const level = classification.nivel_prioridade || "Indefinido";
  const isReview = result.status === "auditoria_humana";
  const percentage = Math.round((classification.score_confianca || 0) * 100);

  document.querySelector("#priority-label").textContent =
    "SUGESTÃO DE ENCAMINHAMENTO";
  document.querySelector("#confidence").textContent =
    `Confiança informada pelo modelo: ${percentage}%`;
  document.querySelector("#result-title").textContent =
    `Prioridade sugerida: ${level}`;
  document.querySelector("#result-summary").textContent =
    "Resultado de processamento automatizado; requer validação humana.";
  document.querySelector("#document-id").textContent =
    `Documento ${result.id_documento || "—"}`;
  document.querySelector("#review-text").textContent = isReview
    ? "Encaminhado para revisão humana antes de qualquer decisão."
    : "O resultado deve ser validado por uma pessoa responsável.";
  document.querySelector("#document-type").textContent =
    classification.tipo_documento || "Não identificado";
  document.querySelector("#specialty").textContent =
    result.especialidade_sugerida || "Não identificada";
  document.querySelector("#storage-status").textContent =
    result.armazenamento?.status === "confirmado"
      ? "Guardado com sucesso"
      : "Não confirmado";
  document.querySelector("#entity-count").textContent =
    result.seguranca?.pii_mascarada
      ? "Identificadores mascarados"
      : "Sem identificadores detetados";
  document.querySelector("#json-output").textContent = JSON.stringify(
    result,
    null,
    2,
  );

  priorityCard.dataset.priority =
    level === "Urgente" ? "urgent" : level === "Indefinido" ? "review" : "routine";
  resultStatus.classList.remove("is-ready", "is-review");
  resultStatus.classList.add(isReview ? "is-review" : "is-ready");
  resultStatus.lastChild.textContent = isReview
    ? " Em revisão humana"
    : " Processamento concluído";
  emptyState.hidden = true;
  resultContent.hidden = false;
  document.querySelector("#results-heading").focus({ preventScroll: true });
}

function initializeSession() {
  const userLabel = document.querySelector("#demo-user-name");
  if (userLabel) userLabel.textContent = "Dr. Equipa 23 (Demo)";
  showApplication();
}

const characterCount = document.querySelector("#character-count");
if (clinicalText && characterCount) {
  clinicalText.addEventListener("input", () => {
    characterCount.textContent = `${clinicalText.value.length} / 20000`;
  });
}

if (documentFile) {
  documentFile.addEventListener("change", () => {
    const file = documentFile.files?.[0];
    filePreview.hidden = !file;
    if (file) {
      fileName.textContent = file.name;
      fileDetails.textContent = `${(file.size / 1024).toFixed(1)} KB`;
    }
  });
}

if (removeFile) {
  removeFile.addEventListener("click", () => {
    documentFile.value = "";
    filePreview.hidden = true;
  });
}

if (triageForm) {
  triageForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setFormError(formError, "");
    const file = documentFile?.files?.[0];
    if (!file && !clinicalText.value.trim()) {
      setFormError(formError, "Introduza texto ou selecione um documento.");
      return;
    }
    if (file && clinicalText.value.trim()) {
      setFormError(formError, "Envie um ficheiro ou texto, não ambos ao mesmo tempo.");
      return;
    }
    const submitButton = triageForm.querySelector('button[type="submit"]');
    submitButton.disabled = true;
    resultStatus.lastChild.textContent = " A processar documento...";
    try {
      const body = new FormData();
      let endpoint = `${API_BASE_URL}/triage/text`;
      if (file) {
        endpoint = `${API_BASE_URL}/triage/file`;
        body.append("file", file);
      } else {
        body.append("texto", clinicalText.value);
      }
      const response = await authorizedFetch(endpoint, {
        method: "POST",
        body,
      });
      const result = await readApiResponse(response);
      renderResult(result);
    } catch (error) {
      resultStatus.lastChild.textContent = " Falha no processamento";
      setFormError(formError, error.message || "Não foi possível processar o documento.");
    } finally {
      submitButton.disabled = false;
    }
  });
}

initializeSession();
