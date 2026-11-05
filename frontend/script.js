"use strict";

const scenarios = {
  routine: {
    text: "Paciente fictício relata desconforto leve há dois dias. Nega outros sintomas. Retorno de rotina agendado para acompanhamento.",
    priority: "routine",
    confidence: 0.94,
    title: "Fluxo de rotina",
    summary: "O texto de demonstração não contém sinalizador de prioridade definido neste protótipo.",
    review: "Encaminhamento sugerido: fila de revisão de rotina.",
    documentType: "Relato clínico (simulado)",
    entities: ["desconforto leve", "dois dias", "retorno agendado"],
  },
  urgent: {
    text: "CASO FICTÍCIO — Documento de demonstração. O texto menciona dor intensa e falta de ar. Sinalizador urgente para demonstrar o encaminhamento prioritário.",
    priority: "urgent",
    confidence: 0.98,
    title: "Revisão prioritária",
    summary: "Sinalizador de prioridade detectado no texto fictício deste cenário.",
    review: "Encaminhamento sugerido: revisão prioritária por profissional de saúde. Este exemplo não é orientação médica.",
    documentType: "Relato clínico (simulado)",
    entities: ["dor intensa (exemplo)", "falta de ar (exemplo)", "sinalizador de prioridade"],
  },
  ambiguous: {
    text: "CASO FICTÍCIO — Documento de demonstração. As informações deste relato são inconclusivas e ambíguas, sem dados suficientes para classificação automatizada.",
    priority: "review",
    confidence: 0.48,
    title: "Revisão humana necessária",
    summary: "As informações do exemplo são ambíguas; não é possível classificar com segurança neste protótipo.",
    review: "Encaminhamento sugerido: revisão humana antes de qualquer decisão.",
    documentType: "Relato clínico (simulado)",
    entities: ["informações ambíguas", "dados insuficientes"],
  },
};

const form = document.querySelector("#triage-form");
const textInput = document.querySelector("#clinical-text");
const fileInput = document.querySelector("#document-file");
const characterCount = document.querySelector("#character-count");
const formError = document.querySelector("#form-error");
const emptyState = document.querySelector("#empty-state");
const resultContent = document.querySelector("#result-content");
const resultStatus = document.querySelector("#result-status");
const priorityCard = document.querySelector("#priority-card");
const selectedScenarioButtons = document.querySelectorAll("[data-scenario]");
const attachmentPreview = document.querySelector("#attachment-preview");
const attachmentImage = document.querySelector("#attachment-image");
const attachmentName = document.querySelector("#attachment-name");
const attachmentDetails = document.querySelector("#attachment-details");
const attachmentOpen = document.querySelector("#attachment-open");
const removeAttachmentButton = document.querySelector("#remove-attachment");

let selectedScenario = null;
let currentFile = null;
let attachmentObjectUrl = null;

const supportedFileTypes = {
  txt: { kind: "text", label: "Arquivo de texto" },
  json: { kind: "json", label: "Arquivo JSON" },
  jpg: { kind: "image", label: "Imagem" },
  jpeg: { kind: "image", label: "Imagem" },
  png: { kind: "image", label: "Imagem" },
  webp: { kind: "image", label: "Imagem" },
  gif: { kind: "image", label: "Imagem" },
  pdf: { kind: "pdf", label: "Documento PDF" },
};

const priorityLabels = {
  routine: "ROTINA",
  urgent: "PRIORIDADE",
  review: "REVISÃO HUMANA",
};

function countEntities(text) {
  const patterns = [
    /\b(?:dor|desconforto|febre|falta de ar|tosse|náusea)\b/gi,
    /\b(?:leve|moderada|intensa|aguda|crônica)\b/gi,
    /\b\d+\s*(?:dias?|semanas?|meses?|anos?|°c|bpm)\b/gi,
    /\b(?:retorno|acompanhamento|sintomas?)\b/gi,
  ];
  const matches = new Set();

  patterns.forEach((pattern) => {
    for (const match of text.matchAll(pattern)) {
      matches.add(match[0].toLocaleLowerCase("pt-BR"));
    }
  });

  return [...matches];
}

