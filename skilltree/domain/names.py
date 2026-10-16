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


NAME_FORMAT_NONE = "none"


NAME_FORMAT_TITLE = "title"


NAME_FORMAT_SENTENCE = "sentence"


NAME_FORMAT_MODES = {
    NAME_FORMAT_NONE,
    NAME_FORMAT_TITLE,
    NAME_FORMAT_SENTENCE,
}


def format_name(name, formatting):
    """`name` as the user's name formatting writes it: as typed, Sentence
    case, or Title Case leaving the exclusions lower case. `formatting` is
    ConfigManager.get_name_formatting()."""
    mode = formatting['mode']
    if mode == NAME_FORMAT_NONE:
        return name
    if mode == NAME_FORMAT_SENTENCE:
        for index, character in enumerate(name):
            if character.isalpha():
                return name[:index] + character.upper() + name[index + 1:]
        return name

    exclusions = {w.lower() for w in formatting.get('exclusions', [])}
    words = name.split()
    result = []
    for i, word in enumerate(words):
        if i == 0:
            result.append(word[0].upper() + word[1:] if word else word)
        elif word.lower() in exclusions:
            result.append(word.lower())
        else:
            result.append(word[0].upper() + word[1:] if word else word)
    return ' '.join(result)
