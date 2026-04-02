const GEMINI_MODEL = "gemini-2.5-flash";
const GEMINI_ENDPOINT =
  `https://generativelanguage.googleapis.com/v1beta/models/${GEMINI_MODEL}:generateContent`;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === "ANALYZE_QUIZ") {
    handleAnalyzeQuiz()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) =>
        sendResponse({
          ok: false,
          error: error.message || "Unable to analyze the current quiz."
        })
      );

    return true;
  }

  if (message?.type === "QUIZ_DATA_CAPTURED") {
    storeCapturedQuiz(message.quizData, sender).catch((error) => {
      console.warn("AI Study Assistant could not store captured quiz data.", error);
    });
  }

  return undefined;
});

async function handleAnalyzeQuiz() {
  const apiKey = await getStoredApiKey();

  if (!apiKey) {
    throw new Error("Enter your Gemini API key in the popup before analyzing.");
  }

  const activeTab = await getActiveTab();
  assertSupportedTab(activeTab);

  await injectContentScript(activeTab.id);

  const quizData = await requestQuizData(activeTab.id);
  await chrome.storage.local.set({ lastCapturedQuiz: quizData });

  const tutorResponse = await askGemini(quizData, apiKey);
  const analysis = {
    question: quizData.question,
    options: quizData.options,
    answer: tutorResponse.answer,
    explanation: tutorResponse.explanation,
    pageTitle: quizData.pageTitle,
    pageUrl: quizData.pageUrl,
    analyzedAt: new Date().toISOString()
  };

  await chrome.storage.local.set({ lastAnalysis: analysis });

  return analysis;
}

async function getStoredApiKey() {
  const { geminiApiKey = "" } = await chrome.storage.sync.get(["geminiApiKey"]);
  return geminiApiKey.trim();
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({
    active: true,
    currentWindow: true
  });

  return tab;
}

function assertSupportedTab(tab) {
  if (!tab?.id || !tab.url) {
    throw new Error("Open a quiz webpage in the active tab and try again.");
  }

  if (!/^https?:/i.test(tab.url)) {
    throw new Error("This extension only works on regular website tabs.");
  }
}

async function injectContentScript(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"]
    });
  } catch (error) {
    throw new Error(
      "The extension could not inspect this page. Some browser pages block extensions."
    );
  }
}

async function requestQuizData(tabId) {
  const response = await chrome.tabs.sendMessage(tabId, { type: "EXTRACT_QUIZ" });

  if (!response?.ok) {
    throw new Error(response?.error || "Could not detect a quiz question on this page.");
  }

  return response.quizData;
}

async function storeCapturedQuiz(quizData, sender) {
  if (!quizData) {
    return;
  }

  await chrome.storage.local.set({
    lastCapturedQuiz: {
      ...quizData,
      tabId: sender?.tab?.id ?? null
    }
  });
}

function buildTutorPrompt(quizData) {
  const lines = [
    "You are a tutor. Provide the correct answer and a short explanation. If MCQ, return the best option exactly as written.",
    'Respond with JSON only using this schema: {"answer":"...","explanation":"..."}.',
    "",
    `Question: ${quizData.question}`
  ];

  if (quizData.options.length) {
    lines.push("Options:");
    quizData.options.forEach((option) => lines.push(`- ${option}`));
  } else {
    lines.push("Options: None provided.");
  }

  return lines.join("\n");
}

async function askGemini(quizData, apiKey) {
  const prompt = buildTutorPrompt(quizData);
  const response = await fetch(`${GEMINI_ENDPOINT}?key=${encodeURIComponent(apiKey)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": apiKey
    },
    body: JSON.stringify({
      system_instruction: {
        parts: [
          {
            text:
              "You are a tutor. Provide the correct answer and a short explanation. If MCQ, return the best option exactly as written."
          }
        ]
      },
      contents: [
        {
          parts: [{ text: prompt }]
        }
      ],
      generationConfig: {
        temperature: 0.2,
        responseMimeType: "application/json"
      }
    })
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(
      extractGeminiError(data) ||
        `Gemini request failed with status ${response.status}.`
    );
  }

  const rawText = data?.candidates?.[0]?.content?.parts
    ?.map((part) => part.text || "")
    .join("\n")
    .trim();

  if (!rawText) {
    throw new Error("Gemini returned an empty response.");
  }

  return parseGeminiResponse(rawText);
}

function extractGeminiError(data) {
  return (
    data?.error?.message ||
    data?.promptFeedback?.blockReason ||
    ""
  );
}

function parseGeminiResponse(rawText) {
  const cleaned = rawText
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();

  try {
    const parsed = JSON.parse(cleaned);
    return {
      answer: normalizeField(parsed.answer),
      explanation: normalizeField(parsed.explanation) || "No explanation provided."
    };
  } catch (error) {
    console.debug("AI Study Assistant received non-JSON Gemini output.", error);
  }

  const lines = cleaned
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  const answerLine = lines.find((line) => /^answer\s*:/i.test(line));
  const explanationLineIndex = lines.findIndex((line) => /^explanation\s*:/i.test(line));

  if (answerLine) {
    const answer = answerLine.replace(/^answer\s*:\s*/i, "").trim();
    const explanation =
      explanationLineIndex >= 0
        ? lines
            .slice(explanationLineIndex)
            .join(" ")
            .replace(/^explanation\s*:\s*/i, "")
            .trim()
        : lines.filter((line) => line !== answerLine).join(" ").trim();

    return {
      answer: answer || lines[0] || cleaned,
      explanation: explanation || "No explanation provided."
    };
  }

  return {
    answer: lines[0] || cleaned,
    explanation: lines.slice(1).join(" ") || "No explanation provided."
  };
}

function normalizeField(value) {
  return typeof value === "string" ? value.trim() : "";
}
