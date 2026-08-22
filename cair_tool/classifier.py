import json
import re
from typing import Dict, Optional
from anthropic import Anthropic


SYSTEM_INSTRUCTIONS = (
    "You are a classifier for Islamophobic content in YouTube comments. "
    "Apply the rubric provided in the user message exactly. Favor not_sure when "
    "ambiguous. Criticism of a religion's ideas is NOT itself Islamophobic; hostility "
    "toward Muslims as people is. Do not output prose or code fences. Output strict "
    "JSON only."
)


def _safe_float(value, default=0.0):
    """Tolerate non-numeric confidences like 'low'/'high' the model may return."""
    try:
        return float(value)
    except (TypeError, ValueError):
        mapping = {"low": 0.25, "medium": 0.5, "moderate": 0.5, "high": 0.9, "none": 0.0}
        if isinstance(value, str) and value.strip().lower() in mapping:
            return mapping[value.strip().lower()]
        return default


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_strict_json(text: str) -> Optional[Dict[str, object]]:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.strip("`").strip()
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def build_classifier_prompt(rubric_text: str, comment_text: str) -> str:
    return (
        f"Rubric:\n{rubric_text}\n\nComment:\n{comment_text}\n\n"
        "Return only a JSON object with the following keys:"
        " islamophobic, islamophobia_category, severity, target, triggering_span,"
        " is_counterspeech, overall_sentiment, detected_language, language_confidence,"
        " english_translation, model_confidence, model_rationale."
    )


def classify_comment(client: Anthropic, model: str, rubric_text: str, comment_text: str) -> Dict[str, object]:
    response = client.messages.create(
        model=model,
        max_tokens=600,
        temperature=0.0,
        system=SYSTEM_INSTRUCTIONS,
        messages=[{"role": "user", "content": build_classifier_prompt(rubric_text, comment_text)}],
    )
    output_text = "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    parsed = parse_strict_json(output_text)
    if parsed is None:
        return {
            "islamophobic": "not_sure",
            "islamophobia_category": "none",
            "severity": 0,
            "target": "none",
            "triggering_span": "",
            "is_counterspeech": False,
            "overall_sentiment": "neutral",
            "detected_language": "und",
            "language_confidence": 0.0,
            "english_translation": "",
            "model_confidence": 0.0,
            "model_rationale": "PARSE_ERROR — routed to human review",
        }
    result = {
        "islamophobic": parsed.get("islamophobic", "not_sure"),
        "islamophobia_category": parsed.get("islamophobia_category", "none"),
        "severity": _safe_int(parsed.get("severity", 0)),
        "target": parsed.get("target", "none"),
        "triggering_span": parsed.get("triggering_span", "") or "",
        "is_counterspeech": bool(parsed.get("is_counterspeech", False)),
        "overall_sentiment": parsed.get("overall_sentiment", "neutral"),
        "detected_language": parsed.get("detected_language", "und"),
        "language_confidence": _safe_float(parsed.get("language_confidence", 0.0)),
        "english_translation": parsed.get("english_translation", "") or "",
        "model_confidence": _safe_float(parsed.get("model_confidence", 0.0)),
        "model_rationale": parsed.get("model_rationale", "") or "",
    }
    if result["islamophobic"] != "yes":
        result["islamophobia_category"] = "none"
        result["severity"] = 0
        result["target"] = result.get("target", "none") or "none"
    return result


def escalation_flag_for_row(classification: Dict[str, object], text: str) -> bool:
    return (
        classification["islamophobic"] == "yes"
        and classification["islamophobia_category"] == "threat_of_violence"
    )
