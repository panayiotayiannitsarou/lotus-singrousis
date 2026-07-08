# -*- coding: utf-8 -*-
"""
Step 2 — Ζωηροί & Ιδιαιτερότητες (Fixed v3, patched)
- Η στήλη εξόδου του Βήματος 2 ΜΕΤΟΝΟΜΑΖΕΤΑΙ σε «ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{k}»
  όπου k είναι ο αριθμός από το step1_col_name (π.χ. ΒΗΜΑ1_ΣΕΝΑΡΙΟ_2 -> k=2).
- Δεν δημιουργεί FINAL/audit στήλες. Μόνο τη στήλη ΒΗΜΑ2.
"""
from typing import List, Dict, Tuple, Any, Set, Optional
import pandas as pd
import random
import re

def _auto_num_classes(df, override=None):
    import math
    n = len(df)
    # keep min 2 (συμβατότητα downstream)
    k = max(2, math.ceil(n/25))
    return int(k if override is None else override)

from step_2_helpers_FIXED import (
    normalize_columns, parse_friends_cell, scope_step2, mutual_pairs_in_scope
)

# Βήμα 0: κοινός φύλακας δηλωμένων/εξωτερικών συγκρούσεων.
# Κανονικά πρέπει να υπάρχει στον ίδιο φάκελο το conflict_guard.py.
try:
    import conflict_guard as _conflict_guard
except Exception as e:
    print(f"⚠️ conflict_guard δεν βρέθηκε ή δεν φορτώθηκε σωστά στο Step 2: {e}")
    print("⚠️ Το Step 2 θα χρησιμοποιήσει fallback έλεγχο χωρίς fuzzy matching / χωρίς πλήρη κανονικοποίηση.")
    _conflict_guard = None


def _extract_declared_conflict_pairs(df: pd.DataFrame):
    """Επιστρέφει (conflict_pairs, unresolved_count) από το κοινό conflict_guard, όταν υπάρχει."""
    if _conflict_guard is None:
        return frozenset(), 0
    try:
        if hasattr(_conflict_guard, "extract_conflict_data"):
            data = _conflict_guard.extract_conflict_data(
                df,
                warn_if_missing_col=False,
                warn_unresolved=True,
            )
            return data.pairs, len(getattr(data, "unresolved", ()))
        if hasattr(_conflict_guard, "extract_conflict_pairs"):
            return _conflict_guard.extract_conflict_pairs(df), 0
    except Exception as e:
        print(f"⚠️ Αποτυχία extract_conflict_data στο Step 2: {e}")
    return frozenset(), 0


def _has_declared_conflict_violation(df: pd.DataFrame, scenario_col: str, conflict_pairs) -> bool:
    """Τελική ασφάλεια: κανένα candidate Step 2 δεν μπαίνει στο best αν έχει δηλωμένη σύγκρουση."""
    if _conflict_guard is None or not conflict_pairs or scenario_col not in df.columns:
        return False
    try:
        return bool(_conflict_guard.has_conflict_violation(df, scenario_col, conflict_pairs))
    except Exception as e:
        print(f"⚠️ Αποτυχία ελέγχου has_conflict_violation στο Step 2: {e}")
        return False

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

def _pair_conflict_penalty(aZ, aI, bZ, bI) -> int:
    if aI and bI: return 5
    if (aI and bZ) or (bI and aZ): return 4
    if aZ and bZ: return 3
    return 0

