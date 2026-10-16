"""Node names: the words title case leaves alone, and comparing names for
duplicates."""


DEFAULT_TITLECASE_EXCLUSIONS = ["a", "an", "or", "not", "with", "the", "but", "and", "vs", "vs.", "at", "of", "are", "as", "is", "in"]


# Duplicate-name comparison is a separate concern from display formatting.
# Keep its connector words stable when the user changes capitalization modes or
# title-case exceptions.
DEFAULT_DUPLICATE_STOP_WORDS = frozenset(DEFAULT_TITLECASE_EXCLUSIONS)


def _get_duplicate_stop_words():
    """Return stable connector words ignored during duplicate comparison."""
    return set(DEFAULT_DUPLICATE_STOP_WORDS)


def normalize_name_for_comparison(name):
    """Strip stop/connector words and lowercase for fuzzy duplicate comparison.

    Duplicate detection deliberately does not depend on the user's display
    formatting choice or Title Case exceptions.
    """
    if not name:
        return ""
    stop_words = _get_duplicate_stop_words()
    words = name.lower().split()
    return " ".join(w for w in words if w not in stop_words)
