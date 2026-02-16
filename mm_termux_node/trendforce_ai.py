"""AI summary generation for TrendForce alerts."""

from __future__ import annotations

import logging

try:
    from google import genai
except Exception:  # noqa: BLE001
    genai = None

LOGGER = logging.getLogger("trendforce_ai")

PROMPT_TEMPLATE = """
You are the "TrendForce Sentinel," a quantitative trading assistant for a financial engineer. 
Your goal is to strip away noise and deliver a high-signal, blunt summary of semiconductor and macro market changes.

**Rules:**
1. **Be Blunt:** No pleasantries. State the data.
2. **Focus on Change:** Only comment on indicators that have updated or breached a threshold.
3. **Prioritize Alpha:** DRAM/NAND Spot prices and Custom Signals (Golden Cross/Supply Squeeze) are priority #1.
4. **Format for Pushover:** Use concise bullet points, emojis for trend direction (📈, 📉, ⚠️), and keep the total length under 150 words.


**Input Data:**
The following indicators have updated since the last run (Daily/Monthly change % included):

{formatted_list_of_updated_indicators} 
# ^ Python should format this as: "ID 6105 (DRAM Spot): $X.XX (+5.2%)"

**Custom Signal Status:**
{list_of_triggered_signals}
# ^ Python should format this as: "⚠️ DRAM Golden Cross: TRIGGERED (Spot +15% > Capex -2%)"

**Task:**
Draft a Pushover notification summary. 
- If nothing significant changed, reply only with "📉 No significant alpha signal updates."
- If there are updates, structure the alert as:
  **HEADLINE:** (3-4 words summarizing the regime, e.g., "NAND Supply Squeeze Active")
  **ALPHA:** (Updates on Indicators 6105/6106 or Signal breaches)
  **FLOW:** (Significant changes in Shipments/Revenue/Capex)
  **MACRO:** (Only if VIX or Yields moved >5%)
"""


def generate_ai_summary(
    api_key: str, updated_indicators: list[str], triggered_signals: list[str]
) -> str | None:
    """Generate daily summary using Google Gemini API."""
    if not updated_indicators and not triggered_signals:
        return None

    if genai is None:
        LOGGER.error("google.genai not available; skipping AI summary")
        return None

    # Format lists
    inds_str = "\n".join(updated_indicators) if updated_indicators else "None"
    sigs_str = "\n".join(triggered_signals) if triggered_signals else "None"

    prompt = PROMPT_TEMPLATE.format(
        formatted_list_of_updated_indicators=inds_str,
        list_of_triggered_signals=sigs_str,
    )

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
        )
        return response.text
    except Exception as exc:  # noqa: BLE001
        LOGGER.error("Failed to generate AI summary: %s", exc)
        return None
