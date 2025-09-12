from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

_RE = re.compile


# Core robotics signals
CORE_PATTERNS = _RE(r"\b(ros2?|robot(?:ique|ics)?|move ?it2?|gazebo(?: sim| ignition)?|urdf|xacro|tf2|nav2|navigation2|rclcpp|rclpy|colcon|ament|pcl|slam|navigation|opencv|perception)\b", re.I)

# Adjacent categories with simple keyword patterns
ADJACENT_MAP: List[Tuple[str, re.Pattern]] = [
    ("automatisme", _RE(r"\b(automatisme|automaticien|automatismes|plc|grafcet|tia|twincat)\b", re.I)),
    ("vision_industrielle", _RE(r"\b(vision industrielle|opencv|halcon)\b", re.I)),
    ("maintenance_robot", _RE(r"\b(maintenance).*(robot)|robot.*maintenance|\bSAV\b", re.I)),
    ("ivvq_test", _RE(r"\b(ivvq|validation|int[eé]gration|tests?)\b", re.I)),
    ("cobot", _RE(r"\b(cobot|collaboratif|ur\b|universal robots)\b", re.I)),
    ("agv_amr", _RE(r"\b(agv|amr|mobile robot)\b", re.I)),
    ("machine_speciale", _RE(r"\b(machine sp[eé]ciale|int[eé]gration (ligne|ilot)|ilot robotis[eé])\b", re.I)),
]

# Tech tags
PLC_TAGS: List[Tuple[str, re.Pattern]] = [
    ("plc_siemens", _RE(r"\b(siemens|tia ?portal)\b", re.I)),
    ("plc_beckhoff", _RE(r"\b(beckhoff|twincat)\b", re.I)),
    ("plc_rockwell", _RE(r"\b(rockwell|allen[- ]?bradley)\b", re.I)),
]

LANG_TAGS: List[Tuple[str, re.Pattern]] = [
    ("c++", _RE(r"\bc\+\+\b|\bcpp\b", re.I)),
    ("python", _RE(r"\bpython\b", re.I)),
    ("c", _RE(r"\bc\b(?!\+)")),
    ("matlab", _RE(r"\bmatlab\b", re.I)),
]

SENSOR_TAGS: List[Tuple[str, re.Pattern]] = [
    ("lidar", _RE(r"\blidar\b", re.I)),
    ("camera", _RE(r"\b(camera|cam[eé]ra|rgbd|rgb-d)\b", re.I)),
    ("imu", _RE(r"\bimu\b", re.I)),
]

# Vision libraries / vendors
VISION_LIBS: List[Tuple[str, re.Pattern]] = [
    ("opencv", _RE(r"\bopencv\b", re.I)),
    ("halcon", _RE(r"\bhalcon\b", re.I)),
    ("cognex", _RE(r"\bcognex\b", re.I)),
    ("keyence", _RE(r"\bkeyence\b", re.I)),
]

# Robot brands
ROBOT_BRANDS: List[Tuple[str, re.Pattern]] = [
    ("fanuc", _RE(r"\bfanuc\b", re.I)),
    ("abb", _RE(r"\babb\b", re.I)),
    ("kuka", _RE(r"\bkuka\b", re.I)),
    ("staubli", _RE(r"\bst[äa]ubli\b", re.I)),
    ("yaskawa", _RE(r"\byaskawa\b", re.I)),
    ("universal_robots", _RE(r"\b(universal robots|ur\b)\b", re.I)),
    ("omron", _RE(r"\bomron\b", re.I)),
    ("mir", _RE(r"\b(mobile industrial robots|\bmir\b)\b", re.I)),
    ("clearpath", _RE(r"\bclearpath\b", re.I)),
    ("doosan", _RE(r"\bdoosan\b", re.I)),
]


def _present(text: str, pat: re.Pattern) -> bool:
    return bool(pat.search(text))


def detect_core(text: str) -> bool:
    return _present(text, CORE_PATTERNS)


