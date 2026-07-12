
# -*- coding: utf-8 -*-
from __future__ import annotations

"""
step4_multi_groups_v2.py
========================
Βελτιωμένη εκδοχή του Βήματος 4 για Κ>2 τμήματα, με:
- @dataclass config (Step4Config)
- Input validation & custom exceptions
- Δημιουργία δυάδων πλήρως αμοιβαίων, αποκλεισμός "σπασμένων"
- Incremental metrics (χωρίς συνεχές recompute)
- Heuristics τοποθέτησης με weighted class scoring (variance / cap / balance)
- Early bounds pruning
- Penalty & summary export με metadata
- "FILLED" εξαγωγή (μεταφορά αναθέσεων Βημάτων 1–3 μέσα στο Βήμα 4)
- One‑shot export σε μορφή PER_SCENARIO_EXACT (12 στήλες), όπως το παράδειγμα

Συμβατότητα πεδίων:
- ΦΥΛΟ: "ΑΓΟΡΙ"/"ΚΟΡΙΤΣΙ" (tolerant normalization)
- ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ: "Ν" / "Ο"
- ΦΙΛΟΙ (ή ΦΙΛΟΣ): λίστα φιλίας (comma/semicolon/pipe/newline separated)
- ΣΠΑΣΜΕΝΕΣ_ΦΙΛΙΕΣ: bool (optional, default False)
- ΒΗΜΑ1/2/3_ΣΕΝΑΡΙΟ_k: προγενέστερες αναθέσεις

API (κύρια):
    run_step4_multi_with_fill_v2(df, config=Step4Config()) -> DataFrame
    export_step4_nextcol_full_multi_filled_v2(step3_xlsx, out_xlsx, config=Step4Config()) -> str
    export_step3_to_per_scenario_exact_filled_v2(step3_xlsx, out_xlsx, config=Step4Config()) -> str
"""

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd, numpy as np, re, math, random, statistics
from datetime import datetime

# --- Προαιρετικός κοινός guard δηλωμένων/εξωτερικών συγκρούσεων ---
try:
    from conflict_guard import (
        extract_conflict_pairs as _cg_extract_conflict_pairs,
        can_place_student as _cg_can_place_student,
        norm_name as _cg_norm_name,
    )
except Exception as _cg_import_error:
    print(f"⚠️ conflict_guard δεν βρέθηκε ή δεν φορτώθηκε σωστά στο Step 4: {_cg_import_error}")
    print("⚠️ Το Step 4 θα χρησιμοποιήσει fallback raw έλεγχο χωρίς fuzzy/canon matching.")
    _cg_extract_conflict_pairs = None
    _cg_can_place_student = None
    def _cg_norm_name(x):
        return re.sub(r"\s+", " ", str(x).strip())

# --- Conflict helper (επαναχρησιμοποιήσιμο από step_3_helpers) ---

def _parse_conflicts(x) -> List[str]:
    """Parsing ΣΥΓΚΡΟΥΣΗ — ίδια μορφή με ΦΙΛΟΙ."""
    return _friends_list(x)  # ορίζεται παρακάτω — forward ref OK λόγω module load


def _conflict_pairs_for_df(df: pd.DataFrame):
    """Εξάγει conflict_pairs με το κοινό conflict_guard όταν είναι διαθέσιμο."""
    if _cg_extract_conflict_pairs is None:
        return None
    try:
        return _cg_extract_conflict_pairs(df)
    except Exception as e:
        print(f"⚠️ Step 4: αποτυχία extract_conflict_pairs, fallback raw έλεγχος: {e}")
        return None


def _names_conflict_by_guard(df: pd.DataFrame, idx_a: int, idx_b: int, conflict_pairs=None) -> bool:
    """True αν τα δύο indices είναι δηλωμένο ζεύγος σύγκρουσης."""
    name_col = _choose_name_col(df)
    a = _cg_norm_name(df.loc[idx_a, name_col])
    b = _cg_norm_name(df.loc[idx_b, name_col])
    if not a or not b or a == b:
        return False
    if conflict_pairs is not None:
        return tuple(sorted((a, b))) in {tuple(sorted((_cg_norm_name(x), _cg_norm_name(y)))) for x, y in conflict_pairs}

    # Fallback raw check αν δεν υπάρχει conflict_guard
    if "ΣΥΓΚΡΟΥΣΗ" not in df.columns:
        return False
    ci = {_cg_norm_name(x) for x in _parse_conflicts(df.loc[idx_a].get("ΣΥΓΚΡΟΥΣΗ", ""))}
    cj = {_cg_norm_name(x) for x in _parse_conflicts(df.loc[idx_b].get("ΣΥΓΚΡΟΥΣΗ", ""))}
    return b in ci or a in cj


