const apiKeyInput = document.getElementById("apiKey");
const analyzeButton = document.getElementById("analyzeButton");
const statusElement = document.getElementById("status");
const questionElement = document.getElementById("questionText");
const answerElement = document.getElementById("answerText");
const explanationElement = document.getElementById("explanationText");

document.addEventListener("DOMContentLoaded", () => {
  initializePopup().catch((error) => {
    showStatus(error.message || "Unable to initialize the popup.", true);
  });
});

analyzeButton.addEventListener("click", async () => {
  setLoading(true);
  showStatus("Analyzing the active page...");

  try {
    await persistApiKeyIfProvided();

    const response = await chrome.runtime.sendMessage({ type: "ANALYZE_QUIZ" });

    if (!response?.ok) {
      throw new Error(response?.error || "Analysis failed.");
    }

    renderAnalysis(response.result);
    showStatus("Analysis complete.");
  } catch (error) {
    showStatus(error.message || "Something went wrong during analysis.", true);
  } finally {
    setLoading(false);
  }
});

async function initializePopup() {
  const [{ geminiApiKey = "" }, { lastAnalysis = null }] = await Promise.all([
    chrome.storage.sync.get(["geminiApiKey"]),
    chrome.storage.local.get(["lastAnalysis"])
  ]);

  apiKeyInput.value = geminiApiKey;

  if (lastAnalysis) {
    renderAnalysis(lastAnalysis);
  }
}

async function persistApiKeyIfProvided() {
  const typedKey = apiKeyInput.value.trim();

  if (typedKey) {
    await chrome.storage.sync.set({ geminiApiKey: typedKey });
    return;
  }

  const { geminiApiKey = "" } = await chrome.storage.sync.get(["geminiApiKey"]);

  if (!geminiApiKey.trim()) {
    throw new Error("Enter your Gemini API key before analyzing.");
  }
}

function renderAnalysis(result) {
  questionElement.textContent = result?.question || "No question detected.";
  answerElement.textContent = result?.answer || "No answer returned.";
  explanationElement.textContent = result?.explanation || "No explanation returned.";

  questionElement.classList.remove("muted");
  answerElement.classList.remove("muted");
  explanationElement.classList.remove("muted");
}

function showStatus(message, isError = false) {
  statusElement.textContent = message;
  statusElement.classList.toggle("error", isError);
}

function setLoading(isLoading) {
  analyzeButton.disabled = isLoading;
  analyzeButton.textContent = isLoading ? "Analyzing..." : "Analyze Quiz";
}
