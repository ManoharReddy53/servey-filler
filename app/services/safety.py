from app.models.domain import StopReason


def detect_stop_reason(text: str) -> StopReason | None:
    normalized = text.casefold()
    if any(term in normalized for term in ("captcha", "recaptcha", "i'm not a robot")):
        return StopReason.CAPTCHA
    if any(term in normalized for term in ("anti-bot", "antibot", "bot detection", "automated access")):
        return StopReason.ANTI_BOT
    if any(term in normalized for term in ("submit survey", "final submission", "manual submission")):
        return StopReason.MANUAL_SUBMISSION
    return None
