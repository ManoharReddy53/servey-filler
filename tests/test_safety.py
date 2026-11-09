from app.models.domain import StopReason
from app.services.safety import detect_stop_reason


def test_detects_captcha_and_antibot() -> None:
    assert detect_stop_reason("Please complete reCAPTCHA") == StopReason.CAPTCHA
    assert detect_stop_reason("Automated access detected") == StopReason.ANTI_BOT


def test_detects_manual_submission() -> None:
    assert detect_stop_reason("Review before final submission") == StopReason.MANUAL_SUBMISSION
