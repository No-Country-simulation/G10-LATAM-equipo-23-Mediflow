"use strict";

const PAGE_HOSTNAME = window.location.hostname;
const IS_LOCAL_FRONTEND =
  !PAGE_HOSTNAME || ["localhost", "127.0.0.1"].includes(PAGE_HOSTNAME);
const LOCAL_DEMO_MODE = IS_LOCAL_FRONTEND;
const PRODUCTION_API_URL =
  window.MEDIFLOW_API_URL || window.location.origin;
const API_ORIGIN = IS_LOCAL_FRONTEND
  ? "http://127.0.0.1:8000"
  : PRODUCTION_API_URL.replace(/\/+$/, "").replace(/\/api\/v1$/, "");
const API_BASE_URL = `${API_ORIGIN}/api/v1`;
const loginScreen = document.querySelector("#login-screen");
const loginForm = document.querySelector("#login-form");
const loginError = document.querySelector("#login-error");
const loginSubmit = document.querySelector("#login-submit");
const usernameInput = document.querySelector("#login-username");
const passwordInput = document.querySelector("#login-password");
const registerForm = document.querySelector("#register-form");
const registerError = document.querySelector("#register-error");
const registerSubmit = document.querySelector("#register-submit");
const registerUsername = document.querySelector("#register-username");
const registerPassword = document.querySelector("#register-password");
const registerRole = document.querySelector("#register-role");
const setupForm = document.querySelector("#setup-form");
const setupError = document.querySelector("#setup-error");
const setupSubmit = document.querySelector("#setup-submit");
const setupUsernameInput = document.querySelector("#setup-username");
const setupPasswordInput = document.querySelector("#setup-password");
const setupConfirmationInput = document.querySelector(
  "#setup-password-confirmation",
);
const loginFootnote = document.querySelector("#login-footnote");
const loginTitle = document.querySelector("#login-title");
const loginDescription = document.querySelector("#login-description");
const applicationShell = document.querySelector("#application-shell");
const logoutButton = document.querySelector("#logout-button");
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
let authToken = null;

function setFormError(element, message) {
  element.textContent = message;
  element.hidden = !message;
}

function showLogin(message = "") {
  applicationShell.hidden = true;
  loginScreen.hidden = false;
  skipLink.hidden = true;
  loginForm.hidden = false;
  registerForm.hidden = true;
  setupForm.hidden = true;
  loginTitle.textContent = "Entre no MediFlow";
  loginDescription.textContent =
    "Acesse com sua conta ou crie um perfil de operador ou médico auditor.";
  loginFootnote.textContent = "Sessão protegida · acesso demonstrativo";
  setFormError(loginError, message);
  if (!message) usernameInput.focus({ preventScroll: true });
}

function showRegister() {
  loginForm.hidden = true;
  registerForm.hidden = false;
  setupForm.hidden = true;
  loginTitle.textContent = "Crie sua conta";
  loginDescription.textContent =
    "O registo público permite os perfis de operador e médico auditor.";
  setFormError(registerError, "");
  registerUsername.focus({ preventScroll: true });
}

function showInitialSetup() {
  applicationShell.hidden = true;
  loginScreen.hidden = false;
  skipLink.hidden = true;
  loginForm.hidden = true;
  registerForm.hidden = true;
  setupForm.hidden = false;
  loginTitle.textContent = "Crie o acesso inicial";
  loginDescription.textContent =
    "Configure a primeira conta de administrador deste ambiente local.";
  loginFootnote.textContent =
    "Primeiro acesso · a senha é guardada como hash.";
  setupUsernameInput.focus({ preventScroll: true });
}

function showApplication() {
  loginScreen.hidden = true;
  applicationShell.hidden = false;
  skipLink.hidden = false;
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
          "Verifique se o backend está ativo e se CORS permite a origem desta página.",
      );
    }
    throw error;
  }
}

async function refreshAccessToken() {
  const response = await apiFetch(`${API_BASE_URL}/auth/refresh`, {
    method: "POST",
    credentials: "include",
  });
  const result = await readApiResponse(response);
  authToken = result.access_token;
}

