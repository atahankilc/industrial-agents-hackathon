"""Claude API failures as a short sentence for the person using the app, plus a code the app can act on.

The raw error (`BadRequestError: Error code: 400 - {...}`) goes to the server log only. Codes: credits (the API
credit has run out), auth (key not accepted), busy (rate limited), unavailable (Anthropic overloaded or down),
offline (no connection / timeout), internal (anything else, including our own bugs)."""

import logging

import anthropic

log = logging.getLogger("backend")

MESSAGES = {
    "credits": "The Guide is offline right now: its AI credit has run out. Please try again later.",
    "auth": "The Guide is offline right now: its AI access key was not accepted. Please try again later.",
    "busy": "The Guide is getting too many questions at once. Please try again in a moment.",
    "unavailable": "The Guide's AI service is busy or down right now. Please try again in a moment.",
    "offline": "The Guide can't reach its AI service right now. Check the connection and try again.",
    "internal": "Something went wrong on our side. Please try again.",
}
STATUS = {"credits": 503, "auth": 503, "busy": 429, "unavailable": 503, "offline": 503, "internal": 500}


def code_of(error: Exception) -> str:
    if isinstance(error, anthropic.APIStatusError):
        text = str(error).lower()
        if error.status_code == 402 or "credit balance" in text or "billing" in text:
            return "credits"
        if error.status_code in (401, 403):
            return "auth"
        if error.status_code == 429:
            return "busy"
        if error.status_code >= 500:
            return "unavailable"
        return "internal"
    if isinstance(error, anthropic.APIConnectionError):  # includes APITimeoutError
        return "offline"
    return "internal"


def friendly(error: Exception) -> dict:
    """{"code", "message"} for the app; the raw error is logged here."""
    code = code_of(error)
    log.warning("Claude call failed (%s): %s: %s", code, type(error).__name__, str(error)[:500])
    return {"code": code, "message": MESSAGES[code]}


def error_line(error: Exception) -> dict:
    """The NDJSON error line of the Guide and Builder streams: readable `message`, `code`, raw `detail` for logs."""
    return {"type": "error", **friendly(error), "detail": f"{type(error).__name__}: {error}"[:300]}
