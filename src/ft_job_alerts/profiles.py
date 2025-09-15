from __future__ import annotations

"""
Centralized, configurable categories/domains for GUI/TUI presets.

Behavior
- Loads an optional JSON file (default: data/profiles.json) describing
  categories, domains and a default profile.
- Falls back to built-in defaults if the file is missing or invalid.

Schema (JSON)
{
  "categories": [{"name": "Robotique / ROS", "keywords": ["ros2","ros",...]}, ...],
  "domains": [{"name": "Robotique (ROS/vision)", "keywords": ["ros2","ros","vision","c++"]}, ...],
  "default_profile": {
    "domain": "Robotique (ROS/vision)",
    "selected_categories": ["Robotique / ROS", "Vision industrielle", ...],
    "extra_keywords": ["ros2","c++","vision"],
    "dept": "68",
    "distance_km": 50,
    "published_since_days": 7,
    "topn": 100,
    "export_format": "md",
    "full_description": true,
    "min_salary_monthly": null
  }
}
"""

import json
import os
from typing import Any, List, Tuple, Dict


def _builtin_categories() -> List[Tuple[str, List[str]]]:
    # Keep concise, composable buckets for France Travail keyword search
    return [
        ("Robotique / ROS", ["ros2", "ros", "robotique", "robot"]),
        ("Vision industrielle", ["vision", "opencv", "halcon", "cognex", "keyence"]),
        ("Navigation / SLAM", ["navigation", "slam", "path planning"]),
        ("ROS stack", ["moveit", "nav2", "gazebo", "urdf", "tf2", "pcl", "rclcpp", "rclpy", "colcon", "ament"]),
        ("Marques robots", ["fanuc", "abb", "kuka", "staubli", "yaskawa", "ur"]),
        ("Automatisme / PLC", ["automatisme", "plc", "grafcet", "siemens", "twincat"]),
        ("Capteurs", ["lidar", "camera", "imu"]),
        ("Langages", ["c++", "python"]),
        # Extra buckets often useful to triage the market
        ("AGV / AMR / Mobile", ["agv", "amr", "mobile robot", "fleet manager"]),
        ("IVVQ / Validation / Test", ["ivvq", "validation", "intégration", "tests", "verification"]),
        ("Embarqué / Temps réel", ["embarqué", "temps réel", "rtos", "stm32", "microcontrôleur"]),
        ("Intégration / Machines spéciales", ["machine spéciale", "intégration", "îlot robotisé", "îlot robotise"]),
    ]


def _builtin_domains() -> List[Tuple[str, List[str]]]:
    return [
        ("Custom (libre)", []),
        ("Robotique (ROS/vision)", ["ros2", "ros", "robotique", "vision", "c++"]),
        ("Software (général)", ["python", "java", "javascript", "backend", "fullstack"]),
        ("Data / IA", ["data", "python", "pandas", "sql", "machine learning"]),
        ("Automatisme / PLC", ["automatisme", "plc", "siemens", "twincat", "grafcet"]),
        ("Logistique", ["logistique", "supply chain", "magasinier", "cariste"]),
        ("Finance / Comptabilité", ["comptable", "audit", "finance"]),
        ("Santé", ["infirmier", "infirmière", "aide soignant"]),
    ]


def _load_json(path: str) -> Dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_profiles_config() -> tuple[List[Tuple[str, List[str]]], List[Tuple[str, List[str]]], Dict[str, Any] | None, Dict[str, Dict[str, Any]], Dict[str, List[Tuple[str, List[str]]]]]:
    path = os.getenv("PROFILES_PATH", os.path.join("data", "profiles.json"))
    data = _load_json(path)
    if not data:
        # No custom file: global categories available for robotics domain
        dom_map = {"Robotique (ROS/vision)": _builtin_categories()}
        return _builtin_categories(), _builtin_domains(), None, {}, dom_map

    def _coerce_pairs(items: Any) -> List[Tuple[str, List[str]]]:
        out: List[Tuple[str, List[str]]] = []
        if not isinstance(items, list):
            return out
        for it in items:
            if isinstance(it, dict):
                name = str(it.get("name", "")).strip()
                kws = [str(k).strip() for k in it.get("keywords", []) if str(k).strip()]
                if name:
                    out.append((name, kws))
            elif isinstance(it, (list, tuple)) and len(it) == 2 and isinstance(it[1], (list, tuple)):
                out.append((str(it[0]), [str(k).strip() for k in it[1] if str(k).strip()]))
        return out

    cats = _coerce_pairs(data.get("categories")) or _builtin_categories()
    doms = _coerce_pairs(data.get("domains")) or _builtin_domains()
    default_profile = data.get("default_profile") if isinstance(data.get("default_profile"), dict) else None
    profiles = data.get("profiles") if isinstance(data.get("profiles"), dict) else {}
    # Ensure all profiles are dicts
    profiles = {str(k): v for k, v in profiles.items() if isinstance(v, dict)} if profiles else {}
    # Domain-specific categories mapping (optional)
    dom_cats_raw = data.get("domain_categories") if isinstance(data.get("domain_categories"), dict) else {}
    dom_cats: Dict[str, List[Tuple[str, List[str]]]] = {}
    for dom_name, items in (dom_cats_raw or {}).items():
        try:
            dom_cats[str(dom_name)] = [
                (str(it.get("name", "")).strip(), [str(k).strip() for k in it.get("keywords", []) if str(k).strip()])
                for it in items if isinstance(it, dict)
            ]
        except Exception:
            continue
    # Fallback: if robotics domain exists and not present in map, attach builtin categories
    for name, _ in doms:
        if name.lower().startswith("robotique") and name not in dom_cats:
            dom_cats[name] = _builtin_categories()
    return cats, doms, default_profile, profiles, dom_cats


def get_categories() -> List[Tuple[str, List[str]]]:
    cats, _doms, _prof, _profiles, _dom_map = load_profiles_config()
    return cats


def get_domains() -> List[Tuple[str, List[str]]]:
    _cats, doms, _prof, _profiles, _dom_map = load_profiles_config()
    return doms


def list_profiles() -> Dict[str, Dict[str, Any]]:
    _cats, _doms, _prof, profiles, _dom_map = load_profiles_config()
    return profiles


def get_profile_by_name(name: str) -> Dict[str, Any] | None:
    return list_profiles().get(name)


def get_default_profile(name_override: str | None = None) -> Dict[str, Any] | None:
    if name_override:
        return get_profile_by_name(name_override)
    _cats, _doms, prof, _profiles, _dom_map = load_profiles_config()
    return prof


def build_keywords_from_profile(profile: Dict[str, Any]) -> List[str]:
    """Compose a deduplicated keyword list from selected categories and extra keywords."""
    cats = get_categories()
    cat_map = {label: kws for label, kws in cats}
    kws: List[str] = []
    for name in profile.get("selected_categories", []) or []:
        if name in cat_map:
            kws.extend(cat_map[name])
    extra = profile.get("extra_keywords", []) or []
    if isinstance(extra, list):
        kws.extend([str(k).strip() for k in extra if str(k).strip()])
    seen = set()
    return [k for k in kws if not (k in seen or seen.add(k))]


def get_domain_categories_map() -> Dict[str, List[Tuple[str, List[str]]]]:
    _cats, _doms, _prof, _profiles, dom_map = load_profiles_config()
    return dom_map
