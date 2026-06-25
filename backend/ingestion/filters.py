import re

from langdetect import LangDetectException, detect

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "\U0001F900-\U0001F9FF"
    "\U00002600-\U000026FF"
    "\U0001FA70-\U0001FAFF"
    "]+",
    flags=re.UNICODE,
)
EMOJI_MODIFIER_PATTERN = re.compile(r"[\ufe00-\ufe0f\u200d]")
WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
NON_LATIN_SCRIPT_PATTERN = re.compile(
    r"[\u0400-\u04FF\u0600-\u06FF\u4E00-\u9FFF\u3040-\u30FF\uAC00-\uD7AF]"
)


def strip_emojis(text: str) -> str:
    cleaned = EMOJI_PATTERN.sub("", text)
    cleaned = EMOJI_MODIFIER_PATTERN.sub("", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def english_word_count(text: str) -> int:
    return len(WORD_PATTERN.findall(text))


def is_english(text: str) -> bool:
    if NON_LATIN_SCRIPT_PATTERN.search(text):
        return False

    letters = [char for char in text if char.isalpha()]
    if not letters:
        return False

    ascii_letters = sum(1 for char in letters if ord(char) < 128)
    if ascii_letters / len(letters) < 0.85:
        return False

    try:
        return detect(text) == "en"
    except LangDetectException:
        return ascii_letters / len(letters) >= 0.95


def review_rejection_reason(
    text: str,
    *,
    min_words: int,
    english_only: bool,
) -> str | None:
    cleaned = strip_emojis(text)
    if not cleaned:
        return "empty_after_clean"

    if english_word_count(cleaned) < min_words:
        return "too_short"

    if english_only and not is_english(cleaned):
        return "non_english"

    return None