def _conflict_in_class(
    df: pd.DataFrame,
    student_name: str,
    class_name: str,
    assign: "pd.Series | Dict",
    conflict_pairs=None,
) -> bool:
    """
    Επιστρέφει True αν ο student_name έχει δηλωμένη σύγκρουση
    με οποιονδήποτε μαθητή ήδη στο class_name.

    Όταν υπάρχει conflict_guard.py, χρησιμοποιεί το κοινό can_place_student()
    ώστε το Step 4 να έχει την ίδια λογική με τα υπόλοιπα βήματα.
    Αν δεν φορτωθεί, πέφτει στο παλιό raw bidirectional fallback.
    """
    name = str(student_name).strip()
    if not name or not str(class_name).strip():
        return False

    tmp_col = "__STEP4_TMP_ASSIGN__"

    # Κοινός guard: χτίζουμε προσωρινή στήλη ανάθεσης από base_assign + new_assign.
    if _cg_can_place_student is not None:
        try:
            tmp_df = df.copy()
            tmp_df[tmp_col] = pd.Series([pd.NA] * len(tmp_df), index=tmp_df.index, dtype="object")
            if isinstance(assign, dict):
                for idx, cl in assign.items():
                    if idx in tmp_df.index and pd.notna(cl) and str(cl).strip():
                        tmp_df.loc[idx, tmp_col] = str(cl).strip()
            else:
                for idx in assign.index:
                    cl = assign.loc[idx]
                    if idx in tmp_df.index and pd.notna(cl) and str(cl).strip():
                        tmp_df.loc[idx, tmp_col] = str(cl).strip()
            pairs = conflict_pairs if conflict_pairs is not None else _conflict_pairs_for_df(tmp_df)
            return not _cg_can_place_student(tmp_df, name, class_name, tmp_col, pairs)
        except Exception as e:
            print(f"⚠️ Step 4: conflict_guard.can_place_student απέτυχε, fallback raw έλεγχος: {e}")

    # Fallback raw exact/bidirectional check
    if "ΣΥΓΚΡΟΥΣΗ" not in df.columns:
        return False

    if isinstance(assign, dict):
        in_class = [str(df.loc[idx, _choose_name_col(df)]).strip()
                    for idx, cl in assign.items() if cl == class_name and idx in df.index]
    else:
        in_class_idx = [idx for idx in assign.index if assign.loc[idx] == class_name]
        in_class = [str(df.loc[idx, _choose_name_col(df)]).strip() for idx in in_class_idx]

    if not in_class:
        return False

    row_u = df[df[_choose_name_col(df)].astype(str).str.strip() == name]
    conflicts_u: set = set()
    if not row_u.empty:
        conflicts_u = set(_parse_conflicts(row_u.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", "")))

    for member in in_class:
        if member in conflicts_u:
            return True
        row_m = df[df[_choose_name_col(df)].astype(str).str.strip() == member]
        if not row_m.empty:
            c_m = set(_parse_conflicts(row_m.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", "")))
            if name in c_m:
                return True
    return False

# ------------------------- Exceptions -------------------------

class Step4Error(Exception): pass
class InsufficientDataError(Step4Error): pass
class InvalidConfigError(Step4Error): pass

# ------------------------- Config & constants -----------------

@dataclass
class Step4Config:
    max_pop_diff: int = 4
    max_greek_diff: int = 6
    max_gender_diff: int = 6
    cap_per_class: int = 25
    max_scenarios: int = 5
    # weights for heuristic class scoring (lower is better)
    w_pop_variance: float = 1.0
    w_greek_variance: float = 0.6
    w_gender_variance: float = 0.6
    w_cap_overflow: float = 100.0   # hard discourage breaking cap
    random_seed: int = 42
    # NEW: ideal strategy flags
    use_ideal_strategy: bool = True
    prefer_opposites: bool = True
    max_greek_diff: int = 6
    max_gender_diff: int = 6
    cap_per_class: int = 25
    max_scenarios: int = 5
    # weights for heuristic class scoring (lower is better)
    w_pop_variance: float = 1.0
    w_greek_variance: float = 0.6
    w_gender_variance: float = 0.6
    w_cap_overflow: float = 100.0   # hard discourage breaking cap
    random_seed: int = 42
    # NEW: ideal strategy flags
    use_ideal_strategy: bool = True
    prefer_opposites: bool = True

STEP_COLUMN_PATTERNS = re.compile(r"^ΒΗΜΑ[1-3]_ΣΕΝΑΡΙΟ_\d+$")
FRIEND_COLUMN_CANDIDATES = ("ΦΙΛΟΙ","ΦΙΛΟΣ")
NAME_COLUMN_CANDIDATES = ("ΟΝΟΜΑ","ΟΝΟΜΑΤΕΠΩΝΥΜΟ","Ονοματεπώνυμο","ΜΑΘΗΤΗΣ","ΜΑΘΗΤΡΙΑ","Name","FULL_NAME")

random.seed(42)

# ------------------------- Normalization utils ----------------

def _norm_str(x: Any) -> str:
    if pd.isna(x): return ""
    s = str(x).strip().lower()
    return re.sub(r"\s+", " ", s)

def _gender_norm(x: Any) -> str:
    if pd.isna(x):
        return ""
    s = str(x).strip().lower()
    if s in ("αγορι","boy","male","α","m"):
        return "ΑΓΟΡΙ"
    if s in ("κοριτσι","girl","female","κ","f"):
        return "ΚΟΡΙΤΣΙ"
    # unknown -> empty to avoid spurious categories
    return ""
def _greek_norm(x: Any) -> str:
    if pd.isna(x):
        return ""
    t = str(x).strip().upper()
    if t in ("Ν","NAI","YES","GOOD","KALH","KALΗ"):
        return "Ν"
    if t in ("Ο","OXI","ΟΧΙ","NO","NOT","OK"):
        return "Ο"
    # unknown -> empty
    return ""

def _friends_list(x):
    """
    Return a clean Python list of friend names from a cell value.
    Handles:
      - NaN/None/empty -> []
      - Python list/tuple/set -> list(str)
      - numpy arrays -> list(str)
      - JSON-like strings: "['A','B']" or '["A","B"]'
      - Plain strings with separators: comma/semicolon/slash/pipe/ampersand/space-και-space
    Never raises "truth value of empty array is ambiguous".
    """
    import pandas as pd
    import numpy as np
    import ast
    import re

    # Fast path for obvious empties
    if x is None:
        return []
    # If scalar, we can safely use pd.isna
    try:
        is_scalar = np.isscalar(x) or isinstance(x, (pd.Timestamp, pd.Timedelta))
    except Exception:
        is_scalar = True
    if is_scalar:
        try:
            if pd.isna(x):
                return []
        except Exception:
            pass

    # Already a list/tuple/set/ndarray
    if isinstance(x, (list, tuple, set)):
        vals = list(x)
    elif hasattr(x, "tolist") and not isinstance(x, str):
        # numpy array etc.
        try:
            vals = list(x.tolist())
        except Exception:
            vals = [str(x)]
    else:
        s = str(x).strip()
        if not s or s.lower() in {"nan", "none", "null"}:
            return []
        # Try parse as Python/JSON list
        if (s.startswith("[") and s.endswith("]")) or (s.startswith("(") and s.endswith(")")):
            try:
                parsed = ast.literal_eval(s)
                if isinstance(parsed, (list, tuple, set)):
                    vals = list(parsed)
                else:
                    vals = [parsed]
            except Exception:
                vals = [s]
        else:
            # Split by common separators (including Greek " και ")
            s = re.sub(r"\s+και\s+", ",", s, flags=re.IGNORECASE)
            vals = re.split(r"[;,/|&]+", s)

    # Cleanup, normalize, drop empties/dummies like '-'
    out = []
    for v in vals:
        if v is None:
            continue
        sv = str(v).strip()
        if not sv or sv in {"-", "_"}:
            continue
        out.append(sv)
    return out

def _find_step_cols(df: pd.DataFrame) -> List[str]:
    cols = [c for c in df.columns if STEP_COLUMN_PATTERNS.match(str(c))]
    if not cols:
        cols = [c for c in df.columns if str(c).startswith("ΒΗΜΑ1_") or str(c).startswith("ΒΗΜΑ2_") or str(c).startswith("ΒΗΜΑ3_")]
    return cols

def _detect_classes(df: pd.DataFrame) -> List[str]:
    step_cols = _find_step_cols(df)
    classes = []
    for c in step_cols:
        vals = df[c].dropna().astype(str).unique().tolist()
        classes.extend(vals)
    classes = [v for v in classes if str(v).strip() != ""]
    classes = sorted(set(classes), key=lambda x: (len(str(x)), str(x)))
    return classes

def _get_current_assignment_row(row: pd.Series, step_cols: List[str]) -> Optional[str]:
    def key_order(c):
        if str(c).startswith("ΒΗΜΑ3_"): return 0
        if str(c).startswith("ΒΗΜΑ2_"): return 1
        if str(c).startswith("ΒΗΜΑ1_"): return 2
        return 3
    for c in sorted(step_cols, key=key_order):
        v = row.get(c, np.nan)
        if pd.notna(v) and str(v).strip() != "":
            return str(v).strip()
    return None

# ------------------------- Input validation -------------------

def _require_columns(df: pd.DataFrame) -> None:
    # At minimum: ΦΥΛΟ, ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ, ΦΙΛΟΙ/ΦΙΛΟΣ, step 1..3
    missing_steps = not any(str(c).startswith("ΒΗΜΑ") for c in df.columns)
    if missing_steps:
        raise InsufficientDataError("Λείπουν στήλες ΒΗΜΑ1/2/3 για να οριστούν οι μη-τοποθετημένοι.")
    if "ΦΥΛΟ" not in df.columns:
        raise InsufficientDataError("Λείπει η στήλη ΦΥΛΟ.")
    if "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ" not in df.columns:
        raise InsufficientDataError("Λείπει η στήλη ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ.")
    if not any(c in df.columns for c in FRIEND_COLUMN_CANDIDATES):
        raise InsufficientDataError("Λείπει στήλη ΦΙΛΟΙ ή ΦΙΛΟΣ.")

def _choose_name_col(df: pd.DataFrame) -> str:
    for cand in NAME_COLUMN_CANDIDATES:
        if cand in df.columns:
            return cand
    # fallback: first object col that isn't a step/friends
    for c in df.columns:
        if df[c].dtype == object and not str(c).startswith("ΒΗΜΑ") and c not in FRIEND_COLUMN_CANDIDATES:
            return c
    return NAME_COLUMN_CANDIDATES[0] if NAME_COLUMN_CANDIDATES[0] in df.columns else df.columns[0]

# ------------------------- Grouping / dyads -------------------

def build_unplaced_and_mutual_dyads(df: pd.DataFrame,
                                    broken_col="ΣΠΑΣΜΕΝΕΣ_ΦΙΛΙΕΣ") -> Tuple[pd.DataFrame, List[Tuple[int,int]]]:
    step_cols = _find_step_cols(df)
    mask_unplaced = pd.Series(True, index=df.index)
    for c in step_cols:
        mask_unplaced &= df[c].isna()
    unplaced_df = df[mask_unplaced].copy()

    name_col = _choose_name_col(df)
    friends_col = "ΦΙΛΟΙ" if "ΦΙΛΟΙ" in df.columns else ("ΦΙΛΟΣ" if "ΦΙΛΟΣ" in df.columns else None)
    if friends_col is None:
        raise InsufficientDataError("Δεν βρέθηκε στήλη ΦΙΛΟΙ/ΦΙΛΟΣ.")

    names = unplaced_df[name_col].astype(str).fillna("").map(str.strip)
    names_norm = names.map(_norm_str)

    # Map normalized name -> index (unique)
    index_by_norm = {}
    for idx, nm in zip(unplaced_df.index.tolist(), names_norm.tolist()):
        if nm and nm not in index_by_norm:
            index_by_norm[nm] = idx

    # Precompute normalized friend sets per index
    raw_lists = unplaced_df[friends_col].tolist()
    friend_sets = {}
    for idx, raw in zip(unplaced_df.index.tolist(), raw_lists):
        lst = [_norm_str(f) for f in _friends_list(raw)]
        friend_sets[idx] = set([f for f in lst if f])

    broken_mask = unplaced_df[broken_col] if (broken_col in unplaced_df.columns) else pd.Series(False, index=unplaced_df.index)

    dyads_set = set()
    pos_indices = unplaced_df.index.tolist()
    for i_pos, idx_i in enumerate(pos_indices):
        if bool(broken_mask.loc[idx_i]):
            continue
        me_norm = names_norm.iloc[i_pos]
        if not me_norm:
            continue
        for f_norm in friend_sets[idx_i]:
            j_idx = index_by_norm.get(f_norm)
            if j_idx is None or j_idx == idx_i:
                continue
            if bool(broken_mask.loc[j_idx]):
                continue
            # check mutual via normalized names
            if me_norm in friend_sets[j_idx]:
                pair = tuple(sorted([idx_i, j_idx]))
                dyads_set.add(pair)

    dyads = sorted(list(dyads_set))

    # Αφαίρεση δυάδων όπου οι δύο μαθητές έχουν δηλωμένη/εξωτερική σύγκρουση.
    # Με conflict_guard χρησιμοποιείται ίδια κανονικοποίηση με τα υπόλοιπα βήματα.
    conflict_pairs = _conflict_pairs_for_df(df)
    dyads = [(i, j) for (i, j) in dyads if not _names_conflict_by_guard(df, i, j, conflict_pairs)]

    return unplaced_df, dyads

def group_category(rows: List[pd.Series]) -> Dict[str,str]:
    genders = {_gender_norm(r.get("ΦΥΛΟ","")) for r in rows}
    greeks = {_greek_norm(r.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) for r in rows}
    gender_cat = "ΑΓΟΡΙΑ" if genders == {"ΑΓΟΡΙ"} else ("ΚΟΡΙΤΣΙΑ" if genders == {"ΚΟΡΙΤΣΙ"} else "ΜΙΚΤΟ ΦΥΛΟ")
    greek_cat  = "ΚΑΛΗ" if greeks == {"Ν"} else ("ΟΧΙ ΚΑΛΗ" if greeks == {"Ο"} else "ΜΙΚΤΗ")
    return {"gender_cat": gender_cat, "greek_cat": greek_cat}

# ------------------------- Metrics / penalty ------------------

def empty_metrics(classes: List[str]) -> Dict[str,Dict[str,int]]:
    return {c: {"total":0, "boys":0, "girls":0, "greek_good":0} for c in classes}

def apply_student_to_metrics(df: pd.DataFrame, idx: int, cl: str, metrics: Dict[str,Dict[str,int]]) -> None:
    # metrics must be pre-initialized for all classes
    row = df.loc[idx]
    m = metrics[cl]
    m["total"] += 1
    g = _gender_norm(row.get("ΦΥΛΟ",""))
    if g == "ΑΓΟΡΙ":
        m["boys"] += 1
    elif g == "ΚΟΡΙΤΣΙ":
        m["girls"] += 1
    if _greek_norm(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) == "Ν":
        m["greek_good"] += 1

def metrics_diff_tuple(mets: Dict[str,Dict[str,int]]) -> Tuple[int,int,int,int]:
    totals = [m["total"] for m in mets.values()] or [0]
    goods  = [m["greek_good"] for m in mets.values()] or [0]
    boys   = [m["boys"] for m in mets.values()] or [0]
    girls  = [m["girls"] for m in mets.values()] or [0]
    return (max(totals)-min(totals), max(boys)-min(boys), max(girls)-min(girls), max(goods)-min(goods))

def ranges_ok(mets: Dict[str,Dict[str,int]], cfg: Step4Config) -> bool:
    d_pop, d_boys, d_girls, d_good = metrics_diff_tuple(mets)
    if d_pop > cfg.max_pop_diff: return False
    if d_good > cfg.max_greek_diff: return False
    if d_boys > cfg.max_gender_diff: return False
    if d_girls > cfg.max_gender_diff: return False
    return True

def penalty_score(mets: Dict[str,Dict[str,int]]) -> int:
    d_pop, d_boys, d_girls, d_good = metrics_diff_tuple(mets)
    pop_pen = max(0, d_pop - 1)
    grk_pen = max(0, d_good - 2)
    sex_pen = max(0, d_boys - 1) + max(0, d_girls - 1)
    return int(pop_pen + grk_pen + sex_pen)

def variance_score(mets: Dict[str,Dict[str,int]]) -> Tuple[float,float,float]:
    vals = list(mets.values())
    if not vals:
        return (0.0, 0.0, 0.0)
    totals = [max(0, int(m.get("total", 0))) for m in vals]
    boys   = [max(0, int(m.get("boys", 0)))  for m in vals]
    girls  = [max(0, int(m.get("girls", 0))) for m in vals]
    goods  = [max(0, int(m.get("greek_good", 0))) for m in vals]
    v_tot = statistics.pvariance(totals) if len(totals) > 1 else 0.0
    v_gen = statistics.pvariance([b - g for b,g in zip(boys, girls)]) if len(boys) > 1 else 0.0
    v_grk = statistics.pvariance(goods) if len(goods) > 1 else 0.0
    return (v_tot, v_gen, v_grk)

# ------------------------- Core algorithm ---------------------

def _base_assignment_series(df: pd.DataFrame) -> pd.Series:
    step_cols = _find_step_cols(df)
    base = pd.Series(index=df.index, dtype=object)
    for ridx, row in df.iterrows():
        val = _get_current_assignment_row(row, step_cols)
        if val is not None:
            base.loc[ridx] = val
    return base

def _classes_from_base(base: pd.Series) -> List[str]:
    classes = sorted(set(str(v) for v in base.dropna().unique().tolist()))
    return [c for c in classes if c.strip() != ""]

def _init_metrics_from_base(df: pd.DataFrame, base: pd.Series, classes: List[str]) -> Dict[str,Dict[str,int]]:
    mets = empty_metrics(classes)
    class_set = set(classes)
    for idx, cl in base.items():
        if pd.isna(cl):
            continue
        cl = str(cl)
        if cl not in class_set:
            continue
        apply_student_to_metrics(df, idx, cl, mets)
    return mets

def _dyad_catalog(df: pd.DataFrame, dyads: List[Tuple[int,int]]) -> List[Dict[str,Any]]:
    info = []
    cat_counts = {}
    for (i,j) in dyads:
        rows = [df.loc[i], df.loc[j]]
        cat = group_category(rows)
        key = (cat["gender_cat"], cat["greek_cat"])
        cat_counts[key] = cat_counts.get(key, 0) + 1
        info.append({"pair": (i,j), "size": 2, "cat": cat, "key": key})
    # scarcity = 1 / count; rare categories first
    for item in info:
        cnt = cat_counts[item["key"]]
        item["scarcity"] = 1.0 / cnt
    # sort dyads: rare categories first (desc scarcity), then by index
    info.sort(key=lambda x: (-x["scarcity"], x["pair"]))
    return info

def _class_weighted_score(mets: Dict[str,Dict[str,int]], cfg: Step4Config) -> float:
    v_tot, v_gen, v_grk = variance_score(mets)
    return cfg.w_pop_variance*v_tot + cfg.w_gender_variance*v_gen + cfg.w_greek_variance*v_grk

def _place_pair(df: pd.DataFrame, pair: Tuple[int,int], cl: str, mets: Dict[str,Dict[str,int]]) -> None:
    apply_student_to_metrics(df, pair[0], cl, mets)
    apply_student_to_metrics(df, pair[1], cl, mets)

def _would_break_cap(mets: Dict[str,Dict[str,int]], cl: str, size: int, cfg: Step4Config) -> bool:
    return (mets.get(cl, {"total":0})["total"] + size) > cfg.cap_per_class

def generate_scenarios_for_dyads_v2(df: pd.DataFrame,
                                    dyads: List[Tuple[int,int]],
                                    base_assign: pd.Series,
                                    classes: List[str],
                                    cfg: Step4Config) -> List[Dict[str,Any]]:
    """Backtracking με incremental metrics, scarcity ordering & weighted class scoring."""
    base_metrics = _init_metrics_from_base(df, base_assign, classes)
    dyad_info = _dyad_catalog(df, dyads)
    conflict_pairs = _conflict_pairs_for_df(df)

    solutions: List[Dict[str,Any]] = []
    new_assign: Dict[int,str] = {}
    mets = {c: m.copy() for c,m in base_metrics.items()}  # working metrics

    def backtrack(idx: int):
        if len(solutions) >= cfg.max_scenarios:
            return
        if idx >= len(dyad_info):
            # accept if ranges ok
            if not ranges_ok(mets, cfg): return
            pen = penalty_score(mets)
            assign_ser = pd.Series(index=df.index, dtype=object)
            for sid, cl in new_assign.items():
                assign_ser.loc[sid] = cl
            solutions.append({"assign": assign_ser, "metrics": {c: m.copy() for c,m in mets.items()}, "penalty": pen})
            return

        item = dyad_info[idx]
        pair, size = item["pair"], item["size"]

        # order classes by lowest projected weighted score
        class_scores: List[Tuple[float,str]] = []
        for cl in classes:
            if _would_break_cap(mets, cl, size, cfg):
                continue
            # simulate
            _place_pair(df, pair, cl, mets)
            ok_now = ranges_ok(mets, cfg)  # early pruning (tight bound)
            score = _class_weighted_score(mets, cfg) + (1000.0 if not ok_now else 0.0)
            # undo
            # We need to revert metrics: subtract pair
            # Create a cheap revert by manual subtraction
            for sid in pair:
                row = df.loc[sid]
                m = mets[cl]
                m["total"] -= 1
                g = _gender_norm(row.get("ΦΥΛΟ",""))
                if g == "ΑΓΟΡΙ": m["boys"] -= 1
                elif g == "ΚΟΡΙΤΣΙ": m["girls"] -= 1
                if _greek_norm(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) == "Ν": m["greek_good"] -= 1
            class_scores.append((score, cl))

        class_scores.sort(key=lambda t: t[0])

        for _, cl in class_scores:
            if len(solutions) >= cfg.max_scenarios:
                break
            # Έλεγχος σύγκρουσης με ήδη τοποθετημένους στο cl
            if any(_conflict_in_class(df, df.loc[sid, _choose_name_col(df)], cl,
                                      base_assign.to_dict() | new_assign, conflict_pairs) for sid in pair):
                continue
            # apply
            for sid in pair: new_assign[sid] = cl
            _place_pair(df, pair, cl, mets)

            # deeper
            backtrack(idx+1)

            # revert
            for sid in pair: del new_assign[sid]
            # subtract pair from mets
            for sid in pair:
                row = df.loc[sid]
                m = mets[cl]
                m["total"] -= 1
                g = _gender_norm(row.get("ΦΥΛΟ",""))
                if g == "ΑΓΟΡΙ": m["boys"] -= 1
                elif g == "ΚΟΡΙΤΣΙ": m["girls"] -= 1
                if _greek_norm(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) == "Ν": m["greek_good"] -= 1

    backtrack(0)

    # sort & tie-breakers
    def diffs_tuple(m):
        d_pop, d_boys, d_girls, d_good = metrics_diff_tuple(m)
        return (d_pop, d_boys, d_girls, d_good)
    solutions.sort(key=lambda s: (s["penalty"],) + diffs_tuple(s["metrics"]))
    return solutions[:cfg.max_scenarios]



def generate_scenarios_for_dyads_ideal(df, dyads, base_assign, classes, cfg):
    # Fallback minimal ideal strategy: equalize category counts per class with alternation.
    K = len(classes)
    mets = _init_metrics_from_base(df, base_assign, classes)
    conflict_pairs = _conflict_pairs_for_df(df)
    # Build category counts and dyads per category
    info = []
    cat_counts = {}
    for (i,j) in dyads:
        rows = [df.loc[i], df.loc[j]]
        cat = group_category(rows)  # uses gender_cat/greek_cat
        key = (cat["gender_cat"], cat["greek_cat"])
        cat_counts[key] = cat_counts.get(key, 0) + 1
        info.append({"pair": (i,j), "key": key})
    # Ideal per category (students)
    per_class_cat = {key: {cl:0 for cl in classes} for key in cat_counts.keys()}
    ideals = {key: round((sum(per_class_cat[key].values()) + 2*sum(1 for x in info if x["key"]==key))/max(1,K)) for key in cat_counts.keys()}

    # Order by scarcity
    info.sort(key=lambda x: -1.0/cat_counts[x["key"]])

    last_key = {cl: None for cl in classes}
    sols = []
    assign = {}
    def backtrack(pos):
        if len(sols) >= cfg.max_scenarios: return
        if pos >= len(info):
            if not ranges_ok(mets, cfg): return
            pen = penalty_score(mets)
            ser = pd.Series(index=df.index, dtype=object)
            for sid, cl in assign.items(): ser.loc[sid] = cl
            sols.append({"assign": ser, "metrics": {c: m.copy() for c,m in mets.items()}, "penalty": pen})
            return
        item = info[pos]
        pair, key = item["pair"], item["key"]
        cands = []
        for cl in classes:
            # cap check
            if _would_break_cap(mets, cl, 2, cfg): 
                continue
            # score by gap to ideal + alternation bonus
            gap = abs((per_class_cat[key][cl] + 2) - ideals[key])
            alt_bonus = -0.5 if (cfg.prefer_opposites and last_key[cl] is not None and last_key[cl] != key) else 0.0
            # simulate quick range ok
            _place_pair(df, pair, cl, mets)
            ok = ranges_ok(mets, cfg)
            # revert
            for sid in pair:
                row = df.loc[sid]; m = mets[cl]
                m["total"] -= 1
                g = _gender_norm(row.get("ΦΥΛΟ",""))
                if g == "ΑΓΟΡΙ": m["boys"] -= 1
                elif g == "ΚΟΡΙΤΣΙ": m["girls"] -= 1
                if _greek_norm(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) == "Ν": m["greek_good"] -= 1
            if ok:
                cands.append(((gap + alt_bonus), cl))
        if not cands:
            return
        cands.sort(key=lambda x: x[0])
        best = [cl for sc,cl in cands if sc == cands[0][0]]
        for cl in best[:max(2, cfg.max_scenarios - len(sols))]:
            # Έλεγχος σύγκρουσης με ήδη τοποθετημένους
            # ΔΙΟΡΘΩΣΗ: περνάμε το ήδη υπολογισμένο conflict_pairs (γραμμή 622),
            # ώστε να μην ξαναϋπολογίζεται _conflict_pairs_for_df() -> extract_conflict_data()
            # (με τα warnings.warn για unresolved names) σε κάθε candidate class / δυάδα / βήμα backtracking.
            if any(_conflict_in_class(df, df.loc[sid, _choose_name_col(df)], cl,
                                      base_assign.to_dict() | assign, conflict_pairs) for sid in pair):
                continue
            assign[pair[0]] = cl; assign[pair[1]] = cl
            _place_pair(df, pair, cl, mets)
            per_class_cat[key][cl] += 2
            prev = last_key[cl]; last_key[cl] = key
            backtrack(pos+1)
            last_key[cl] = prev
            per_class_cat[key][cl] -= 2
            for sid in pair:
                del assign[sid]
                row = df.loc[sid]; m = mets[cl]
                m["total"] -= 1
                g = _gender_norm(row.get("ΦΥΛΟ",""))
                if g == "ΑΓΟΡΙ": m["boys"] -= 1
                elif g == "ΚΟΡΙΤΣΙ": m["girls"] -= 1
                if _greek_norm(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","")) == "Ν": m["greek_good"] -= 1
    backtrack(0)
    sols.sort(key=lambda s: (s["penalty"],) + metrics_diff_tuple(s["metrics"]))
    return sols[:cfg.max_scenarios]
# ------------------------- Public APIs --------------------------------------

def run_step4_multi_with_fill_v2(df: pd.DataFrame, config: Step4Config = Step4Config()) -> pd.DataFrame:
    _require_columns(df)
    base_assign = _base_assignment_series(df)
    classes = _detect_classes(df)
    if not classes:
        # αν δεν βρεθούν από στήλες 1..3, πάρε από base
        classes = _classes_from_base(base_assign)
    if not classes:
        raise InsufficientDataError("Δεν εντοπίστηκαν labels τμημάτων από τα Βήματα 1–3.")
    if len(classes) < 2:
        out = df.copy()
        for k in range(1, config.max_scenarios+1):
            out[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{k}"] = base_assign
        out["Σύνοψη_ΒΗΜΑ4"] = "Μόνο 1 τμήμα — carry-forward από Βήματα 1–3."
        return out
    unplaced_df, dyads = build_unplaced_and_mutual_dyads(df)

    out = df.copy()
    if not dyads:
        # carry-forward to ensure ΒΗΜΑ4 continuity
        for k in range(1, config.max_scenarios+1):
            out[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{k}"] = base_assign
        out["Σύνοψη_ΒΗΜΑ4"] = "Δεν βρέθηκαν πλήρως αμοιβαίες δυάδες μεταξύ μη-τοποθετημένων."
        return out

    sols = (generate_scenarios_for_dyads_ideal(df, dyads, base_assign, classes, config)
        if getattr(config, 'use_ideal_strategy', True) else
        generate_scenarios_for_dyads_v2(df, dyads, base_assign, classes, config))
    if not sols:
        out["Σύνοψη_ΒΗΜΑ4"] = "Δεν βρέθηκαν αποδεκτά σενάρια με βάση τα όρια."
        return out

    # Γράψε έως 5 σενάρια
    for k,sol in enumerate(sols, start=1):
        col = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{k}"
        out[col] = pd.Series(index=out.index, dtype=object)  # object ώστε να δέχεται strings
        for idx, cl in sol["assign"].items():
            if pd.notna(cl):
                out.loc[idx, col] = str(cl)

    # FILLED: μεταφορά όλων των υπαρχουσών αναθέσεων (βάση)
    for c in [c for c in out.columns if re.match(r"^ΒΗΜΑ4_ΣΕΝΑΡΙΟ_\d+$", str(c))]:
        out[c] = out[c].where(out[c].notna(), base_assign)

    # penalties snapshot στην πρώτη γραμμή (αν θες να επιλέγεις “best” αργότερα)
    for k,sol in enumerate(sols, start=1):
        out.loc[out.index[0], f"ΒΗΜΑ4_penalty_{k}"] = int(sol["penalty"])

    # metadata
    out.loc[out.index[0], "ΒΗΜΑ4_meta"] = f"generated:{datetime.now().isoformat(timespec='seconds')} cfg={config}"
    try:
        _pairs = _conflict_pairs_for_df(df)
        out.loc[out.index[0], "ΒΗΜΑ4_declared_conflict_pairs"] = 0 if _pairs is None else len(_pairs)
    except Exception:
        pass

    return out

def export_step4_nextcol_full_multi_filled_v2(step3_xlsx_path: str, out_xlsx_path: str, config: Step4Config = Step4Config()) -> str:
    xls = pd.ExcelFile(step3_xlsx_path)
    summary_rows = []
    with pd.ExcelWriter(out_xlsx_path, engine="openpyxl") as writer:
        for sh in xls.sheet_names:
            df = xls.parse(sh)
            if str(sh).strip().lower().startswith("σύνοψη"):
                # αντιγράφουμε σύνοψη, για πληρότητα
                df.to_excel(writer, index=False, sheet_name=str(sh)[:31])
                continue
            try:
                out_df = run_step4_multi_with_fill_v2(df, config=config)
                step4_cols = [c for c in out_df.columns if re.match(r"^ΒΗΜΑ4_ΣΕΝΑΡΙΟ_\d+$", str(c))]
                placed_counts = [int(out_df[c].notna().sum()) for c in step4_cols] if step4_cols else []
                summary_rows.append({
                    "Φύλλο": sh, 
                    "Σενάρια ΒΗΜΑ4": len(step4_cols),
                    "Τοποθετημένοι (ανά σενάριο)": ", ".join(map(str, placed_counts)) if placed_counts else "(κανένας)"
                })
            except Exception as ex:
                out_df = df.copy()
                out_df["Σύνοψη_ΒΗΜΑ4"] = f"ERROR: {type(ex).__name__}: {ex}"
                summary_rows.append({
                    "Φύλλο": sh,
                    "Σενάρια ΒΗΜΑ4": "ERROR",
                    "Τοποθετημένοι (ανά σενάριο)": f"{type(ex).__name__}: {ex}"
                })
            out_df.to_excel(writer, index=False, sheet_name=str(sh)[:31])
        # summary + metadata
        meta = pd.DataFrame([{
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": repr(config)
        }])
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="Σύνοψη")
        meta.to_excel(writer, index=False, sheet_name="Meta")
    return out_xlsx_path

def _pick_best_step4_col(df: pd.DataFrame) -> Tuple[Optional[int], Optional[str]]:
    pen_map = {}
    for c in df.columns:
        m = re.match(r"^ΒΗΜΑ4_penalty_(\d+)$", str(c))
        if m:
            k = int(m.group(1))
            val = df[c].dropna()
            if not val.empty:
                try:
                    pen_map[k] = float(val.iloc[0])
                except: pass
    step4_cols = [c for c in df.columns if re.match(r"^ΒΗΜΑ4_ΣΕΝΑΡΙΟ_\d+$", str(c))]
    if not step4_cols:
        return None, None
    if pen_map:
        best_k = min(pen_map, key=lambda k: pen_map[k])
        best_col = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{best_k}"
        return best_k, best_col
    first_col = step4_cols[0]
    k = int(re.search(r"\d+$", first_col).group(0))
    return k, first_col

def export_step3_to_per_scenario_exact_filled_v2(step3_xlsx_path: str, out_xlsx_path: str, config: Step4Config = Step4Config()) -> str:
    TARGET_BASE_COLS = ['Α/Α','ΟΝΟΜΑ','ΦΥΛΟ','ΖΩΗΡΟΣ','ΙΔΙΑΙΤΕΡΟΤΗΤΑ','ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ','ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ','ΦΙΛΟΙ']
    xls = pd.ExcelFile(step3_xlsx_path)
    with pd.ExcelWriter(out_xlsx_path, engine="openpyxl") as writer:
        chosen_rows = []
        for sh in xls.sheet_names:
            if str(sh).strip().lower().startswith("σύνοψη"):
                continue
            df = xls.parse(sh)
            filled_df = run_step4_multi_with_fill_v2(df, config=config)
            m = re.search(r"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_(\d+)", str(sh))
            sid = int(m.group(1)) if m else 1

            out_df = pd.DataFrame(index=filled_df.index)
            for c in TARGET_BASE_COLS:
                out_df[c] = filled_df[c] if c in filled_df.columns else None
            for step in [1,2,3]:
                col = f"ΒΗΜΑ{step}_ΣΕΝΑΡΙΟ_{sid}"
                out_df[col] = filled_df[col] if col in filled_df.columns else None

            best_k, best_col = _pick_best_step4_col(filled_df)
            if best_col is not None:
                out_df[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"] = filled_df[best_col]
                pen = None
                if best_k is not None and f"ΒΗΜΑ4_penalty_{best_k}" in filled_df.columns:
                    pser = filled_df[f"ΒΗΜΑ4_penalty_{best_k}"].dropna()
                    pen = float(pser.iloc[0]) if not pser.empty else None
                chosen_rows.append({"Sheet": f"ΣΕΝΑΡΙΟ_{sid}", "Best": best_col, "Penalty": pen})
            else:
                out_df[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"] = None
                chosen_rows.append({"Sheet": f"ΣΕΝΑΡΙΟ_{sid}", "Best": "(none)", "Penalty": None})

            ordered = TARGET_BASE_COLS + [f"ΒΗΜΑ1_ΣΕΝΑΡΙΟ_{sid}", f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}", f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}", f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"]
            out_df = out_df[ordered]
            out_df.to_excel(writer, index=False, sheet_name=f"ΣΕΝΑΡΙΟ_{sid}")

        summ = pd.DataFrame(chosen_rows)
        summ.to_excel(writer, index=False, sheet_name="Σύνοψη_Επιλογών")
        meta = pd.DataFrame([{
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "config": repr(config)
        }])
        meta.to_excel(writer, index=False, sheet_name="Meta")
    return out_xlsx_path

# --- Compatibility shim for external callers ---
import pandas as pd
from typing import Optional

def apply_step4_with_enhanced_strategy(
    df: pd.DataFrame,
    assigned_column: str = 'ΒΗΜΑ3_ΣΕΝΑΡΙΟ_1',
    num_classes: Optional[int] = None,
    max_results: int = 5,
    **kwargs
):
    """
    Return DataFrame with ΒΗΜΑ4_ΣΕΝΑΡΙΟ_1..max_results filled.
    - If no mutual dyads exist, all ΒΗΜΑ4_ΣΕΝΑΡΙΟ_k are carry-forward of prior steps (Βήμα3→2→1).
    - Honors hard constraints and produces up to `max_results` candidate Step4 columns.
    """
    cfg = Step4Config(max_scenarios=int(max_results), use_ideal_strategy=True, prefer_opposites=True)
    return run_step4_multi_with_fill_v2(df, config=cfg)


def export_step3_to_per_scenario_exact_like_template(step3_xlsx_path: str, out_xlsx_path: str, config: Step4Config = Step4Config()) -> str:
    """
    Export EXACTLY like the provided template:
    - Only sheets named 'ΣΕΝΑΡΙΟ_{k}'.
    - Columns (in order): 8 base + ΒΗΜΑ1_ΣΕΝΑΡΙΟ_k, ΒΗΜΑ2_ΣΕΝΑΡΙΟ_k, ΒΗΜΑ3_ΣΕΝΑΡΙΟ_k, ΒΗΜΑ4_ΣΕΝΑΡΙΟ_k
    - No 'Σύνοψη' / No 'Meta' sheets.
    """
    TARGET_BASE_COLS = ['Α/Α','ΟΝΟΜΑ','ΦΥΛΟ','ΖΩΗΡΟΣ','ΙΔΙΑΙΤΕΡΟΤΗΤΑ','ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ','ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ','ΦΙΛΟΙ']
    xls = pd.ExcelFile(step3_xlsx_path)
    with pd.ExcelWriter(out_xlsx_path, engine="openpyxl") as writer:
        for sh in xls.sheet_names:
            if str(sh).strip().lower().startswith("σύνοψη"):
                continue
            df = xls.parse(sh)
            filled_df = run_step4_multi_with_fill_v2(df, config=config)
            m = re.search(r"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_(\d+)", str(sh))
            sid = int(m.group(1)) if m else 1

            out_df = pd.DataFrame(index=filled_df.index)
            # base
            for c in TARGET_BASE_COLS:
                out_df[c] = filled_df[c] if c in filled_df.columns else None

            # step columns
            step_cols = [f"ΒΗΜΑ1_ΣΕΝΑΡΙΟ_{sid}", f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}", f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}"]
            for c in step_cols:
                out_df[c] = filled_df[c] if c in filled_df.columns else None

            # pick best ΒΗΜΑ4 and keep only that one
            k_best, best_col = _pick_best_step4_col(filled_df)
            if best_col is not None and best_col in filled_df.columns:
                out_df[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"] = filled_df[best_col]
            else:
                # carry-forward if none
                base_assign = _base_assignment_series(filled_df)
                out_df[f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"] = base_assign

            ordered = TARGET_BASE_COLS + step_cols + [f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"]
            out_df = out_df[ordered]
            out_df.to_excel(writer, index=False, sheet_name=f"ΣΕΝΑΡΙΟ_{sid}")
    return out_xlsx_path
