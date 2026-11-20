"""Default voice-role routing policy for audiobook Production."""


def has_legacy_character_voice_reference(state: dict) -> bool:
    """Return whether a legacy project contains a non-empty character voice choice."""
    if not isinstance(state, dict):
        return False
    characters = state.get("characters") or []
    if isinstance(characters, (list, tuple)):
        for row in characters:
            if isinstance(row, dict) and str(row.get("voice_profile") or "").strip():
                return True
    for key in ("voice_cast", "voice_cast_identity_assignments"):
        assignments = state.get(key)
        if isinstance(assignments, dict) and any(
            str(value or "").strip() for value in assignments.values()
        ):
            return True
    return False


def narrator_only_for_generation(
    state: dict,
    configured_character_profile_count: int,
    third_person_profile_available: bool,
) -> bool:
    """Use Third Person by default, but preserve legacy explicit narrator-only choices.

    The old project flag was also written automatically for zero-cast projects.
    Therefore a legacy True is treated as an explicit choice only when the
    project contains a saved character assignment/reference. New choices use the
    dedicated user-choice key and always take precedence.
    """
    if not isinstance(state, dict):
        state = {}
    if state.get("narrator_only_generation_user_choice") is True:
        return state.get("narrator_only_generation") is True
    if state.get("narrator_only_generation_user_opt_out") is True:
        return False
    try:
        configured_count = max(0, int(configured_character_profile_count))
    except (TypeError, ValueError, OverflowError):
        configured_count = 0
    legacy_explicit_cast = configured_count > 0 or has_legacy_character_voice_reference(state)
    if state.get("narrator_only_generation") is True and legacy_explicit_cast:
        return True
    if third_person_profile_available:
        return False
    return state.get("narrator_only_generation") is True or configured_count == 0
