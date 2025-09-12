from __future__ import annotations

import re
from typing import Iterable


# Basic keyword filters for robotics/ROS2/C++/vision oriented queries.
MUST_ANY = [
    r"\bros ?2\b",
    r"\bros2\b",
    r"\bros\b",
    r"\brobot(?:ique|ics)?\b",
    r"\bvision\b",
    r"\bc\+\+\b",
    r"\bperception\b",
    r"\bnavigation\b",
    r"\bslam\b",
    r"\bopencv\b",
    r"\bmoveit\b",
]

EXCLUDE = [
    r"\bcommercial\b",
    r"\btechnico-commercial\b",
    r"\bvendeur\b",
    r"\bchauffeur\b",
    r"\bserveur\b",
    r"\blogistique\b",
]


def _match_any(patterns: Iterable[str], text: str) -> bool:
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE):
            return True
    return False


def is_relevant(title: str, description: str | None) -> bool:
    text = f"{title}\n{description or ''}"
    if not _match_any(MUST_ANY, text):
        return False
    if _match_any(EXCLUDE, text):
        return False
    return True

