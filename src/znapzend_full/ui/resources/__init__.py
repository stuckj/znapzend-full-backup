"""Resources for znapzend-full UI."""

from pathlib import Path

RESOURCES_DIR = Path(__file__).parent
ICONS_DIR = RESOURCES_DIR / "icons"


def get_icon_path(name: str) -> Path:
    """Get the path to an icon file.

    Args:
        name: Icon name without extension (e.g., 'idle', 'backing_up').

    Returns:
        Path to the SVG icon file.
    """
    return ICONS_DIR / f"{name}.svg"