function classifyText(text) {
  const urgentTerms = /\b(?:urgente|prioridade|emergência|emergencial|alta gravidade)\b/i;
  const ambiguousTerms = /\b(?:ambígu[oa]s?|inconclusiv[oa]s?|inconsistente|dados insuficientes)\b/i;

  if (urgentTerms.test(text)) {
    return {
      priority: "urgent",
      confidence: 0.78,
      title: "Sinalizador de prioridade",
      summary: "Um termo sinalizador foi encontrado no texto. A regra demonstrativa não avalia sintomas nem gravidade.",
      review: "Encaminhamento sugerido: revisão prioritária por profissional de saúde.",
    };
  }

  if (ambiguousTerms.test(text) || text.trim().length < 40) {
    return {
      priority: "review",
      confidence: 0.42,
      title: "Revisão humana necessária",
      summary: "O texto é insuficiente ou contém termos inconclusivos para as regras deste protótipo.",
      review: "Encaminhamento sugerido: revisão humana antes de qualquer decisão.",
    };
  }

  return {
    priority: "routine",
    confidence: 0.67,
    title: "Fluxo de rotina",
    summary: "Nenhum sinalizador definido para este protótipo foi encontrado no texto.",
    review: "Encaminhamento sugerido: revisão de rotina. A ausência de sinalizadores não indica ausência de risco.",
  };
}

