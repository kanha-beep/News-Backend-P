import re


PROFANITY = ["damn", "shit", "fuck", "bastard", "idiot"]
SPAM_PATTERNS = [
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"(.)\1{6,}"),
    re.compile(r"\b(?:buy now|free money|click here)\b", re.IGNORECASE),
]


def moderate_comment(content: str) -> dict:
    normalized = content.lower()
    profanity_match = next((word for word in PROFANITY if word in normalized), None)
    spam_match = next((pattern for pattern in SPAM_PATTERNS if pattern.search(content)), None)

    if profanity_match:
        return {"accepted": False, "reason": "Comment failed moderation for profanity."}
    if spam_match:
        return {"accepted": False, "reason": "Comment failed moderation for spam-like content."}
    return {"accepted": True, "reason": ""}

