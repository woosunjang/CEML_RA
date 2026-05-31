"""
Lab Research Agents — Agent Router

Maps agent modes to their preferred document types for retrieval prioritization.
v0.1: uses explicit user-selected filters (router is informational only).
v0.2: will use these priorities for automatic retrieval expansion.
"""

# ---------------------------------------------------------------------------
# Agent → Document type priority lists
# ---------------------------------------------------------------------------

AGENT_DOCUMENT_PRIORITIES: dict[str, list[str]] = {
    "literature": ["paper", "review", "proposal", "lecture_note"],
    "proposal": ["proposal", "memo", "paper", "review", "lecture_note"],
    "manuscript": ["manuscript", "response_letter", "paper", "review"],
    "lecture": ["lecture_slide", "lecture_note", "review", "paper"],
    "scout": ["paper"],  # project="paper-scout" auto-collected papers only
}


def get_preferred_document_types(agent_mode: str) -> list[str]:
    """
    Get the preferred document types for a given agent mode.

    In v0.1, this is informational only — the user selects filters explicitly.
    In v0.2, this will be used when document_type == "all" to expand retrieval
    in priority order.

    Args:
        agent_mode: One of "literature", "proposal", "manuscript", "lecture".

    Returns:
        Ordered list of preferred document type strings.
    """
    return AGENT_DOCUMENT_PRIORITIES.get(agent_mode, [])