async function authorizedFetch(url, options = {}) {
  if (LOCAL_DEMO_MODE) {
    return apiFetch(url, options);
  }
  if (!authToken) await refreshAccessToken();
  const headers = new Headers(options.headers || {});
  headers.set("Authorization", `Bearer ${authToken}`);
  let response = await apiFetch(url, {
    ...options,
    headers,
    credentials: "include",
  });
  if (response.status === 401) {
    await refreshAccessToken();
    headers.set("Authorization", `Bearer ${authToken}`);
    response = await apiFetch(url, {
      ...options,
      headers,
      credentials: "include",
    });
  }
  return response;
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
    `Documento ${result.id_documento}`;
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

async function initializeSession() {
  if (LOCAL_DEMO_MODE) {
    document.querySelector("#demo-user-name").textContent = "Dr. Equipa 23 (Demo)";
    logoutButton.hidden = true;
    showApplication();
    return;
  }

  try {
    await refreshAccessToken();
    const response = await apiFetch(`${API_BASE_URL}/auth/me`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (response.ok) {
      showApplication();
      return;
    }
    authToken = null;
  } catch {
    authToken = null;
  }

  try {
    const response = await apiFetch(`${API_BASE_URL}/auth/status`);
    const { configured } = await readApiResponse(response);
    if (configured) showLogin("Entre com seu utilizador e senha.");
    else showInitialSetup();
  } catch (error) {
    showLogin(error.message || "Não foi possível conectar à API.");
  }
}

document.querySelector("#show-register").addEventListener("click", showRegister);
document.querySelector("#show-login").addEventListener("click", () => showLogin());

setupForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormError(setupError, "");
  if (setupPasswordInput.value !== setupConfirmationInput.value) {
    setFormError(setupError, "As senhas não coincidem.");
    setupConfirmationInput.focus();
    return;
  }
  setupSubmit.disabled = true;
  try {
    const response = await apiFetch(`${API_BASE_URL}/auth/setup`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: setupUsernameInput.value,
        password: setupPasswordInput.value,
      }),
    });
    const result = await readApiResponse(response);
    authToken = result.access_token;
    setupPasswordInput.value = "";
    setupConfirmationInput.value = "";
    showApplication();
  } catch (error) {
    setFormError(setupError, error.message || "Não foi possível configurar o acesso.");
  } finally {
    setupSubmit.disabled = false;
  }
});

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormError(loginError, "");
  loginSubmit.disabled = true;
  try {
    const response = await apiFetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: usernameInput.value,
        password: passwordInput.value,
      }),
    });
    const result = await readApiResponse(response);
    authToken = result.access_token;
    passwordInput.value = "";
    showApplication();
  } catch (error) {
    setFormError(loginError, error.message || "Não foi possível autenticar.");
  } finally {
    loginSubmit.disabled = false;
  }
});

registerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormError(registerError, "");
  registerSubmit.disabled = true;
  try {
    const response = await apiFetch(`${API_BASE_URL}/auth/register`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: registerUsername.value,
        password: registerPassword.value,
        role: registerRole.value,
      }),
    });
    const result = await readApiResponse(response);
    authToken = result.access_token;
    registerPassword.value = "";
    showApplication();
  } catch (error) {
    setFormError(registerError, error.message || "Não foi possível criar a conta.");
  } finally {
    registerSubmit.disabled = false;
  }
});

const characterCount = document.querySelector("#character-count");
clinicalText.addEventListener("input", () => {
  characterCount.textContent = `${clinicalText.value.length} / 20000`;
});

documentFile.addEventListener("change", () => {
  const file = documentFile.files?.[0];
  filePreview.hidden = !file;
  if (file) {
    fileName.textContent = file.name;
    fileDetails.textContent = `${(file.size / 1024).toFixed(1)} KB`;
  }
});

removeFile.addEventListener("click", () => {
  documentFile.value = "";
  filePreview.hidden = true;
});

triageForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  setFormError(formError, "");
  const file = documentFile.files?.[0];
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
  resultStatus.lastChild.textContent = " A processar documento";
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

logoutButton.addEventListener("click", async () => {
  try {
    const response = await apiFetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.detail || "Não foi possível encerrar a sessão.");
    }
  } catch (error) {
    authToken = null;
    showLogin(error.message || "Sessão local encerrada.");
    return;
  }
  authToken = null;
  showLogin();
});

initializeSession();
