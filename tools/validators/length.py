"""Length constraint validator."""

from typing import Dict, Any, Optional


def validate_length(
    section_name: str,
    text: str,
    min_sentences: Optional[int] = None,
    max_sentences: Optional[int] = None,
    min_words: Optional[int] = None,
    max_words: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Validate length constraints for a section.

    Args:
        section_name: Section name (for logging)
        text: Text to validate
        min_sentences: Optional min sentence count
        max_sentences: Optional max sentence count
        min_words: Optional min word count
        max_words: Optional max word count

    Returns:
        {"valid": bool, "errors": [...]}
    """
    errors = []
    text = (text or "").strip()

    if min_words is not None or max_words is not None:
        words = len(text.split())
        if min_words is not None and words < min_words:
            errors.append(
                f"{section_name}: expected at least {min_words} words, got {words}"
            )
        if max_words is not None and words > max_words:
            errors.append(
                f"{section_name}: expected at most {max_words} words, got {words}"
            )

    if min_sentences is not None or max_sentences is not None:
        sentences = len([s for s in text.replace("!", ".").replace("?", ".").split(".") if s.strip()])
        if min_sentences is not None and sentences < min_sentences:
            errors.append(
                f"{section_name}: expected at least {min_sentences} sentences, got {sentences}"
            )
        if max_sentences is not None and sentences > max_sentences:
            errors.append(
                f"{section_name}: expected at most {max_sentences} sentences, got {sentences}"
            )

    return {"valid": len(errors) == 0, "errors": errors}
