(() => {
  if (window.__aiStudyAssistantInitialized) {
    return;
  }

  window.__aiStudyAssistantInitialized = true;

  const SELECTOR = "h1, h2, p, li, label";
  const QUESTION_PREFIX_RE = /^(question|q\s*\d+[\).\:]?)/i;
  const OPTION_PREFIX_RE = /^(?:[A-Z]|[a-z]|[0-9]{1,2})[\).\:\-]\s+\S+/;
  const MCQ_HINT_RE =
    /\b(select|choose|which of the following|multiple choice|true or false)\b/i;

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message?.type !== "EXTRACT_QUIZ") {
      return undefined;
    }

    handleExtraction(sendResponse);
    return true;
  });

  async function handleExtraction(sendResponse) {
    try {
      const quizData = extractQuizData();

      try {
        await chrome.runtime.sendMessage({
          type: "QUIZ_DATA_CAPTURED",
          quizData
        });
      } catch (storageError) {
        console.debug(
          "AI Study Assistant could not forward quiz data to the background script.",
          storageError
        );
      }

      sendResponse({ ok: true, quizData });
    } catch (error) {
      sendResponse({
        ok: false,
        error: error.message || "Quiz extraction failed."
      });
    }
  }

  function extractQuizData() {
    const candidates = getVisibleTextCandidates();

    if (!candidates.length) {
      throw new Error("No readable quiz content found on this page.");
    }

    const questionCandidate = chooseQuestionCandidate(candidates);

    if (!questionCandidate) {
      throw new Error("Unable to detect a likely quiz question on this page.");
    }

    const options = findOptionsNearQuestion(questionCandidate, candidates);

    return {
      question: questionCandidate.text,
      options,
      pageTitle: document.title,
      pageUrl: window.location.href,
      extractedAt: new Date().toISOString()
    };
  }

  function getVisibleTextCandidates() {
    const seenTexts = new Set();

    return Array.from(document.querySelectorAll(SELECTOR))
      .map((element, index) => ({
        element,
        index,
        text: normalizeText(element.innerText || element.textContent || "")
      }))
      .filter((candidate) => {
        if (!candidate.text || candidate.text.length < 4 || !isVisible(candidate.element)) {
          return false;
        }

        const normalizedKey = candidate.text.toLowerCase();

        if (seenTexts.has(normalizedKey)) {
          return false;
        }

        seenTexts.add(normalizedKey);
        return true;
      });
  }

  function chooseQuestionCandidate(candidates) {
    if (!candidates.length) {
      return null;
    }

    const scored = candidates
      .map((candidate) => ({
        ...candidate,
        score: scoreQuestionCandidate(candidate.element, candidate.text)
      }))
      .sort((left, right) => right.score - left.score || left.index - right.index);

    if (scored[0].score >= 15) {
      return scored[0];
    }

    return { ...candidates[0], score: 0 };
  }

  function scoreQuestionCandidate(element, text) {
    const tagName = element.tagName.toLowerCase();
    let score = 0;

    if (text.endsWith("?")) {
      score += 40;
    }

    if (QUESTION_PREFIX_RE.test(text)) {
      score += 24;
    }

    if (MCQ_HINT_RE.test(text)) {
      score += 20;
    }

    if (tagName === "h1" || tagName === "h2") {
      score += 15;
    }

    if (text.length >= 20 && text.length <= 260) {
      score += 10;
    }

    if (!looksLikeOption(text)) {
      score += 5;
    }

    return score;
  }

  function findOptionsNearQuestion(questionCandidate, allCandidates) {
    let currentContainer = questionCandidate.element.parentElement;
    let depth = 0;

    while (currentContainer && depth < 4) {
      const scopedCandidates = Array.from(currentContainer.querySelectorAll(SELECTOR))
        .map((element, index) => ({
          element,
          index,
          text: normalizeText(element.innerText || element.textContent || "")
        }))
        .filter((candidate) => candidate.text && isVisible(candidate.element));

      const scopedIndex = scopedCandidates.findIndex(
        (candidate) => candidate.element === questionCandidate.element
      );

      if (scopedIndex >= 0) {
        const scopedOptions = collectOptionsFromCandidates(scopedCandidates, scopedIndex);

        if (scopedOptions.length >= 2) {
          return scopedOptions;
        }
      }

      currentContainer = currentContainer.parentElement;
      depth += 1;
    }

    const allCandidatesIndex = allCandidates.findIndex(
      (candidate) => candidate.element === questionCandidate.element
    );

    return collectOptionsFromCandidates(allCandidates, allCandidatesIndex);
  }

  function collectOptionsFromCandidates(candidates, startIndex) {
    if (startIndex < 0) {
      return [];
    }

    const options = [];

    for (let index = startIndex + 1; index < candidates.length && index <= startIndex + 12; index += 1) {
      const candidate = candidates[index];

      if (isLikelyQuestionText(candidate.element, candidate.text) && options.length > 0) {
        break;
      }

      if (isOptionCandidate(candidate.element, candidate.text, options.length)) {
        options.push(candidate.text);
        continue;
      }

      if (options.length > 0) {
        break;
      }
    }

    return uniqueTexts(options).slice(0, 6);
  }

  function isOptionCandidate(element, text, currentOptionCount) {
    const tagName = element.tagName.toLowerCase();

    if (!text || text.length > 160 || text.endsWith("?")) {
      return false;
    }

    if (QUESTION_PREFIX_RE.test(text)) {
      return false;
    }

    if (looksLikeOption(text)) {
      return true;
    }

    if ((tagName === "label" || tagName === "li") && text.split(" ").length <= 20) {
      return true;
    }

    if (currentOptionCount > 0 && text.split(" ").length <= 16) {
      return true;
    }

    return false;
  }

  function isLikelyQuestionText(element, text) {
    return scoreQuestionCandidate(element, text) >= 30;
  }

  function looksLikeOption(text) {
    return OPTION_PREFIX_RE.test(text) || /^[A-D]\s*[-:)]\s*\S+/i.test(text);
  }

  function uniqueTexts(values) {
    const seen = new Set();

    return values.filter((value) => {
      const key = value.toLowerCase();

      if (seen.has(key)) {
        return false;
      }

      seen.add(key);
      return true;
    });
  }

  function normalizeText(value) {
    return value.replace(/\s+/g, " ").trim();
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();

    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      parseFloat(style.opacity || "1") > 0 &&
      rect.width > 0 &&
      rect.height > 0
    );
  }
})();
