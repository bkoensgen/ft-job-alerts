from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Iterable, List, Tuple, Dict


_RE_TOKEN = re.compile(r"[a-zA-Z][a-zA-Z0-9+_\-/]{1,}")


STOPWORDS_FR_EN = set(
    [
        # French
        "le","la","les","un","une","des","du","de","d","au","aux","et","en","dans","sur","avec","pour","par","ou","où","que","qui","quoi","dont","cela","cette","cet","ce","ces","son","sa","ses","leur","leurs","nos","notre","vos","votre","plus","moins","très","tres","bien","a","à","est","sont","être","etes","etes","été","etre","fait","faire","afin","ainsi","entre","chez","vers","sans","sous","fois","ans","jours",
        # English
        "the","a","an","and","or","of","to","in","on","for","from","by","as","is","are","be","been","this","that","these","those","it","its","at","we","you","they","our","your","their","will","can","may","more","most","less","very","good","strong","ability","skills","experience","experiences",
        # Job boilerplate FR
        "vous","nous","poste","profil","mission","missions","client","clients","candidat","candidature","recherche","recherchons","souhaitez","justifiez","intervenez","assurer","assurez","realiser","realisez","participer","participerez","selon","niveau","horaire","horaires","cdi","cdd","interim","h/f","hf","de","d'","l'","au","aux","ans","mois","semaine","jour","jours","souhait","souhaite","souhaitees","souhaitees","souhaitee","souhaitez",
        # Job boilerplate EN
        "position","role","responsibilities","responsibility","requirements","apply","applicant","candidate","team","work","working","ensure","ensuring","perform","performing","according","based","within","environment",
    ]
)


def normalize_text(text: str) -> str:
    t = text or ""
    # Lower + remove diacritics
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii", "ignore").lower()
    # Common merges
    t = re.sub(r"\bros\s*2\b", "ros2", t)
    t = re.sub(r"\bmove\s*it\s*2?\b", "moveit", t)
    t = re.sub(r"\btia\s*portal\b", "tia portal", t)
    t = re.sub(r"\btwin\s*cat\b", "twincat", t)
    t = re.sub(r"c\+\+", "c++", t)
    return t


def build_stopwords(extra: Iterable[str] | None = None) -> set[str]:
    base = set(STOPWORDS_FR_EN)
    if extra:
        for w in extra:
            if not w:
                continue
            base.add(normalize_text(w))
    return base


def tokenize(text: str, *, keep: Iterable[str] | None = None, extra_stops: Iterable[str] | None = None) -> List[str]:
    t = normalize_text(text)
    toks = _RE_TOKEN.findall(t)
    out: List[str] = []
    keep_set = set(keep or [])
    stops = build_stopwords(extra_stops)
    for tok in toks:
        if tok in keep_set:
            out.append(tok)
            continue
        if tok in stops:
            continue
        if len(tok) <= 1:
            continue
        if tok.isdigit():
            continue
        out.append(tok)
    return out


def bigrams(tokens: List[str]) -> List[Tuple[str, str]]:
    return [(tokens[i], tokens[i + 1]) for i in range(len(tokens) - 1)]


def log_odds_with_prior(
    counts_a: Counter,
    counts_b: Counter,
    alpha: float = 0.01,
) -> List[Tuple[str, float, float]]:
    """
    Monroe et al. (2008) log-odds with informative Dirichlet prior (uniform alpha).
    Returns list of (token, z_score, delta) where z>0 => associated with group A.
    """
    vocab = set(counts_a.keys()) | set(counts_b.keys())
    n_a = sum(counts_a.values())
    n_b = sum(counts_b.values())
    alpha_0 = alpha * len(vocab) if vocab else 1.0
    out: List[Tuple[str, float, float]] = []
    if n_a == 0 or n_b == 0:
        return [(t, 0.0, 0.0) for t in vocab]
    for t in vocab:
        y_a = counts_a.get(t, 0)
        y_b = counts_b.get(t, 0)
        num_a = y_a + alpha
        den_a = (n_a - y_a) + (alpha_0 - alpha)
        num_b = y_b + alpha
        den_b = (n_b - y_b) + (alpha_0 - alpha)
        logit_a = math.log(num_a / den_a)
        logit_b = math.log(num_b / den_b)
        delta = logit_a - logit_b
        var = 1.0 / (y_a + alpha) + 1.0 / (y_b + alpha)
        z = delta / math.sqrt(var)
        out.append((t, z, delta))
    # sort by z desc
    out.sort(key=lambda x: x[1], reverse=True)
    return out