def detect_adjacent(text: str) -> List[str]:
    out: List[str] = []
    for name, pat in ADJACENT_MAP:
        if _present(text, pat):
            out.append(name)
    return out


def detect_remote(text: str) -> bool:
    return bool(re.search(r"\b(t[eé]l[eé]travail|remote|hybride)\b", text, flags=re.I))


def detect_seniority(text: str) -> str:
    if re.search(r"\b(junior|d[eé]butant)\b", text, re.I):
        return "junior"
    if re.search(r"\b(1 ?- ?3 ?ans|1\s*[àa]\s*3\s*ans)\b", text, re.I):
        return "1-3 ans"
    if re.search(r"\b(3 ?- ?5 ?ans|3\s*[àa]\s*5\s*ans)\b", text, re.I):
        return "3-5 ans"
    if re.search(r"\b(5\+?\s*ans|5\s*ans|senior|lead|expert)\b", text, re.I):
        return "5+ ans/senior"
    return "unspecified"


def detect_plc(text: str) -> List[str]:
    out: List[str] = []
    for tag, pat in PLC_TAGS:
        if _present(text, pat):
            out.append(tag)
    return out


def detect_langs(text: str) -> List[str]:
    out: List[str] = []
    for tag, pat in LANG_TAGS:
        if _present(text, pat):
            out.append(tag)
    return out


def detect_sensors(text: str) -> List[str]:
    out: List[str] = []
    for tag, pat in SENSOR_TAGS:
        if _present(text, pat):
            out.append(tag)
    return out


AGENCY_PAT = _RE(r"\b(cabinet|recrut|int[eé]rim|esn|ssii|agence)\b", re.I)


def detect_agency(company: str | None, text: str) -> bool:
    if company and AGENCY_PAT.search(company):
        return True
    return bool(AGENCY_PAT.search(text or ""))


def compute_labels(row: Dict[str, Any]) -> Dict[str, Any]:
    text = " ".join([
        str(row.get("title", "")),
        str(row.get("description", "")),
    ])
    company = str(row.get("company") or "")

    core = detect_core(text)
    adjacent = detect_adjacent(text)
    remote = detect_remote(text)
    seniority = detect_seniority(text)
    plc = detect_plc(text)
    langs = detect_langs(text)
    sensors = detect_sensors(text)
    agency = detect_agency(company, text)
    # vision libs and brands
    vis = [tag for tag, pat in VISION_LIBS if _present(text, pat)]
    brands = [tag for tag, pat in ROBOT_BRANDS if _present(text, pat)]
    # ros stack tags
    ros_stack = []
    for tag, pat in [
        ("ros2", _RE(r"\bros ?2\b|\bros2\b", re.I)),
        ("ros1", _RE(r"\bros\b(?!\s?2)", re.I)),
        ("moveit", _RE(r"\bmove ?it2?\b", re.I)),
        ("gazebo", _RE(r"\bgazebo(?: sim| ignition)?\b", re.I)),
        ("nav2", _RE(r"\bnav2|navigation2\b", re.I)),
        ("tf2", _RE(r"\btf2\b", re.I)),
        ("urdf", _RE(r"\burdf|xacro\b", re.I)),
        ("pcl", _RE(r"\bpcl\b", re.I)),
        ("rclcpp", _RE(r"\brclcpp\b", re.I)),
        ("rclpy", _RE(r"\brclpy\b", re.I)),
        ("colcon", _RE(r"\bcolcon\b", re.I)),
        ("ament", _RE(r"\bament\b", re.I)),
    ]:
        if _present(text, pat):
            ros_stack.append(tag)

    return {
        "CORE_ROBOTICS": core,
        "ADJACENT_CATEGORIES": adjacent,
        "REMOTE": remote,
        "SENIORITY": seniority,
        "PLC_TAGS": plc,
        "LANG_TAGS": langs,
        "SENSOR_TAGS": sensors,
        "AGENCY": agency,
        "VISION_LIBS": vis,
        "ROBOT_BRANDS": brands,
        "ROS_STACK": ros_stack,
    }