function setScenarioButton(activeScenario) {
  selectedScenarioButtons.forEach((button) => {
    const isSelected = button.dataset.scenario === activeScenario;
    button.classList.toggle("is-selected", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  });
}

function getFileType(file) {
  const extension = file.name.split(".").pop()?.toLocaleLowerCase("pt-BR");
  return supportedFileTypes[extension] ?? null;
}

function formatFileSize(size) {
  return size < 1024 * 1024
    ? `${Math.max(1, Math.round(size / 1024))} KB`
    : `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function showFileError(message) {
  formError.textContent = message;
  formError.hidden = false;
}

function updateAttachmentPreview(file, type) {
  if (attachmentObjectUrl) {
    URL.revokeObjectURL(attachmentObjectUrl);
    attachmentObjectUrl = null;
  }

  currentFile = file;
  attachmentName.textContent = file.name;
  attachmentDetails.textContent = `${type.label} · ${formatFileSize(file.size)} · somente neste dispositivo`;
  attachmentImage.hidden = true;
  attachmentOpen.hidden = true;
  attachmentImage.removeAttribute("src");
  attachmentOpen.removeAttribute("href");

  if (type.kind === "image" || type.kind === "pdf") {
    attachmentObjectUrl = URL.createObjectURL(file);
    if (type.kind === "image") {
      attachmentImage.src = attachmentObjectUrl;
      attachmentImage.hidden = false;
    } else {
      attachmentOpen.href = attachmentObjectUrl;
      attachmentOpen.hidden = false;
    }
  }

  attachmentPreview.hidden = false;
}

function clearAttachment() {
  if (attachmentObjectUrl) {
    URL.revokeObjectURL(attachmentObjectUrl);
    attachmentObjectUrl = null;
  }

  currentFile = null;
  fileInput.value = "";
  attachmentPreview.hidden = true;
  attachmentImage.hidden = true;
  attachmentImage.removeAttribute("src");
  attachmentOpen.hidden = true;
  attachmentOpen.removeAttribute("href");
}

function showResult(result, sourceText, file = null) {
  const extractedEntities = result.entities ?? countEntities(sourceText);
  const fileType = file ? getFileType(file) : null;
  const isUnprocessedDocument = fileType?.kind === "image" || fileType?.kind === "pdf";
  const reviewMessage = isUnprocessedDocument && sourceText.trim()
    ? `${result.review} O arquivo anexado não foi interpretado; a demonstração considera apenas o texto digitado.`
    : result.review;
  const output = {
    demonstracao: true,
    somente_dados_ficticios: true,
    tipo_documento: result.documentType ?? fileType?.label ?? "Texto digitado",
    prioridade_revisao: result.priority,
    confianca_ilustrativa: result.confidence ?? null,
    dados_identificados: extractedEntities,
    encaminhamento_sugerido: reviewMessage,
    requer_auditoria_humana: result.priority !== "routine",
    arquivo: file
      ? {
          nome: file.name,
          formato: fileType?.label,
          tamanho: file.size,
          conteudo_extraido: !isUnprocessedDocument,
        }
      : null,
    observacao: "Resultado ilustrativo; não é diagnóstico nem orientação médica.",
  };

  emptyState.hidden = true;
  resultContent.hidden = false;
  priorityCard.dataset.priority = result.priority;
  document.querySelector("#priority-label").textContent = priorityLabels[result.priority];
  document.querySelector("#confidence").textContent = result.confidence == null
    ? "Sem análise automatizada"
    : `Confiança ilustrativa · ${Math.round(result.confidence * 100)}%`;
  document.querySelector("#result-title").textContent = result.title;
  document.querySelector("#result-summary").textContent = result.summary;
  document.querySelector("#review-text").textContent = reviewMessage;
  document.querySelector("#document-type").textContent =
    result.documentType ?? fileType?.label ?? "Texto digitado";
  document.querySelector("#entity-count").textContent =
    `${extractedEntities.length} ${extractedEntities.length === 1 ? "item" : "itens"}`;
  document.querySelector("#json-output").textContent = JSON.stringify(output, null, 2);

  resultStatus.classList.toggle("is-review", result.priority !== "routine");
  resultStatus.classList.add("is-ready");
  resultStatus.innerHTML =
    '<span class="status-dot" aria-hidden="true"></span>Análise demonstrativa';
  resultContent.setAttribute("aria-label", "Resultado da análise demonstrativa");
}

textInput.addEventListener("input", () => {
  characterCount.textContent = `${textInput.value.length} / 6000`;
  formError.hidden = true;
  selectedScenario = null;
  setScenarioButton(null);
});

selectedScenarioButtons.forEach((button) => {
  button.setAttribute("aria-pressed", "false");
  button.addEventListener("click", () => {
    selectedScenario = button.dataset.scenario;
    textInput.value = scenarios[selectedScenario].text;
    characterCount.textContent = `${textInput.value.length} / 6000`;
    formError.hidden = true;
    setScenarioButton(selectedScenario);
    textInput.focus();
  });
});

fileInput.addEventListener("change", async () => {
  const [file] = fileInput.files ?? [];
  if (!file) return;

  const type = getFileType(file);
  if (!type) {
    showFileError("Formato não suportado. Escolha TXT, JSON, JPG, PNG, WEBP, GIF ou PDF.");
    fileInput.value = "";
    return;
  }

  const textFile = type.kind === "text" || type.kind === "json";
  const maxSize = textFile ? 100_000 : 10 * 1024 * 1024;
  if (file.size > maxSize) {
    showFileError(textFile
      ? "Arquivos TXT e JSON devem ter no máximo 100 KB nesta demonstração."
      : "Imagens e PDFs devem ter no máximo 10 MB nesta demonstração.");
    fileInput.value = "";
    return;
  }

  formError.hidden = true;
  selectedScenario = null;
  setScenarioButton(null);

  if (textFile) {
    try {
      const text = await file.text();
      let content = text;

      if (type.kind === "json") {
        try {
          content = JSON.stringify(JSON.parse(text), null, 2);
        } catch {
          showFileError("O JSON não é válido. Confira o arquivo e tente novamente.");
          fileInput.value = "";
          return;
        }

        if (content.length > 6000) {
          showFileError("O JSON formatado ultrapassa o limite de 6.000 caracteres da demonstração.");
          fileInput.value = "";
          return;
        }
      } else if (content.length > 6000) {
        content = content.slice(0, 6000);
        showFileError("O texto foi limitado a 6.000 caracteres para esta demonstração.");
      }

      textInput.value = content;
      textInput.dispatchEvent(new Event("input", { bubbles: true }));
      updateAttachmentPreview(file, type);
    } catch {
      showFileError("Não foi possível ler o arquivo. Verifique o arquivo e tente novamente.");
      fileInput.value = "";
    }
    return;
  }

  textInput.value = "";
  textInput.dispatchEvent(new Event("input", { bubbles: true }));
  updateAttachmentPreview(file, type);
});

removeAttachmentButton.addEventListener("click", () => {
  clearAttachment();
  formError.hidden = true;
});

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = textInput.value.trim();

  if (!text && !currentFile) {
    showFileError("Escolha um cenário, anexe um arquivo ou escreva um texto fictício antes de continuar.");
    if (!currentFile) textInput.focus();
    return;
  }

  const fileType = currentFile ? getFileType(currentFile) : null;
  const imageOrPdf = fileType?.kind === "image" || fileType?.kind === "pdf";
  const result = imageOrPdf && !text
    ? {
        priority: "review",
        confidence: null,
        title: "Arquivo pronto para revisão",
        summary: "O arquivo foi selecionado localmente, mas este protótipo não extrai nem analisa conteúdo de imagens ou PDFs.",
        review: "Encaminhamento sugerido: integrar OCR ou processamento de documentos no backend antes de analisar este arquivo.",
      }
    : selectedScenario
      ? scenarios[selectedScenario]
      : classifyText(text);

  showResult(result, text, currentFile);
  document.querySelector("#results-heading").focus({ preventScroll: true });
});

window.addEventListener("pagehide", () => {
  if (attachmentObjectUrl) URL.revokeObjectURL(attachmentObjectUrl);
});