def _count_ped_conflicts(df: pd.DataFrame, col: str) -> int:
    cnt = 0
    by_class = {}
    for _, r in df.iterrows():
        cl = r.get(col)
        if pd.isna(cl): continue
        by_class.setdefault(str(cl), []).append(r)
    for _cl, rows in by_class.items():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                aZ = str(rows[i].get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
                aI = str(rows[i].get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
                bZ = str(rows[j].get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
                bI = str(rows[j].get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
                if _pair_conflict_penalty(aZ, aI, bZ, bI) > 0:
                    cnt += 1
    return cnt

def _sum_conflicts(df: pd.DataFrame, col: str) -> int:
    s = 0
    by_class = {}
    for _, r in df.iterrows():
        cl = r.get(col)
        if pd.isna(cl): continue
        by_class.setdefault(str(cl), []).append(r)
    for _cl, rows in by_class.items():
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                aZ = str(rows[i].get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
                aI = str(rows[i].get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
                bZ = str(rows[j].get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
                bI = str(rows[j].get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
                s += _pair_conflict_penalty(aZ, aI, bZ, bI)
    return s

def _broken_mutual_pairs(df: pd.DataFrame, col: str, scope: Set[str]) -> int:
    pairs = mutual_pairs_in_scope(df, scope)
    name2class = {
        str(r["ΟΝΟΜΑ"]).strip(): str(r.get(col))
        for _, r in df.iterrows()
        if pd.notna(r.get(col))
    }
    return sum(1 for a, b in pairs if name2class.get(a) != name2class.get(b))

def _compute_targets_global(df: pd.DataFrame, step1_col: str, class_labels: List[str]) -> Dict[str, Dict[str, int]]:
    Z_step1 = {cl: 0 for cl in class_labels}
    I_step1 = {cl: 0 for cl in class_labels}
    Z_total_step1 = 0
    I_total_step1 = 0
    for _, r in df.iterrows():
        cl = r.get(step1_col)
        z = str(r.get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
        i = str(r.get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
        if not pd.isna(cl):
            if z:
                Z_step1[str(cl)] += 1
                Z_total_step1 += 1
            if i:
                I_step1[str(cl)] += 1
                I_total_step1 += 1

    to_place = df[pd.isna(df[step1_col])]
    Z_to_place = int((to_place["ΖΩΗΡΟΣ"].astype(str).str.strip() == "Ν").sum())
    I_to_place = int((to_place["ΙΔΙΑΙΤΕΡΟΤΗΤΑ"].astype(str).str.strip() == "Ν").sum())

    Z_final_total = Z_total_step1 + Z_to_place
    I_final_total = I_total_step1 + I_to_place

    def _qmax(total):
        q, r = divmod(total, len(class_labels))
        return {"q": q, "max": q + (1 if r > 0 else 0)}

    return {
        "Z": _qmax(Z_final_total),
        "I": _qmax(I_final_total),
        "Z_step1": Z_step1,
        "I_step1": I_step1,
    }

def _prereject(assign_map, next_name, next_cl, df, step1_col, class_labels, targets, conflict_pairs=None) -> bool:
    Zc = targets["Z_step1"].copy()
    Ic = targets["I_step1"].copy()
    tmp = assign_map.copy()
    if next_name and next_cl:
        tmp[next_name] = next_cl

    for n, cl in tmp.items():
        row = df[df["ΟΝΟΜΑ"] == n].iloc[0]
        if str(row.get("ΖΩΗΡΟΣ", "")).strip() == "Ν": Zc[cl] += 1
        if str(row.get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν": Ic[cl] += 1

    for cl in class_labels:
        if Zc[cl] > targets["Z"]["max"]: return False
        if Ic[cl] > targets["I"]["max"]: return False

    # HARD CONSTRAINT δηλωμένων/εξωτερικών συγκρούσεων με το κοινό conflict_guard.
    # Ελέγχει τον next_name απέναντι σε ΟΛΟΥΣ τους ήδη τοποθετημένους
    # στο προσωρινό σενάριο: Step 1 + προσωρινές τοποθετήσεις Step 2.
    if (_conflict_guard is not None) and next_name and next_cl and conflict_pairs and hasattr(_conflict_guard, "can_place_student"):
        tmp_df = df.copy()
        tmp_col = "__STEP2_TMP_CONFLICT_CHECK__"
        tmp_df[tmp_col] = tmp_df[step1_col]
        for n, cl_assigned in assign_map.items():
            tmp_df.loc[tmp_df["ΟΝΟΜΑ"].astype(str).str.strip() == str(n).strip(), tmp_col] = cl_assigned
        try:
            if not _conflict_guard.can_place_student(
                tmp_df,
                next_name,
                next_cl,
                tmp_col,
                conflict_pairs=conflict_pairs,
            ):
                return False
        except Exception as e:
            print(f"⚠️ Αποτυχία can_place_student στο Step 2: {e}")

    # Fallback/παλιός raw έλεγχος αν δεν φορτώθηκε conflict_guard.
    if (_conflict_guard is None) and next_name and next_cl and "ΣΥΓΚΡΟΥΣΗ" in df.columns:
        mask_next = (df["ΟΝΟΜΑ"] == next_name)
        next_conf_cell = df.loc[mask_next, "ΣΥΓΚΡΟΥΣΗ"]
        toks_next = set(parse_friends_cell(next_conf_cell.values[0] if not next_conf_cell.empty else ""))

        fixed_same = df[(pd.notna(df[step1_col])) & (df[step1_col] == next_cl)]
        if any((n in toks_next) for n in fixed_same["ΟΝΟΜΑ"].astype(str).tolist()):
            return False
        # Αντίστροφη μονόπλευρη δήλωση: ο ήδη τοποθετημένος μπορεί να δηλώνει τον next_name.
        for _, rr in fixed_same.iterrows():
            toks_fixed = set(parse_friends_cell(rr.get("ΣΥΓΚΡΟΥΣΗ", "")))
            if next_name in toks_fixed:
                return False

        for n2, cl2 in tmp.items():
            if cl2 != next_cl: continue
            mask_n2 = (df["ΟΝΟΜΑ"] == n2)
            n2_conf_cell = df.loc[mask_n2, "ΣΥΓΚΡΟΥΣΗ"]
            toks2 = set(parse_friends_cell(n2_conf_cell.values[0] if not n2_conf_cell.empty else ""))
            if (next_name in toks2) or (n2 in toks_next):
                return False
    return True

def _extract_step1_id(step1_col_name: str) -> int:
    m = re.search(r'(?:ΒΗΜΑ1_|V1_)ΣΕΝΑΡΙΟ[_\s]*(\d+)', str(step1_col_name))
    return int(m.group(1)) if m else 1

def step2_apply_FIXED_v3(
    df_in: pd.DataFrame,
    step1_col_name: str,
    num_classes: Optional[int] = None,
    *,
    seed: int = 42,
    max_results: int = 5,
) -> List[Tuple[str, pd.DataFrame, Dict[str, Any]]]:
    """
    Επιστρέφει έως max_results σενάρια ως (label, DataFrame, metrics).
    Το DataFrame περιέχει στήλες εισόδου + «ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{k}» όπου k = id του ΒΗΜΑ1_ΣΕΝΑΡΙΟ_k.
    """
    random.seed(seed)
    df = normalize_columns(df_in).copy()
    num_classes = _auto_num_classes(df, num_classes)
    class_labels = [f"Α{i+1}" for i in range(num_classes)]
    scope = scope_step2(df, step1_col=step1_col_name)

    # Πλήρες σύνολο δηλωμένων συγκρούσεων για ΟΛΟ τον πληθυσμό του τρέχοντος σεναρίου.
    # Δεν γίνεται teacher filtering εδώ. Το Step 2 ελέγχει κάθε νέο μαθητή απέναντι
    # σε όλους τους ήδη τοποθετημένους μαθητές.
    conflict_pairs, unresolved_conflicts = _extract_declared_conflict_pairs(df)

    to_place = df[(pd.isna(df[step1_col_name])) & ((df["ΖΩΗΡΟΣ"] == "Ν") | (df["ΙΔΙΑΙΤΕΡΟΤΗΤΑ"] == "Ν"))]["ΟΝΟΜΑ"].astype(str).tolist()
    targets = _compute_targets_global(df, step1_col=step1_col_name, class_labels=class_labels)

    best: List[Tuple[pd.DataFrame, int, int, int, int]] = []
    assign: Dict[str, str] = {}

    def deg(name: str) -> int:
        row = df[df["ΟΝΟΜΑ"] == name].iloc[0]
        return len(parse_friends_cell(row.get("ΣΥΓΚΡΟΥΣΗ", ""))) + len(parse_friends_cell(row.get("ΦΙΛΟΙ", "")))

    to_place_sorted = sorted(
        to_place,
        key=lambda n: (
            -(
                str(df.loc[df["ΟΝΟΜΑ"] == n, "ΖΩΗΡΟΣ"].values[0]).strip() == "Ν"
                and str(df.loc[df["ΟΝΟΜΑ"] == n, "ΙΔΙΑΙΤΕΡΟΤΗΤΑ"].values[0]).strip() == "Ν"
            ),
            -(str(df.loc[df["ΟΝΟΜΑ"] == n, "ΙΔΙΑΙΤΕΡΟΤΗΤΑ"].values[0]).strip() == "Ν"),
            -(str(df.loc[df["ΟΝΟΜΑ"] == n, "ΖΩΗΡΟΣ"].values[0]).strip() == "Ν"),
            -deg(n),
        ),
    )

    def backtrack(i: int) -> None:
        if i == len(to_place_sorted):
            cand = df.copy()
            cand_col = "ΒΗΜΑ2_TMP"
            cand[cand_col] = cand[step1_col_name]
            for n, cl in assign.items():
                cand.loc[cand["ΟΝΟΜΑ"] == n, cand_col] = cl

            counts_new = {cl: 0 for cl in class_labels}
            for cl in assign.values():
                counts_new[cl] += 1
            if sum(counts_new.values()) > 0 and max(counts_new.values()) == sum(counts_new.values()):
                return

            Zc = targets["Z_step1"].copy()
            Ic = targets["I_step1"].copy()
            for n, cl in assign.items():
                row = df[df["ΟΝΟΜΑ"] == n].iloc[0]
                if str(row.get("ΖΩΗΡΟΣ", "")).strip() == "Ν": Zc[cl] += 1
                if str(row.get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν": Ic[cl] += 1
            for cl in class_labels:
                if not (targets["Z"]["q"] <= Zc[cl] <= targets["Z"]["max"]): return
                if not (targets["I"]["q"] <= Ic[cl] <= targets["I"]["max"]): return

            # Τελική ασφάλεια: δεν μπαίνει στη λίστα best σενάριο Step 2
            # που περιέχει έστω μία δηλωμένη/εξωτερική σύγκρουση.
            if _has_declared_conflict_violation(cand, cand_col, conflict_pairs):
                return

            ped_cnt = _count_ped_conflicts(cand, cand_col)
            conf_sum = _sum_conflicts(cand, cand_col)
            broken = _broken_mutual_pairs(cand, cand_col, scope)
            total = conf_sum + 5 * broken
            best.append((cand, ped_cnt, broken, total, conf_sum))
            return

        name = to_place_sorted[i]
        for cl in class_labels:
            if not _prereject(assign, name, cl, df, step1_col_name, class_labels, targets, conflict_pairs=conflict_pairs):
                continue
            assign[name] = cl
            backtrack(i + 1)
            del assign[name]

    backtrack(0)

    if not best:
        tmp = df.copy()
        base_id = _extract_step1_id(step1_col_name)
        tmp[f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{base_id}"] = tmp[step1_col_name]
        return [("option_1", tmp, {"ped_conflicts": None, "broken": None, "penalty": None, "declared_conflict_pairs": int(len(conflict_pairs)), "unresolved_conflicts": int(unresolved_conflicts)})]

    zero_ped = [x for x in best if x[1] == 0]
    selected = []

    total_pairs = len(mutual_pairs_in_scope(df, scope))

    if zero_ped:
        min_broken = min(x[2] for x in zero_ped)
        tier1 = [x for x in zero_ped if x[2] == min_broken]
        min_total = min(x[3] for x in tier1)
        tier2 = [x for x in tier1 if x[3] == min_total]
        selected = tier2
    else:
        min_total = min(x[3] for x in best)
        tier1 = [x for x in best if x[3] == min_total]
        max_preserved = max(total_pairs - x[2] for x in tier1)
        tier2 = [x for x in tier1 if (total_pairs - x[2]) == max_preserved]
        selected = tier2

    results: List[Tuple[str, pd.DataFrame, Dict[str, Any]]] = []
    base_id = _extract_step1_id(step1_col_name)
    for k, (cand, ped_cnt, broken, total, conf_sum) in enumerate(selected, start=1):
        out = cand.copy()
        final_col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{base_id}"
        out[final_col] = out["ΒΗΜΑ2_TMP"]
        out.drop(columns=["ΒΗΜΑ2_TMP"], inplace=True)
        results.append((f"option_{k}", out, {
            "ped_conflicts": int(ped_cnt),
            "broken": int(broken),
            "penalty": int(total),
            "declared_conflict_pairs": int(len(conflict_pairs)),
            "unresolved_conflicts": int(unresolved_conflicts),
        }))
    return results
