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


def load_profiles_config() -> tuple[List[Tuple[str, List[str]]], List[Tuple[str, List[str]]], Dict[str, Any] | None]:
    path = os.getenv("PROFILES_PATH", os.path.join("data", "profiles.json"))
    data = _load_json(path)
    if not data:
        return _builtin_categories(), _builtin_domains(), None

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
    return cats, doms, default_profile


def get_categories() -> List[Tuple[str, List[str]]]:
    cats, _doms, _prof = load_profiles_config()
    return cats


def get_domains() -> List[Tuple[str, List[str]]]:
    _cats, doms, _prof = load_profiles_config()
    return doms


def get_default_profile() -> Dict[str, Any] | None:
    _cats, _doms, prof = load_profiles_config()
    return prof

