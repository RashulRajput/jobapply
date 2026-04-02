# AI Study Assistant

A Manifest V3 Chrome extension that reads quiz-style text from the active webpage, sends the detected question to Gemini, and shows a suggested answer with a short explanation in the popup.

## Files

- `manifest.json`: Extension manifest and permissions.
- `background.js`: Coordinates tab analysis, Gemini requests, and storage.
- `content.js`: Extracts question and option text from the active page.
- `popup.html`: Popup markup.
- `popup.js`: Popup interaction logic.
- `styles.css`: Popup styling.

## Setup

1. Open `chrome://extensions`.
2. Enable **Developer mode**.
3. Click **Load unpacked**.
4. Select the `ai-study-assistant-extension` folder.
5. Open the extension popup and paste your Gemini API key.
6. Visit a quiz webpage and click **Analyze Quiz**.

## Notes

- The extension does not click buttons, submit answers, or automate the page.
- Quiz extraction is heuristic-based and uses generic selectors: `h1`, `h2`, `p`, `li`, and `label`.
- Gemini is prompted to return the answer and a short explanation only.
