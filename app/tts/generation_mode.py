"""Default voice-role routing policy for audiobook Production."""


def narrator_only_for_generation(
    state: dict,
    configured_character_profile_count: int,
    third_person_profile_available: bool,
) -> bool:
    """Resolve narrator-only mode without letting an automatic default bypass Third Person.

    A persisted user choice is authoritative. Older project state can contain
    narrator_only_generation=True because a previous version selected narrator-only
    automatically when no character voice was configured; a saved global Third
    Person profile upgrades that legacy automatic choice to character-cast routing.
    """
    explicitly_chosen = state.get("narrator_only_generation_user_choice") is True
    if explicitly_chosen:
        return state.get("narrator_only_generation") is True
    if state.get("narrator_only_generation_user_opt_out") is True:
        return False
    if third_person_profile_available:
        return False
    return (
        state.get("narrator_only_generation") is True
        or int(configured_character_profile_count) == 0
    )
