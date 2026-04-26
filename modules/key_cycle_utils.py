from typing import Optional, Tuple, Any


def init_first_cycle_key(
    api_key_manager: Any,
    service_name: str,
    first_key_in_overall_cycle: Optional[str],
    key_loop_initial_run: bool,
) -> Tuple[Optional[str], bool]:
    if key_loop_initial_run:
        return api_key_manager.get_key(service_name, peek=True), False
    return first_key_in_overall_cycle, key_loop_initial_run


def is_full_cycle_completed(
    first_key_in_overall_cycle: Optional[str],
    previous_key: Optional[str],
    current_key_after_rotation: Optional[str],
) -> bool:
    return (
        current_key_after_rotation is not None
        and current_key_after_rotation == first_key_in_overall_cycle
        and current_key_after_rotation != previous_key
    )


def rotate_key_and_detect_full_cycle(
    api_key_manager: Any,
    service_name: str,
    first_key_in_overall_cycle: Optional[str],
    previous_key: Optional[str],
) -> Tuple[bool, bool]:
    if not api_key_manager.rotate_key(service_name):
        return False, False
    current_key_after_rotation = api_key_manager.get_key(service_name, peek=True)
    return True, is_full_cycle_completed(first_key_in_overall_cycle, previous_key, current_key_after_rotation)
