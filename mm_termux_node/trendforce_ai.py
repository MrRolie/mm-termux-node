"""AI summary generation for TrendForce alerts."""

from __future__ import annotations

import logging
import re

# Try new google-genai SDK first, fall back to legacy google-generativeai
_GENAI_SDK: str | None = None
genai = None

try:
    from google import genai  # type: ignore[assignment]
    _GENAI_SDK = "new"
except Exception:  # noqa: BLE001
    pass

if genai is None:
    try:
        import google.generativeai as genai  # type: ignore[assignment,no-redef]
        _GENAI_SDK = "legacy"
    except Exception:  # noqa: BLE001
        pass

LOGGER = logging.getLogger("trendforce_ai")

PROMPT_TEMPLATE = """
You are the "TrendForce Sentinel," a quantitative trading assistant for a financial engineer. 
Your goal is to strip away noise and deliver a high-signal, blunt summary of semiconductor and macro market changes.

Rules:
1. Be blunt: no pleasantries, only data-backed conclusions.
2. Focus on change: only mention indicators that updated or breached a threshold.
3. Prioritize alpha: DRAM/NAND spot prices and custom signals (Golden Cross/Supply Squeeze) are priority #1.
4. Output format: plain text only (no markdown, no bold, no headings with **). Emojis are allowed (📈, 📉, ⚠️).
5. Keep length under 150 words.
6. Use numbers as evidence: every directional call must cite the key value/change (%, spread, or level).
7. Translate evidence into intuitive signal language whenever valid:
     - explicitly label signal as Bullish / Bearish / Neutral
     - tie it to the relevant industry, market, or sector (e.g., memory, semiconductors, risk assets, rates).


Input Data:
The following indicators have updated since the last run (Daily/Monthly change % included):

{formatted_list_of_updated_indicators} 
# ^ Python should format this as: "ID 6105 (DRAM Spot): $X.XX (+5.2%)"

Custom Signal Status:
{list_of_triggered_signals}
# ^ Python should format this as: "⚠️ DRAM Golden Cross: TRIGGERED (Spot +15% > Capex -2%)"

Task:
Draft a Pushover notification summary. 
- If nothing significant changed, reply only with "📉 No significant alpha signal updates."
- If there are updates, use this plaintext layout exactly:
    HEADLINE: 3-4 words summarizing the regime
    ALPHA: key updates on indicators 6105/6106 or signal breaches with numbers
    FLOW: significant changes in shipments/revenue/capex with numbers
    MACRO: only if VIX or yields moved >5%, with numbers
    SIGNAL: one-line interpretation such as "📈 Bullish for [industry/market/sector]" or "📉 Bearish for [industry/market/sector]", justified by the strongest numeric evidence above. Use Neutral if evidence is mixed.
"""


# Ordered preference: try each model until one succeeds (handles quota limits per model)
_NEW_SDK_MODELS = [
    "gemini-2.0-flash",       # Primary: fast, low cost
    "gemini-2.0-flash-lite",  # Fallback: lighter quota
    "gemini-2.5-flash",       # Higher-tier fallback
    "gemini-flash-lite-latest",  # Alias fallback
]
_LEGACY_SDK_MODELS = ["gemini-1.5-flash", "gemini-1.0-pro"]


def _to_plaintext_summary(text: str | None) -> str | None:
    """Strip common markdown artifacts while keeping emojis and readable text."""
    if text is None:
        return None

    cleaned = text.replace("\r\n", "\n")
    cleaned = cleaned.replace("**", "")
    cleaned = cleaned.replace("__", "")
    cleaned = cleaned.replace("`", "")
    cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[-*]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)

    cleaned = cleaned.strip()
    return cleaned or None


def generate_ai_summary(
    api_key: str, updated_indicators: list[str], triggered_signals: list[str]
) -> str | None:
    """Generate daily summary using Google Gemini API.

    Supports both the new ``google-genai`` SDK (_GENAI_SDK == "new") and the
    legacy ``google-generativeai`` SDK (_GENAI_SDK == "legacy").
    Automatically falls back through model list on 429/quota errors.
    """
    if not updated_indicators and not triggered_signals:
        return None

    if genai is None or _GENAI_SDK is None:
        LOGGER.error("google.genai not available; skipping AI summary")
        return None

    # Format lists
    inds_str = "\n".join(updated_indicators) if updated_indicators else "None"
    sigs_str = "\n".join(triggered_signals) if triggered_signals else "None"

    prompt = PROMPT_TEMPLATE.format(
        formatted_list_of_updated_indicators=inds_str,
        list_of_triggered_signals=sigs_str,
    )

    if _GENAI_SDK == "new":
        client = genai.Client(api_key=api_key)  # type: ignore[attr-defined]
        for model_name in _NEW_SDK_MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                )
                LOGGER.info("AI summary generated using model: %s", model_name)
                return _to_plaintext_summary(response.text)
            except Exception as exc:  # noqa: BLE001
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
                    LOGGER.warning("Model %s quota exceeded, trying next model...", model_name)
                    continue
                LOGGER.error("Failed to generate AI summary with %s: %s", model_name, exc)
                return None
        LOGGER.error("All models exhausted due to quota limits")
        return None
    else:
        # Legacy google-generativeai SDK
        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        for model_name in _LEGACY_SDK_MODELS:
            try:
                model = genai.GenerativeModel(model_name)  # type: ignore[attr-defined]
                response = model.generate_content(prompt)
                LOGGER.info("AI summary generated using model: %s", model_name)
                return _to_plaintext_summary(response.text)
            except Exception as exc:  # noqa: BLE001
                exc_str = str(exc)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str or "quota" in exc_str.lower():
                    LOGGER.warning("Model %s quota exceeded, trying next model...", model_name)
                    continue
                LOGGER.error("Failed to generate AI summary with %s: %s", model_name, exc)
                return None
        LOGGER.error("All models exhausted due to quota limits")
        return None
