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

_LEAD_LAG_CONTEXT = """KNOWN LEAD-LAG RELATIONSHIPS (use to project forward signals):
- China PMI leads semiconductor end-demand by 1-2 months
- Memory maker capex leads spot price direction by 6-9 months (inverse: capex cuts mean spot rises later)
- Smartphone/notebook shipment growth leads NAND/DRAM spot demand by 0-2 months
- DRAM spot acceleration predicts foundry utilization changes in 2-3 months
- USD strengthening (DXY up) compresses USD-denominated export revenues for TSMC/Samsung/Hynix
- TWD weakening (TWD/USD falls) pressures TSMC non-USD cost base"""

PROMPT_TEMPLATE = """You are the "TrendForce Sentinel," a cross-asset macro analyst specializing in semiconductor supply chain signals for a financial engineer. Be blunt, data-driven, and cite numbers for every directional call.

{lead_lag_context}

{dashboard_context}

{prior_signals_section}
TODAY'S UPDATED INDICATORS (new data since last run):
{formatted_list_of_updated_indicators}

TRIGGERED CUSTOM SIGNALS:
{list_of_triggered_signals}

OUTPUT FORMAT (use exactly these labels, one per line, plain text, no markdown):
REGIME: <EXPANSION|PEAK|CONTRACTION|TROUGH|INFLECTION>. One sentence justification.
SEMI: most significant semiconductor reading with z-score and direction (cite numbers)
MACRO: most significant macro/FX/trade/yield reading; for any indicator tagged [STALE] in the dashboard write "awaiting release" instead of a directional claim
DEMAND: end-device shipment or production trend for smartphones, notebooks, or servers only; do not use custom signal values here; if no fresh end-device data write "no fresh end-device data"
SIGNAL: <BULLISH|BEARISH|NEUTRAL>. One sentence with numeric evidence. Conviction: N/5.
WATCH: one indicator to monitor next cycle and why (apply lead-lag where relevant)

Rules:
- [STALE] in the dashboard means the data release is overdue - do not make directional claims on it
- A reading of 0% change is NOT stale - it means no movement, not missing data
- Only cite [FRESH] or [NEW] dashboard data for directional claims
- Every directional claim must include a number (%, z-score, or level)
- Total response under 200 words
- Plain text only, no markdown, no bold. Emojis allowed: 📈 📉 ⚠️
- If nothing significant changed, output only: "📉 No significant alpha signal updates."
"""


# Ordered preference: try each model until one succeeds (handles quota limits per model)
_NEW_SDK_MODELS = [
    "gemini-flash-latest",       # Primary: fast, low cost
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
    api_key: str,
    updated_indicators: list[str],
    triggered_signals: list[str],
    dashboard_context: str = "",
    prior_signals: list[str] | None = None,
) -> str | None:
    """Generate daily summary using Google Gemini API.

    Supports both the new ``google-genai`` SDK (_GENAI_SDK == "new") and the
    legacy ``google-generativeai`` SDK (_GENAI_SDK == "legacy").
    Automatically falls back through model list on 429/quota errors.

    Args:
        api_key: Google/Gemini API key.
        updated_indicators: Indicator lines for indicators with new data.
        triggered_signals: Custom signal lines that breached thresholds.
        dashboard_context: Full macro dashboard from build_dashboard_context().
        prior_signals: Last N signal history lines for LLM continuity.
    """
    if not updated_indicators and not triggered_signals:
        return None

    if genai is None or _GENAI_SDK is None:
        LOGGER.error("google.genai not available; skipping AI summary")
        return None

    # Format lists
    inds_str = "\n".join(updated_indicators) if updated_indicators else "None"
    sigs_str = "\n".join(triggered_signals) if triggered_signals else "None"

    # Prior signal history section
    if prior_signals:
        prior_signals_section = (
            f"PRIOR SIGNALS (last {len(prior_signals)} run(s)):\n"
            + "\n".join(prior_signals)
            + "\n"
        )
    else:
        prior_signals_section = ""

    prompt = PROMPT_TEMPLATE.format(
        lead_lag_context=_LEAD_LAG_CONTEXT,
        dashboard_context=dashboard_context or "(macro dashboard not available)",
        prior_signals_section=prior_signals_section,
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
