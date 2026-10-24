# BADIA AI — Open-source AI + optional Gemini advisor

The project already includes open-source XGBoost-based environmental modeling. This addition provides an **auditable, rule-based action advisor** with an optional generative explanation using the Gemini API.

## API

POST `/api/ai/advice` with:

```json
{"risk_level":"High","location":"Mafraq","horizon_days":16,"language":"ar","use_gemini":false}
```

Returns a reproducible action and explicit limitations. Available levels are Low, Moderate, High and N/A. Setting `use_gemini: true` uses Gemini only when `GEMINI_API_KEY` is set on the server. Configure `GEMINI_MODEL` to a model your account supports; default is `gemini-2.5-flash`. No API key is needed for the open-source path.

Gemini only explains the fixed recommended action; it does not retrain or replace XGBoost or establish factual validity. It gracefully falls back to the transparent rule if Gemini is unavailable. The endpoint uses user-supplied risk categories, so it should not be described as automatically verifying a particular map cell.

**Important:** This is not a confirmed integration with a model named “Gemma 4.” Gemma and Gemini are different model families. To qualify for any specific MLH prize, verify its official model-use conditions and submission requirements. A public repository by itself is not enough to prove license compliance or prize eligibility.
