# -*- coding: utf-8 -*-
"""
conflict_guard.py
-----------------
Βήμα 0 / κοινός φύλακας δηλωμένων συγκρούσεων.

Σκοπός:
- Διαβάζει τη στήλη ΣΥΓΚΡΟΥΣΗ.
- Μετατρέπει τις δηλωμένες συγκρούσεις σε απαγορευμένα ζεύγη συνύπαρξης.
- Ελέγχει τοποθετήσεις, swaps και τελικά σενάρια.
- Χρησιμοποιεί την ίδια λογική κανονικοποίησης ονομάτων με το app.py:
  strip, συμπίεση κενών, αφαίρεση τόνων/διακριτικών, uppercase.
- Δεν αγνοεί σιωπηλά ονόματα που δεν αναγνωρίζονται:
  τα επιστρέφει ως unresolved για έλεγχο ποιότητας δεδομένων.

Οι δηλωμένες/εξωτερικές συγκρούσεις είναι HARD CONSTRAINT:
αν δύο μαθητές βρίσκονται σε conflict_pairs, δεν επιτρέπεται να είναι στο ίδιο τμήμα.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple
import re
import ast
import unicodedata
import warnings

import pandas as pd


# ----------------------------
# Data structures
# ----------------------------

@dataclass(frozen=True)
class UnresolvedConflictName:
    """Δηλωμένο όνομα στη ΣΥΓΚΡΟΥΣΗ που δεν αντιστοιχίστηκε σε μαθητή."""
    source_student: str
    declared_name: str
    source_student_canon: str
    declared_name_canon: str
    reason: str = "not_found"


@dataclass(frozen=True)
class ConflictExtraction:
    """
    Αποτέλεσμα εξαγωγής συγκρούσεων.

    pairs:
        Ζεύγη σε canonical μορφή, π.χ. ("ΓΙΑΝΝΗΣ ΠΑΠΑΔΟΠΟΥΛΟΣ", "ΜΑΡΙΑ ΚΥΠΡΟΥ").
        Αυτά χρησιμοποιούνται για τους ελέγχους.
    pair_originals:
        Ίδια ζεύγη σε εμφανίσιμη αρχική μορφή.
    unresolved:
        Ονόματα που γράφτηκαν στη ΣΥΓΚΡΟΥΣΗ αλλά δεν βρέθηκαν αξιόπιστα.
    conflict_col:
        Η στήλη που χρησιμοποιήθηκε ως στήλη συγκρούσεων.
    canon_to_original:
        Αντιστοίχιση canonical ονόματος σε αρχικό εμφανίσιμο όνομα.
    """
    pairs: frozenset[Tuple[str, str]] = field(default_factory=frozenset)
    pair_originals: Tuple[Tuple[str, str], ...] = tuple()
    unresolved: Tuple[UnresolvedConflictName, ...] = tuple()
    conflict_col: Optional[str] = None
    canon_to_original: Dict[str, str] = field(default_factory=dict)


# ----------------------------
# Name normalization / matching
# ----------------------------

def strip_diacritics(s: str) -> str:
    """Αφαιρεί τόνους/διακριτικά από ελληνικά και λατινικά γράμματα."""
    nfkd = unicodedata.normalize("NFD", str(s))
    return "".join(ch for ch in nfkd if not unicodedata.combining(ch))


def canon_name(x: Any) -> str:
    """
    Ενιαία κανονικοποίηση ονόματος.

    Συμβατή με τη λογική του app.py:
    - strip
    - αφαίρεση brackets/quotes
    - συμπίεση πολλών κενών
    - αφαίρεση διακριτικών/τόνων
    - uppercase
    """
    if x is None:
        return ""
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass

    s = str(x).strip()
    s = s.strip("[]'\" ")
    s = re.sub(r"\s+", " ", s)
    s = strip_diacritics(s).upper()
    return s


# Backwards-compatible alias, αν κάποιο βήμα καλεί norm_name().
def norm_name(x: Any) -> str:
    return canon_name(x)


def tokenize_canon_name(canon: str) -> List[str]:
    """Tokenization για fuzzy matching."""
    return [t for t in re.split(r"[^A-ZΑ-Ω0-9]+", str(canon)) if t]


def best_name_match(
    target_canon: str,
    candidate_canons: Sequence[str],
    *,
    min_score: float = 0.34,
) -> Optional[str]:
    """
    Fuzzy αντιστοίχιση όπως στο app.py περίπου:
    Jaccard similarity σε tokens + μικρό bonus για prefix overlap.
    """
    target_canon = canon_name(target_canon)
    if not target_canon:
        return None

    candidates = list(candidate_canons)
    if target_canon in candidates:
        return target_canon

    tks = set(tokenize_canon_name(target_canon))
    if not tks:
        return None

    best = None
    best_score = 0.0

    for cand in candidates:
        cand = canon_name(cand)
        cks = set(tokenize_canon_name(cand))
        if not cks:
            continue

        inter = tks & cks
        union = tks | cks
        jacc = len(inter) / max(1, len(union))
        prefix_bonus = 0.0

        if inter:
            prefix_bonus = 0.2 if any(
                cand.startswith(tok) or target_canon.startswith(tok)
                for tok in inter
            ) else 0.0

        score = jacc + prefix_bonus
        if score > best_score:
            best = cand
            best_score = score

    return best if best is not None and best_score >= min_score else None


# ----------------------------
# Parsing / columns
# ----------------------------

SAFE_SEP = re.compile(r"[,;|/·\n]+")

CONFLICT_COL_CANDIDATES = (
    "ΣΥΓΚΡΟΥΣΗ",
    "ΣΥΓΚΡΟΥΣΕΙΣ",
    "ΣΥΓΚΡΟΥΣΗ/CONFLICT",
    "CONFLICT",
    "CONFLICTS",
)


def parse_name_list(value: Any) -> List[str]:
    """Ασφαλές parsing λίστας ονομάτων από κελί Excel."""
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass

    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        s = str(value).strip()
        if not s or s.lower() in {"nan", "none", "null", "-"}:
            return []

        try:
            parsed = ast.literal_eval(s)
            if isinstance(parsed, (list, tuple, set)):
                raw_values = list(parsed)
            else:
                raw_values = SAFE_SEP.split(s)
        except Exception:
            raw_values = SAFE_SEP.split(s)

    out = []
    for x in raw_values:
        sx = str(x).strip()
        if sx and sx.lower() not in {"nan", "none", "null"}:
            out.append(sx)
    return out


# Backwards-compatible alias, επειδή στα βήματα υπάρχει συχνά parse_friends_cell().
def parse_friends_cell(value: Any) -> List[str]:
    return parse_name_list(value)


def choose_conflict_col(
    df: pd.DataFrame,
    *,
    warn_if_missing: bool = True,
) -> Optional[str]:
    """Επιλέγει τη στήλη συγκρούσεων με ανεκτικότητα σε παραλλαγές ονόματος."""
    if df is None or df.empty:
        if warn_if_missing:
            warnings.warn("Δεν δόθηκε DataFrame ή είναι κενό. Δεν μπορεί να ελεγχθεί στήλη ΣΥΓΚΡΟΥΣΗ.")
        return None

    exact = {str(c).strip(): c for c in df.columns}
    for cand in CONFLICT_COL_CANDIDATES:
        if cand in exact:
            return exact[cand]

    for c in df.columns:
        cc = str(c).strip().upper()
        if "ΣΥΓΚΡΟΥ" in cc or "CONFLICT" in cc:
            return c

    if warn_if_missing:
        warnings.warn(
            "Δεν βρέθηκε στήλη ΣΥΓΚΡΟΥΣΗ/ΣΥΓΚΡΟΥΣΕΙΣ. "
            "Οι δηλωμένες συγκρούσεις δεν μπορούν να εφαρμοστούν ως hard constraint."
        )
    return None


def _build_name_maps(
    df: pd.DataFrame,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> Tuple[Dict[str, str], Set[str]]:
    if name_col not in df.columns:
        raise ValueError(f"Λείπει η στήλη ονόματος: {name_col}")

    canon_to_original: Dict[str, str] = {}
    for raw in df[name_col].astype(str).tolist():
        c = canon_name(raw)
        if c and c not in canon_to_original:
            canon_to_original[c] = str(raw).strip()

    return canon_to_original, set(canon_to_original.keys())


def _sorted_pair(a: str, b: str) -> Tuple[str, str]:
    a = canon_name(a)
    b = canon_name(b)
    return tuple(sorted((a, b)))


# ----------------------------
# Conflict extraction
# ----------------------------

def extract_conflict_data(
    df: pd.DataFrame,
    *,
    name_col: str = "ΟΝΟΜΑ",
    conflict_col: Optional[str] = None,
    fuzzy: bool = True,
    warn_if_missing_col: bool = True,
    warn_unresolved: bool = True,
) -> ConflictExtraction:
    """
    Εξάγει δηλωμένες συγκρούσεις για ΟΛΟΥΣ τους μαθητές.

    Μονόπλευρη δήλωση αρκεί:
    αν ο Α γράφει τον Β στη ΣΥΓΚΡΟΥΣΗ, το ζεύγος Α-Β θεωρείται απαγορευμένο.
    """
    df = df.copy()
    canon_to_original, all_canons = _build_name_maps(df, name_col=name_col)

    col = conflict_col or choose_conflict_col(df, warn_if_missing=warn_if_missing_col)
    if col is None:
        return ConflictExtraction(
            pairs=frozenset(),
            pair_originals=tuple(),
            unresolved=tuple(),
            conflict_col=None,
            canon_to_original=canon_to_original,
        )

    pairs: Set[Tuple[str, str]] = set()
    unresolved: List[UnresolvedConflictName] = []

    for _, row in df.iterrows():
        source_raw = str(row.get(name_col, "")).strip()
        source_canon = canon_name(source_raw)
        if not source_canon:
            continue

        for declared_raw in parse_name_list(row.get(col, "")):
            declared_canon = canon_name(declared_raw)

            if not declared_canon or declared_canon == source_canon:
                continue

            resolved = declared_canon if declared_canon in all_canons else None

            if resolved is None and fuzzy:
                resolved = best_name_match(declared_canon, list(all_canons))

            if resolved is None:
                unresolved.append(
                    UnresolvedConflictName(
                        source_student=source_raw,
                        declared_name=str(declared_raw).strip(),
                        source_student_canon=source_canon,
                        declared_name_canon=declared_canon,
                        reason="not_found",
                    )
                )
                continue

            if resolved != source_canon:
                pairs.add(_sorted_pair(source_canon, resolved))

    pair_originals = tuple(
        tuple(canon_to_original.get(x, x) for x in p)
        for p in sorted(pairs)
    )

    if warn_unresolved and unresolved:
        msg = (
            "Υπάρχουν ονόματα στη στήλη ΣΥΓΚΡΟΥΣΗ που δεν αναγνωρίστηκαν: "
            + "; ".join(
                f"{u.source_student} -> {u.declared_name}"
                for u in unresolved[:10]
            )
        )
        if len(unresolved) > 10:
            msg += f" ... (+{len(unresolved)-10} ακόμη)"
        warnings.warn(msg)

    return ConflictExtraction(
        pairs=frozenset(pairs),
        pair_originals=pair_originals,
        unresolved=tuple(unresolved),
        conflict_col=str(col),
        canon_to_original=canon_to_original,
    )


def extract_conflict_pairs(
    df: pd.DataFrame,
    *,
    name_col: str = "ΟΝΟΜΑ",
    conflict_col: Optional[str] = None,
    fuzzy: bool = True,
) -> frozenset[Tuple[str, str]]:
    """
    Backwards-compatible συνάρτηση.
    Επιστρέφει μόνο τα canonical conflict pairs.
    Για unresolved/report χρησιμοποίησε extract_conflict_data().
    """
    return extract_conflict_data(
        df,
        name_col=name_col,
        conflict_col=conflict_col,
        fuzzy=fuzzy,
    ).pairs


# ----------------------------
# Assignment checks
# ----------------------------

def _name_to_class_map(
    df: pd.DataFrame,
    scenario_col: str,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> Dict[str, str]:
    if name_col not in df.columns:
        raise ValueError(f"Λείπει η στήλη {name_col}.")
    if scenario_col not in df.columns:
        raise ValueError(f"Λείπει η στήλη σεναρίου {scenario_col}.")

    out: Dict[str, str] = {}
    for _, row in df.iterrows():
        n = canon_name(row.get(name_col, ""))
        cl = row.get(scenario_col)
        if n and pd.notna(cl) and str(cl).strip():
            out[n] = str(cl).strip()
    return out


def list_conflict_violations(
    df: pd.DataFrame,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> pd.DataFrame:
    """Επιστρέφει DataFrame με τα ζεύγη που βρίσκονται παράνομα στο ίδιο τμήμα."""
    data = extract_conflict_data(df, name_col=name_col) if conflict_pairs is None else None
    pairs = set(conflict_pairs) if conflict_pairs is not None else set(data.pairs)
    canon_to_original = data.canon_to_original if data is not None else _build_name_maps(df, name_col=name_col)[0]

    name2class = _name_to_class_map(df, scenario_col, name_col=name_col)

    rows = []
    for a, b in sorted(pairs):
        a = canon_name(a)
        b = canon_name(b)
        ca = name2class.get(a)
        cb = name2class.get(b)
        if ca and cb and ca == cb:
            rows.append({
                "ΜΑΘΗΤΗΣ_A": canon_to_original.get(a, a),
                "ΜΑΘΗΤΗΣ_B": canon_to_original.get(b, b),
                "ΤΜΗΜΑ": ca,
                "ΣΕΝΑΡΙΟ": scenario_col,
            })
    return pd.DataFrame(rows)


def count_conflict_violations(
    df: pd.DataFrame,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> int:
    return int(len(list_conflict_violations(
        df,
        scenario_col,
        conflict_pairs=conflict_pairs,
        name_col=name_col,
    )))


def has_conflict_violation(
    df: pd.DataFrame,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> bool:
    return count_conflict_violations(
        df,
        scenario_col,
        conflict_pairs=conflict_pairs,
        name_col=name_col,
    ) > 0


def forbidden_classes_for_student(
    df: pd.DataFrame,
    student_name: str,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> Set[str]:
    """
    Επιστρέφει τα τμήματα που απαγορεύονται για έναν μαθητή,
    επειδή ήδη εκεί βρίσκεται κάποιος με τον οποίο έχει δηλωμένη σύγκρουση.
    """
    pairs = set(conflict_pairs) if conflict_pairs is not None else set(extract_conflict_pairs(df, name_col=name_col))
    student_c = canon_name(student_name)
    name2class = _name_to_class_map(df, scenario_col, name_col=name_col)

    forbidden: Set[str] = set()
    for a, b in pairs:
        a = canon_name(a)
        b = canon_name(b)
        if student_c == a and b in name2class:
            forbidden.add(name2class[b])
        elif student_c == b and a in name2class:
            forbidden.add(name2class[a])
    return forbidden


def can_place_student(
    df: pd.DataFrame,
    student_name: str,
    target_class: str,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> bool:
    """
    True αν ο μαθητής μπορεί να τοποθετηθεί στο target_class
    χωρίς να δημιουργήσει δηλωμένη σύγκρουση.
    """
    target = str(target_class).strip()
    if not target:
        return False
    return target not in forbidden_classes_for_student(
        df,
        student_name,
        scenario_col,
        conflict_pairs=conflict_pairs,
        name_col=name_col,
    )


def filter_valid_scenario_cols(
    df: pd.DataFrame,
    scenario_cols: Sequence[str],
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> List[str]:
    """
    Για Βήμα 7/app:
    κρατά μόνο στήλες σεναρίων που έχουν μηδενικές δηλωμένες συγκρούσεις.
    """
    pairs = set(conflict_pairs) if conflict_pairs is not None else set(extract_conflict_pairs(df, name_col=name_col))
    valid = []
    for col in scenario_cols:
        if col in df.columns and not has_conflict_violation(df, col, conflict_pairs=pairs, name_col=name_col):
            valid.append(col)
    return valid


def assert_no_conflicts(
    df: pd.DataFrame,
    scenario_col: str,
    conflict_pairs: Optional[Iterable[Tuple[str, str]]] = None,
    *,
    name_col: str = "ΟΝΟΜΑ",
) -> None:
    """Σηκώνει ValueError αν υπάρχουν δηλωμένες συγκρούσεις στο σενάριο."""
    viol = list_conflict_violations(
        df,
        scenario_col,
        conflict_pairs=conflict_pairs,
        name_col=name_col,
    )
    if not viol.empty:
        details = "; ".join(
            f"{r['ΜΑΘΗΤΗΣ_A']} - {r['ΜΑΘΗΤΗΣ_B']} στο {r['ΤΜΗΜΑ']}"
            for _, r in viol.iterrows()
        )
        raise ValueError(
            f"Το σενάριο {scenario_col} έχει δηλωμένες συγκρούσεις: {details}"
        )


def unresolved_to_dataframe(data: ConflictExtraction) -> pd.DataFrame:
    """Μετατρέπει τα unresolved σε DataFrame για report/export."""
    return pd.DataFrame([
        {
            "ΜΑΘΗΤΗΣ_ΠΗΓΗ": u.source_student,
            "ΔΗΛΩΜΕΝΟ_ΟΝΟΜΑ_ΣΥΓΚΡΟΥΣΗΣ": u.declared_name,
            "CANON_ΠΗΓΗ": u.source_student_canon,
            "CANON_ΔΗΛΩΜΕΝΟΥ": u.declared_name_canon,
            "ΑΙΤΙΑ": u.reason,
        }
        for u in data.unresolved
    ])


def conflict_pairs_to_dataframe(data: ConflictExtraction) -> pd.DataFrame:
    """Μετατρέπει τα conflict pairs σε DataFrame για audit/report."""
    return pd.DataFrame([
        {
            "ΜΑΘΗΤΗΣ_A": a,
            "ΜΑΘΗΤΗΣ_B": b,
            "ΣΤΗΛΗ_ΣΥΓΚΡΟΥΣΗΣ": data.conflict_col or "",
        }
        for a, b in data.pair_originals
    ])


__all__ = [
    "ConflictExtraction",
    "UnresolvedConflictName",
    "strip_diacritics",
    "canon_name",
    "norm_name",
    "tokenize_canon_name",
    "best_name_match",
    "parse_name_list",
    "parse_friends_cell",
    "choose_conflict_col",
    "extract_conflict_data",
    "extract_conflict_pairs",
    "list_conflict_violations",
    "count_conflict_violations",
    "has_conflict_violation",
    "forbidden_classes_for_student",
    "can_place_student",
    "filter_valid_scenario_cols",
    "assert_no_conflicts",
    "unresolved_to_dataframe",
    "conflict_pairs_to_dataframe",
]
