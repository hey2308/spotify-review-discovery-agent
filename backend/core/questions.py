"""Shared discovery question definitions for pipeline and API."""

QUESTION_TEXT: dict[str, str] = {
    "Q1": "Why do users struggle to discover new music?",
    "Q2": "What are the most common frustrations with recommendations?",
    "Q3": "What listening behaviors are users trying to achieve?",
    "Q4": "What causes users to repeatedly listen to the same content?",
    "Q5": "Which user segments experience different discovery challenges?",
    "Q6": "What unmet needs emerge consistently across all sources?",
}

QUESTION_ORDER: tuple[str, ...] = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6")

QUESTION_RETRIEVAL_QUERIES: dict[str, str] = {
    "Q1": (
        "struggle discover new music barriers algorithm recommendations "
        "find fresh artists discovery failure"
    ),
    "Q2": (
        "frustrated recommendations stale repetitive same songs "
        "algorithm wrong bad suggestions discover weekly"
    ),
    "Q3": (
        "listening intent mood exploration focus workout sleep "
        "want to hear trying to achieve session goal"
    ),
    "Q4": (
        "repeat same songs comfort listening autoplay daily mix "
        "loop same artist stuck listening again"
    ),
    "Q5": (
        "power user casual listener new subscriber long term "
        "different discovery experience segment eclectic taste"
    ),
    "Q6": (
        "wish need missing want feature workaround unmet "
        "should exist better discovery control reset taste"
    ),
}
