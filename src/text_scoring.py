import re

RU_KEYWORDS_ESC = [
    "\u0441\u043c\u0435\u0448\u043d\u043e",
    "\u0448\u0443\u0442\u043a\u0430",
    "\u0430\u0445\u0430\u0445\u0430",
    "\u043b\u044e\u0431\u043b\u044e",
    "\u043d\u0435\u043d\u0430\u0432\u0438\u0436\u0443",
    "\u0441\u0435\u043a\u0440\u0435\u0442",
    "\u043f\u0440\u0430\u0432\u0434\u0430",
    "\u0441\u043c\u0435\u0440\u0442\u044c",
    "\u043e\u043f\u0430\u0441\u043d\u043e",
    "\u043f\u043e\u0447\u0435\u043c\u0443",
    "\u0437\u0430\u0447\u0435\u043c",
    "\u0436\u0438\u0437\u043d\u044c",
    "\u0441\u0443\u0434\u044c\u0431\u0430",
    "\u043d\u0435\u0432\u0435\u0440\u043e\u044f\u0442\u043d\u043e",
    "\u0448\u043e\u043a",
    "\u0441\u0442\u0440\u0430\u0445",
    "\u0443\u0436\u0430\u0441",
    "\u0432\u043f\u0435\u0440\u0432\u044b\u0435",
    "\u043d\u0438\u043a\u043e\u0433\u0434\u0430",
    "\u0432\u0441\u0435\u0433\u0434\u0430",
    "\u043f\u0440\u0435\u0434\u0430\u0442\u0435\u043b\u044c",
    "\u0441\u043c\u044b\u0441\u043b",
    "\u0437\u0430\u0434\u0443\u043c\u0430\u0439\u0441\u044f",
]

KEYWORDS = {
    "ru": [bytes(w, "utf-8").decode("unicode_escape") for w in RU_KEYWORDS_ESC],
    "en": [
        "funny", "joke", "haha", "lol", "sarcasm",
        "love", "hate", "fear", "shock", "secret", "truth", "lie",
        "kill", "death", "save", "danger", "betray",
        "why", "how", "never", "always", "first time",
        "meaning", "life", "fate", "unbelievable", "insane",
    ],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def score_segment(seg) -> float:
    text = normalize_text(seg.get("text", ""))
    if not text:
        return 0.0

    score = 0.0
    score += text.count("!") * 0.7
    score += text.count("?") * 0.5
    score += text.count("...") * 0.3

    for kw in KEYWORDS["ru"]:
        if kw in text:
            score += 1.2
    for kw in KEYWORDS["en"]:
        if kw in text:
            score += 1.0

    word_count = len(text.split())
    if 4 <= word_count <= 22:
        score += 0.6
    elif word_count > 40:
        score -= 0.4

    return score
