from __future__ import annotations
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ΕΝΑ ΑΡΧΕΙΟ — Τελική εξαγωγή χωρίς audit στήλες.
Παράγει για κάθε sheet (ΣΕΝΑΡΙΟ_N): A–H + I..N όπου:
  I = ΒΗΜΑ1_ΣΕΝΑΡΙΟ_N
  J = ΒΗΜΑ2_ΣΕΝΑΡΙΟ_N
  K = ΒΗΜΑ3_ΣΕΝΑΡΙΟ_N
  L = ΒΗΜΑ4_ΣΕΝΑΡΙΟ_N  (μένει όπως ήταν)
  M = ΒΗΜΑ5_ΣΕΝΑΡΙΟ_N  (νέες τοποθετήσεις αν υπάρχει step5_enhanced.py, αλλιώς αντιγραφή L)
  N = ΒΗΜΑ6_ΣΕΝΑΡΙΟ_N  (μετά το Βήμα 6)
ΧΩΡΙΣ καμία audit στήλη.
"""
import re, sys, numpy as np, pandas as pd, importlib.util
from pathlib import Path

BASE = ["Α/Α","ΟΝΟΜΑ","ΦΥΛΟ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ","ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ"]

# ========= Step 6 implementation (embedded) =========
# filename: step_6_final_check_and_fix_100_PERCENT_COMPLIANT.py
"""
Βήμα 6: Τελικός Ποιοτικός και Ποσοτικός Έλεγχος
100% σύμφωνος με προδιαγραφές - ΠΛΗΡΕΙΣ διορθώσεις:
1. Έλεγχος απαραβίαστων περιορισμών Βημάτων 1-2 ΣΕ ΣΧΕΣΗ ΜΕ ΤΗ ΒΑΣΗ (όχι between swaps)
2. Σωστός έλεγχος φιλιών που ΕΠΙΤΡΕΠΕΙ προϋπάρχουσες σπασμένες δυάδες σε swaps
3. Πλήρης audit trail με Population αιτία
"""
_IDCOL = "ID"
import itertools
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import numpy as np

# --------------------------
# Optional shared conflict_guard — hard constraint ΣΥΓΚΡΟΥΣΗ
# --------------------------
try:
    from conflict_guard import (
        extract_conflict_pairs as _cg_extract_conflict_pairs,
        list_conflict_violations as _cg_list_conflict_violations,
        norm_name as _cg_norm_name,
    )
except Exception as _cg_import_error:
    print(f"⚠️ conflict_guard δεν βρέθηκε ή δεν φορτώθηκε σωστά στο Step 6: {_cg_import_error}")
    print("⚠️ Το Step 6 θα χρησιμοποιήσει fallback raw έλεγχο χωρίς fuzzy/canon matching.")
    _cg_extract_conflict_pairs = None
    _cg_list_conflict_violations = None
    def _cg_norm_name(x):
        return re.sub(r"\s+", " ", str(x).strip())

def _conflict_pairs_for_df(df: pd.DataFrame):
    """Εξάγει conflict_pairs με το κοινό conflict_guard, όταν είναι διαθέσιμο."""
    if _cg_extract_conflict_pairs is None:
        return None
    try:
        return _cg_extract_conflict_pairs(df)
    except Exception as e:
        print(f"⚠️ Step 6: αποτυχία extract_conflict_pairs, fallback raw έλεγχος: {e}")
        return None

# --------------------------
# Conflict helper — hard constraint ΣΥΓΚΡΟΥΣΗ
# --------------------------

def _parse_conflict_list(x) -> List[str]:
    """Parsing στήλης ΣΥΓΚΡΟΥΣΗ (ίδια μορφή με ΦΙΛΟΙ)."""
    if isinstance(x, list):
        return [str(t).strip() for t in x if str(t).strip()]
    s = "" if pd.isna(x) else str(x).strip()
    if not s or s.upper() == "NAN":
        return []
    import re as _re
    parts = _re.split(r"[,\|\;/·\n]+", s)
    return [p.strip() for p in parts if p.strip()]


def _swap_creates_conflict(df: pd.DataFrame, class_col: str,
                           fromA_ids: List[str], to_class_B: str,
                           fromB_ids: List[str], to_class_A: str,
                           conflict_pairs=None) -> bool:
    """
    Επιστρέφει True αν η ανταλλαγή θα τοποθετήσει μαθητή σε τμήμα
    όπου υπάρχει δηλωμένη σύγκρουση (αμφίδρομος έλεγχος).
    Αν δεν υπάρχει στήλη ΣΥΓΚΡΟΥΣΗ, επιστρέφει πάντα False.
    """
    # Shared guard path: build the post-swap assignment once and check only
    # violations involving moved students, so pre-existing unrelated conflicts
    # do not incorrectly block every possible swap.
    if _cg_list_conflict_violations is not None and "ΟΝΟΜΑ" in df.columns:
        try:
            pairs = conflict_pairs if conflict_pairs is not None else _conflict_pairs_for_df(df)
            if pairs is not None:
                tmp = df.copy()
                if fromA_ids:
                    tmp.loc[tmp[_IDCOL].isin(fromA_ids), class_col] = to_class_B
                if fromB_ids:
                    tmp.loc[tmp[_IDCOL].isin(fromB_ids), class_col] = to_class_A

                moved_ids = set(list(fromA_ids) + list(fromB_ids))
                moved_names = {
                    _cg_norm_name(x)
                    for x in tmp[tmp[_IDCOL].isin(moved_ids)]["ΟΝΟΜΑ"].astype(str).tolist()
                }

                viol = _cg_list_conflict_violations(tmp, class_col, pairs)
                if viol is not None and not viol.empty:
                    for _, r in viol.iterrows():
                        a = _cg_norm_name(r.get("ΜΑΘΗΤΗΣ_A", ""))
                        b = _cg_norm_name(r.get("ΜΑΘΗΤΗΣ_B", ""))
                        if a in moved_names or b in moved_names:
                            return True
                    return False
        except Exception as e:
            print(f"⚠️ Step 6: conflict_guard swap check απέτυχε, fallback raw έλεγχος: {e}")

    if "ΣΥΓΚΡΟΥΣΗ" not in df.columns or "ΟΝΟΜΑ" not in df.columns:
        return False

    name_of = df.set_index(_IDCOL)["ΟΝΟΜΑ"].astype(str).str.strip().to_dict()

    def _conflicts_of(sid: str) -> set:
        row = df[df[_IDCOL] == sid]
        if row.empty:
            return set()
        return {_cg_norm_name(x) for x in _parse_conflict_list(row.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", ""))}

    def _check_group(moving_ids: List[str], target_class: str) -> bool:
        """Έλεγχος για κάθε μαθητή που μετακινείται στο target_class."""
        # Μαθητές που θα παραμείνουν στο target_class μετά το swap
        leaving_ids = set(fromA_ids if target_class == to_class_B else fromB_ids)
        staying = df[(df[class_col] == target_class) &
                     (~df[_IDCOL].isin(leaving_ids))]["ΟΝΟΜΑ"].astype(str).str.strip().tolist()
        # + όσοι έρχονται μαζί (αν είναι δυάδα)
        arriving_names = {name_of.get(sid, "") for sid in moving_ids}

        for sid in moving_ids:
            mover_name = _cg_norm_name(name_of.get(sid, ""))
            conf_of_mover = _conflicts_of(sid)

            for member_name in staying:
                member_name_c = _cg_norm_name(member_name)
                if member_name_c in conf_of_mover:
                    return True
                # αντίστροφη
                member_row = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == member_name]
                if not member_row.empty:
                    if mover_name in {_cg_norm_name(x) for x in _parse_conflict_list(
                            member_row.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", ""))}:
                        return True
        return False

    if fromA_ids and _check_group(fromA_ids, to_class_B):
        return True
    if fromB_ids and _check_group(fromB_ids, to_class_A):
        return True
    return False

# --------------------------
# Constants / Config
# --------------------------
BOY = "Α"           # Αγόρι
GIRL = "Κ"          # Κορίτσι
GOOD = "Ν"          # Καλή Γνώση/Ζωηρότητα/Ιδιαιτερότητα/Παιδί Εκπαιδευτικού
NOTGOOD = "Ο"       # Όχι Καλή

MAX_PER_CLASS = 25
TARGET_POP_DIFF = 2
TARGET_GENDER_DIFF = 3
TARGET_LANG_DIFF = 3

MAX_ITER = 100  # default: 100 ανταλλαγές — ρυθμίζεται από το Streamlit (100/300/500)

# Αποδεκτές τιμές για στήλη ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ
STEP4_MARKERS = {4, "4", "Βήμα 4", "Step4", "Step4_Group", "Β4", "Β4_Δυάδα"}
STEP5_MARKERS = {5, "5", "Βήμα 5", "Step5", "Step5_Solo", "Β5", "Β5_Μεμονωμένος"}

# Στήλες απαραβίαστων περιορισμών Βημάτων 1-2
PROTECTED_COLS = {
    "ΖΩΗΡΟΣ": "Ζωηρότητα",
    "ΙΔΙΑΙΤΕΡΟΤΗΤΑ": "Ιδιαιτερότητα", 
    "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ": "Παιδιά Εκπαιδευτικών"
}

# Baseline snapshot στήλες για σύγκριση με Βήματα 1-2 ανά κατηγορία
BASELINE_MAPPING = {
    "ΖΩΗΡΟΣ": ["ΤΜΗΜΑ_ΒΗΜΑ2", "ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6", "ΤΜΗΜΑ"],
    "ΙΔΙΑΙΤΕΡΟΤΗΤΑ": ["ΤΜΗΜΑ_ΒΗΜΑ2", "ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6", "ΤΜΗΜΑ"], 
    "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ": ["ΤΜΗΜΑ_ΒΗΜΑ1", "ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6", "ΤΜΗΜΑ"]
}

# --------------------------
# Utility Functions
# --------------------------
def _classes(df: pd.DataFrame, class_col: str) -> List[str]:
    """Επιστρέφει τα μοναδικά τμήματα."""
    cls = list(df[class_col].dropna().unique())
    if len(cls) < 2:
        raise ValueError("Απαιτούνται τουλάχιστον 2 τμήματα.")
    return cls

def _metrics(df: pd.DataFrame, class_col: str, gender_col: str, lang_col: str, group_col: str = "GROUP_ID") -> Dict[str, Any]:
    """
    Υπολογίζει μετρικές ανά τμήμα και συνολικές αποκλίσεις.
    
    Returns:
        Dict με 'per_class', 'deltas', 'extremes', 'broken_friendships_per_class'
    """
    per_class = {}
    broken_per_class = {}
    
    for c, sub in df.groupby(class_col):
        per_class[c] = dict(
            total=len(sub),
            boys=(sub[gender_col] == BOY).sum(),
            girls=(sub[gender_col] == GIRL).sum(),
            good=(sub[lang_col] == GOOD).sum(),
        )
        
        # Υπολογισμός σπασμένων φιλιών ανά τμήμα
        if group_col in df.columns:
            # Βρίσκω όλες τις δυάδες που έχουν τουλάχιστον ένα μέλος σε αυτό το τμήμα
            groups_in_class = sub.dropna(subset=[group_col])[group_col].unique()
            broken_count = 0
            for gid in groups_in_class:
                # Ελέγχω αν η δυάδα είναι σπασμένη (μέλη σε >1 τμήματα)
                group_classes = df[df[group_col] == gid][class_col].nunique()
                if group_classes > 1:
                    broken_count += 1
            broken_per_class[c] = broken_count
        else:
            broken_per_class[c] = 0
    
    if not per_class:
        return {"per_class": {}, "deltas": {}, "extremes": {}, "broken_friendships_per_class": {}}
    
    totals = [v["total"] for v in per_class.values()]
    boys   = [v["boys"]  for v in per_class.values()]
    girls  = [v["girls"] for v in per_class.values()]
    good   = [v["good"]  for v in per_class.values()]
    
    deltas = dict(
        pop   = (max(totals) - min(totals)) if totals else 0,
        boys  = (max(boys)   - min(boys))   if boys   else 0,
        girls = (max(girls)  - min(girls))  if girls  else 0,
        gender= max((max(boys)-min(boys)) if boys else 0, (max(girls)-min(girls)) if girls else 0),
        lang  = (max(good)   - min(good))  if good   else 0,
    )
    
    def argmax(metric: str) -> Optional[str]:
        return max(per_class.keys(), key=lambda k: per_class[k][metric]) if per_class else None
    
    def argmin(metric: str) -> Optional[str]:
        return min(per_class.keys(), key=lambda k: per_class[k][metric]) if per_class else None
    
    extremes = dict(
        pop_high = argmax("total"),  pop_low  = argmin("total"),
        boys_high= argmax("boys"),   boys_low = argmin("boys"),
        girls_high=argmax("girls"),  girls_low= argmin("girls"),
        lang_high= argmax("good"),   lang_low = argmin("good"),
    )
    
    return {
        "per_class": per_class, 
        "deltas": deltas, 
        "extremes": extremes,
        "broken_friendships_per_class": broken_per_class
    }

def penalty_score(df: pd.DataFrame, class_col: str, gender_col: str, lang_col: str) -> int:
    """
    Υπολογίζει penalty score σύμφωνα με τις προδιαγραφές:
    - Πληθυσμός: +3 * max(0, Δπληθ - 1)
    - Γλώσσα:    +1 * max(0, Δγλώσσας - 2)
    - Φύλο:      +2 * (max(0, Δαγοριών-1) + max(0, Δκοριτσιών-1))
    """
    try:
        M = _metrics(df, class_col, gender_col, lang_col)
        d = M["deltas"]
        boys_over = max(0, d["boys"] - 1)
        girls_over = max(0, d["girls"] - 1)
        return 3 * max(0, d["pop"] - 1) + 1 * max(0, d["lang"] - 2) + 2 * (boys_over + girls_over)
    except Exception as e:
        print(f"Warning: penalty_score calculation failed: {e}")
        return 9999

def _is_step4(val) -> bool: 
    """Ελέγχει αν η τιμή αντιστοιχεί σε Βήμα 4."""
    return val in STEP4_MARKERS

def _is_step5(val) -> bool: 
    """Ελέγχει αν η τιμή αντιστοιχεί σε Βήμα 5."""
    return val in STEP5_MARKERS

def _find_baseline_col_for_category(df: pd.DataFrame, category_col: str) -> str:
    """Βρίσκει τη κατάλληλη baseline στήλη για κάθε κατηγορία περιορισμών."""
    if category_col in BASELINE_MAPPING:
        for baseline_col in BASELINE_MAPPING[category_col]:
            if baseline_col in df.columns:
                return baseline_col
    # Fallback στην τρέχουσα στήλη αν δε βρεθεί baseline
    return None

def _eligible_units(df: pd.DataFrame, class_col: str, step_col: str, group_col: str,
                    gender_col: str, lang_col: str) -> Tuple[Dict[str, List], Dict[str, List]]:
    """
    Επιστρέφει (singles, pairs):
    - singles[class] = IDs μεμονωμένων Βήματος 5
    - pairs[class]   = λίστα δυάδων Βήματος 4 με metadata
    
    ✅ ΔΙΟΡΘΩΣΗ: ΕΠΙΤΡΕΠΕΙ σπασμένες δυάδες σε swaps (δεν τις φιλτράρει)
    """
    classes = _classes(df, class_col)
    singles = {c: [] for c in classes}
    pairs   = {c: [] for c in classes}

    # Μεμονωμένοι: Βήμα 5, χωρίς group
    try:
        mask_solo = df[step_col].map(_is_step5) & (df[group_col].isna() | (df[group_col] == ""))
        for c, sub in df[mask_solo].groupby(class_col):
            singles[c] = sub[_IDCOL].tolist()
    except Exception as e:
        print(f"Warning: Error processing singles: {e}")

    # Δυάδες: Βήμα 4, με group δύο μελών
    try:
        df_pairs = df[df[step_col].map(_is_step4) & df[group_col].notna()].copy()
        if not df_pairs.empty:
            for gid, g in df_pairs.groupby(group_col):
                if len(g) != 2:
                    continue
                
                # ✅ ΔΙΟΡΘΩΣΗ: Δέχεται δυάδες σε διαφορετικά τμήματα (προϋπάρχουσες σπασμένες)
                classes_in_group = g[class_col].unique()
                
                genders = list(g[gender_col])
                langs   = list(g[lang_col])
                
                # Κατηγοριοποίηση φύλου
                if genders.count(BOY) == 2:   
                    gender_kind = BOY
                elif genders.count(GIRL) == 2:
                    gender_kind = GIRL
                else:                         
                    gender_kind = "ΜΙΚΤΟ"
                
                # Κατηγοριοποίηση γλώσσας
                if langs.count(GOOD) == 2:    
                    lang_kind = "NN"
                elif langs.count(NOTGOOD) == 2: 
                    lang_kind = "OO"
                else:                         
                    lang_kind = "N+O"
                
                is_split = len(classes_in_group) > 1
                
                # ✅ ΔΙΟΡΘΩΣΗ: Προσθέτει τη δυάδα σε ΟΛΑ τα τμήματα που συμμετέχει
                # και την κάνει eligible για swaps ανεξάρτητα αν είναι σπασμένη
                for class_name in classes_in_group:
                    pairs[class_name].append({
                        'group_id': gid, 
                        'ids': list(g[_IDCOL]), 
                        'gender_kind': gender_kind, 
                        'lang_kind': lang_kind,
                        'is_split': is_split,
                        'all_classes': list(classes_in_group)  # Για audit
                    })
                    
    except Exception as e:
        print(f"Warning: Error processing pairs: {e}")

    return singles, pairs

def _check_size_ok(df: pd.DataFrame, class_col: str) -> bool:
    """Ελέγχει ότι κανένα τμήμα δεν υπερβαίνει τα 25 άτομα."""
    try:
        return (df[class_col].value_counts() <= MAX_PER_CLASS).all()
    except Exception:
        return False

def _check_protected_constraints(df_baseline: pd.DataFrame, df_after: pd.DataFrame, 
                                class_col: str, step_col: str) -> bool:
    """
    ✅ ΔΙΟΡΘΩΣΗ: Ελέγχει ότι δεν αλλάζει η κατανομή Ζωηρών/Ιδιαιτερότητας/Παιδιών εκπαιδευτικών
    ανά τμήμα με ΣΩΣΤΗ BASELINE ΑΝΑ ΚΑΤΗΓΟΡΙΑ:
    - ΖΩΗΡΟΣ & ΙΔΙΑΙΤΕΡΟΤΗΤΑ: έναντι Βήματος 2
    - ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ: έναντι Βήματος 1
    """
    try:
        for col_name, description in PROTECTED_COLS.items():
            if col_name not in df_baseline.columns or col_name not in df_after.columns:
                continue
                
            # ✅ ΚΡΙΣΙΜΗ ΔΙΟΡΘΩΣΗ: Baseline ανά κατηγορία
            baseline_class_col = _find_baseline_col_for_category(df_baseline, col_name)
            if baseline_class_col is None:
                print(f"Warning: No baseline found for {col_name}, using current class column")
                baseline_class_col = class_col
                
            baseline_counts = df_baseline.groupby(baseline_class_col)[col_name].apply(
                lambda x: (x == GOOD).sum()
            ).to_dict()
            
            after_counts = df_after.groupby(class_col)[col_name].apply(
                lambda x: (x == GOOD).sum()
            ).to_dict()
            
            # Έλεγχος ότι δεν άλλαξε η κατανομή για κάθε τμήμα
            for class_name in set(baseline_counts.keys()) | set(after_counts.keys()):
                baseline_val = baseline_counts.get(class_name, 0)
                after_val = after_counts.get(class_name, 0)
                if baseline_val != after_val:
                    return False
                
        return True
    except Exception as e:
        print(f"Warning: Error checking protected constraints: {e}")
        return False

def _check_friendship_constraints(df_before: pd.DataFrame, df_after: pd.DataFrame, 
                                 class_col: str, group_col: str) -> bool:
    """
    ✅ ΔΙΟΡΘΩΣΗ: Ελέγχει τις φιλίες σύμφωνα με προδιαγραφές:
    1. Μη αύξηση αριθμού σπασμένων φιλιών (σε σχέση με το Βήμα 5)
    2. Απαγόρευση επανένωσης προϋπάρχουσων σπασμένων φιλιών
    3. Δεν επιτρέπεται διάσπαση ήδη ενωμένων δυάδων
    
    ΔΕΝ απαιτεί όλες οι δυάδες να είναι ενωμένες - επιτρέπει προϋπάρχουσες σπασμένες.
    """
    try:
        if group_col not in df_before.columns or group_col not in df_after.columns:
            return True
            
        def get_group_status(df):
            """
            Επιστρέφει dict: {group_id: {'classes': set, 'is_split': bool}}
            """
            groups_with_data = df.dropna(subset=[group_col])
            if groups_with_data.empty:
                return {}
                
            result = {}
            for gid, group_df in groups_with_data.groupby(group_col):
                classes = set(group_df[class_col])
                result[gid] = {
                    'classes': classes,
                    'is_split': len(classes) > 1
                }
            return result
        
        before_groups = get_group_status(df_before)
        after_groups = get_group_status(df_after)
        
        # Βρίσκουμε όλες τις δυάδες που υπήρχαν πριν ή μετά
        all_group_ids = set(before_groups.keys()) | set(after_groups.keys())
        
        split_before_count = sum(1 for g in before_groups.values() if g['is_split'])
        split_after_count = sum(1 for g in after_groups.values() if g['is_split'])
        
        # 1. Μη αύξηση αριθμού σπασμένων φιλιών
        if split_after_count > split_before_count:
            return False
        
        # 2. Έλεγχος για επανενώσεις και νέες διασπάσεις
        for gid in all_group_ids:
            before_status = before_groups.get(gid, {'classes': set(), 'is_split': False})
            after_status = after_groups.get(gid, {'classes': set(), 'is_split': False})
            
            was_split = before_status['is_split']
            is_now_split = after_status['is_split']
            
            # Απαγόρευση επανένωσης: προϋπάρχουσα σπασμένη δεν γίνεται ενωμένη
            if was_split and not is_now_split and len(after_status['classes']) > 0:
                return False
                
            # Απαγόρευση νέας διάσπασης: ενωμένη δεν γίνεται σπασμένη
            if not was_split and is_now_split:
                return False
                
        return True
        
    except Exception as e:
        print(f"Warning: Error checking friendship constraints: {e}")
        return False

# --------------------------
# Swap Operations
# --------------------------
def _apply_swap(df: pd.DataFrame, class_col: str,
                fromA_ids: List[str], to_class_B: str,
                fromB_ids: List[str], to_class_A: str,
                reason: str, swap_idx: int,
                step_col: str, group_col: str) -> pd.DataFrame:
    """Εφαρμόζει ανταλλαγή μεταξύ δύο τμημάτων."""
    df = df.copy()
    
    # Εφαρμογή ανταλλαγής
    if fromA_ids:
        df.loc[df[_IDCOL].isin(fromA_ids), class_col] = to_class_B
    if fromB_ids:
        df.loc[df[_IDCOL].isin(fromB_ids), class_col] = to_class_A

    # Audit trail
    swap_id = f"SWAP_{swap_idx}"
    moved_ids = list(fromA_ids) + list(fromB_ids)
    if moved_ids:
        mask = df[_IDCOL].isin(moved_ids)
        df.loc[mask, "ΒΗΜΑ6_ΚΙΝΗΣΗ"] = swap_id
        df.loc[mask, "ΑΙΤΙΑ_ΑΛΛΑΓΗΣ"] = reason
        df.loc[mask, "ΠΗΓΗ_ΒΗΜΑ"] = np.where(
            df.loc[mask, group_col].notna(), 
            "Β4_Δυάδα", 
            "Β5_Μεμονωμένος"
        )
    
    return df

def _determine_reason(df_before: pd.DataFrame, class_col: str, gender_col: str, 
                     lang_col: str, objective: str) -> str:
    """
    Καθορίζει την αιτία ανταλλαγής βάσει στόχου και τρέχουσας κατάστασης.
    """
    metrics = _metrics(df_before, class_col, gender_col, lang_col)
    deltas = metrics["deltas"]
    
    within_targets = (
        deltas["pop"] <= TARGET_POP_DIFF and
        deltas["gender"] <= TARGET_GENDER_DIFF and 
        deltas["lang"] <= TARGET_LANG_DIFF
    )
    
    if within_targets and objective == "BOTH":
        return "Population"  # Βελτίωση penalty εντός στόχων
    elif objective == "LANG":
        return "Language"
    elif objective == "GENDER":
        return "Gender" 
    else:
        # Μικτή κατάσταση - προτεραιότητα στο φύλο
        return "Gender" if deltas["gender"] >= deltas["lang"] else "Language"

def _rank_candidates(df_before: pd.DataFrame, df_baseline: pd.DataFrame,
                     class_col: str, gender_col: str, lang_col: str,
                     step_col: str, group_col: str,
                     candidates: List, objective: str) -> List:
    """
    Κατατάσσει υποψήφιες ανταλλαγές βάσει στόχου με πλήρεις ελέγχους συμμόρφωσης.
    ✅ ΔΙΟΡΘΩΣΗ: Περιλαμβάνει έλεγχο baseline constraints.
    """
    base_M = _metrics(df_before, class_col, gender_col, lang_col)
    base_d = base_M["deltas"]
    base_pen = penalty_score(df_before, class_col, gender_col, lang_col)
    ranked = []

    for (fromA, classA, fromB, classB, base_reason) in candidates:
        try:
            # Καθορισμός σωστής αιτίας
            reason = _determine_reason(df_before, class_col, gender_col, lang_col, objective)
            
            tmp = _apply_swap(df_before, class_col, fromA, classB, fromB, classA, 
                            reason, 9999, step_col=step_col, group_col=group_col)
            
            # 1. Έλεγχος μεγέθους τμημάτων
            if not _check_size_ok(tmp, class_col):
                continue
                
            # 2. ✅ ΔΙΟΡΘΩΣΗ: Έλεγχος απαραβίαστων περιορισμών με baseline ανά κατηγορία
            if not _check_protected_constraints(df_baseline, tmp, class_col, step_col):
                continue
                
            # 3. Έλεγχος φιλιών (σπασμένες/επανενώσεις)
            if not _check_friendship_constraints(df_before, tmp, class_col, group_col):
                continue
                
            M = _metrics(tmp, class_col, gender_col, lang_col)
            d = M["deltas"]
            
            # 4. Πληθυσμιακός έλεγχος (αυστηροποίηση)
            if d["pop"] > TARGET_POP_DIFF:
                continue
            if base_d["pop"] <= TARGET_POP_DIFF and d["pop"] > base_d["pop"]:
                continue

            pen = penalty_score(tmp, class_col, gender_col, lang_col)
            dlang_gain   = base_d["lang"]   - d["lang"]
            dgender_gain = base_d["gender"] - d["gender"]
            pen_gain     = base_pen - pen

            # 5. Έλεγχος μη-επιδείνωσης του άλλου δείκτη
            if objective == "LANG"   and dgender_gain < 0: 
                continue
            if objective == "GENDER" and dlang_gain   < 0: 
                continue
            if objective == "BOTH"   and (dlang_gain < 0 or dgender_gain < 0): 
                continue

            # Κατάταξη βάσει στόχου
            if objective in ("GENDER", "BOTH"):
                key = (-dgender_gain, -dlang_gain, -pen_gain, len(fromA) + len(fromB))
            else:
                key = (-dlang_gain, -dgender_gain, -pen_gain, len(fromA) + len(fromB))
                
            ranked.append((key, fromA, classA, fromB, classB, reason))
            
        except Exception as e:
            print(f"Warning: Error evaluating candidate swap: {e}")
            continue

    ranked.sort(key=lambda x: x[0])
    return [(fromA, classA, fromB, classB, reason) for _, fromA, classA, fromB, classB, reason in ranked]

# --------------------------
# Candidate Generation
# --------------------------
def _enum_LANG(df: pd.DataFrame, class_col: str, gender_col: str, lang_col: str,
               step_col: str, group_col: str, top_k: int = 2) -> List:
    """
    Παράγει υποψήφιες ανταλλαγές για διόρθωση γλώσσας.
    ✅ ΔΙΟΡΘΩΣΗ: ΔΕΝ φιλτράρει σπασμένες δυάδες - τις επιτρέπει σε swaps.
    """
    M = _metrics(df, class_col, gender_col, lang_col)
    per_class = M["per_class"]
    
    # Ταξινόμηση τμημάτων κατά 'good' γλώσσα
    classes_sorted = sorted(per_class.keys(), key=lambda c: per_class[c]["good"], reverse=True)
    highs = classes_sorted[:top_k]
    lows  = list(reversed(classes_sorted))[:top_k]

    singles, pairs = _eligible_units(df, class_col, step_col, group_col, gender_col, lang_col)
    candidates = []
    
    try:
        for high in highs:
            for low in lows:
                if high == low: 
                    continue
                
                # 1↔1 (Καλή Γνώση ↔ Όχι Καλή)
                singles_high_good = df[df[_IDCOL].isin(singles[high]) & (df[lang_col] == GOOD)][_IDCOL].tolist()
                singles_low_not   = df[df[_IDCOL].isin(singles[low])  & (df[lang_col] == NOTGOOD)][_IDCOL].tolist()
                
                for i in singles_high_good:
                    for j in singles_low_not:
                        candidates.append(([i], high, [j], low, "Language"))
                
                # ✅ ΔΙΟΡΘΩΣΗ: 2↔2 (NN ↔ OO) - ΧΩΡΙΣ φιλτράρισμα σπασμένων δυάδων
                pairs_high_NN = [p for p in pairs[high] if p["lang_kind"] == "NN"]
                pairs_low_OO  = [p for p in pairs[low]  if p["lang_kind"] == "OO"]
                
                for pNN in pairs_high_NN:
                    for pOO in pairs_low_OO:
                        candidates.append((pNN["ids"], high, pOO["ids"], low, "Language"))
                
                # ✅ ΔΙΟΡΘΩΣΗ: 2↔1+1 scenarios - ΧΩΡΙΣ φιλτράρισμα σπασμένων
                if pairs_high_NN and len(singles_low_not) >= 2:
                    for pNN in pairs_high_NN:
                        for two in itertools.combinations(singles_low_not, 2):
                            candidates.append((pNN["ids"], high, list(two), low, "Language"))
                
                # Αντίστροφα (OO ↔ Ν+Ν)
                pairs_high_OO = [p for p in pairs[high] if p["lang_kind"] == "OO"]
                singles_low_good = df[df[_IDCOL].isin(singles[low]) & (df[lang_col] == GOOD)][_IDCOL].tolist()
                
                if pairs_high_OO and len(singles_low_good) >= 2:
                    for pOO in pairs_high_OO:
                        for two in itertools.combinations(singles_low_good, 2):
                            candidates.append((list(two), low, pOO["ids"], high, "Language"))
                            
    except Exception as e:
        print(f"Warning: Error generating language candidates: {e}")
    
    return candidates

def _enum_GENDER(df: pd.DataFrame, class_col: str, gender_col: str, lang_col: str,
                 step_col: str, group_col: str, top_k: int = 2) -> List:
    """
    Παράγει υποψήφιες ανταλλαγές για διόρθωση φύλου.
    ✅ ΔΙΟΡΘΩΣΗ: ΔΕΝ φιλτράρει σπασμένες δυάδες - τις επιτρέπει σε swaps.
    """
    M = _metrics(df, class_col, gender_col, lang_col)
    per_class = M["per_class"]
    deltas = M["deltas"]
    
    # Καθορισμός target φύλου (το φύλο με μεγαλύτερη απόκλιση)
    target_gender = BOY if deltas["boys"] >= deltas["girls"] else GIRL
    opp_gender = GIRL if target_gender == BOY else BOY
    
    # Ταξινόμηση τμημάτων κατά πλήθος target φύλου
    metric = "boys" if target_gender == BOY else "girls"
    classes_sorted = sorted(per_class.keys(), key=lambda c: per_class[c][metric], reverse=True)
    highs = classes_sorted[:top_k]
    lows  = list(reversed(classes_sorted))[:top_k]

    singles, pairs = _eligible_units(df, class_col, step_col, group_col, gender_col, lang_col)
    candidates = []
    
    try:
        for high in highs:
            for low in lows:
                if high == low: 
                    continue
                
                # 1↔1 (target_gender ↔ opp_gender)
                ids_high_target = df[df[_IDCOL].isin(singles[high]) & (df[gender_col] == target_gender)][_IDCOL].tolist()
                ids_low_opp = df[df[_IDCOL].isin(singles[low]) & (df[gender_col] == opp_gender)][_IDCOL].tolist()
                
                for i in ids_high_target:
                    # Προτίμηση ίδιας γλώσσας
                    lang_i = df.loc[df[_IDCOL] == i, lang_col].iloc[0]
                    same_lang = df[
                        df[_IDCOL].isin(singles[low]) & 
                        (df[gender_col] == opp_gender) & 
                        (df[lang_col] == lang_i)
                    ][_IDCOL].tolist()
                    
                    for j in same_lang:
                        candidates.append(([i], high, [j], low, "Gender"))
                    for j in ids_low_opp:
                        candidates.append(([i], high, [j], low, "Gender"))
                
                # ✅ ΔΙΟΡΘΩΣΗ: 2↔2 - ΧΩΡΙΣ φιλτράρισμα σπασμένων δυάδων
                pairs_high_target = [p for p in pairs[high] if p["gender_kind"] == target_gender]
                pairs_low_opp = [p for p in pairs[low] if p["gender_kind"] == opp_gender]
                
                for p1 in pairs_high_target:
                    for p2 in pairs_low_opp:
                        candidates.append((p1["ids"], high, p2["ids"], low, "Gender"))
                
                # ✅ ΔΙΟΡΘΩΣΗ: 2↔1+1 - ΧΩΡΙΣ φιλτράρισμα σπασμένων δυάδων
                for p1 in pairs_high_target:
                    if len(ids_low_opp) >= 2:
                        for two in itertools.combinations(ids_low_opp, 2):
                            candidates.append((p1["ids"], high, list(two), low, "Gender"))
                            
    except Exception as e:
        print(f"Warning: Error generating gender candidates: {e}")
    
    return candidates

def _enum_BOTH(df: pd.DataFrame, class_col: str, gender_col: str, lang_col: str,
               step_col: str, group_col: str, top_k: int = 2) -> List:
    """Παράγει υποψήφιες ανταλλαγές για ταυτόχρονη διόρθωση."""
    candidates = []
    candidates += _enum_LANG(df, class_col, gender_col, lang_col, step_col, group_col, top_k=top_k)
    candidates += _enum_GENDER(df, class_col, gender_col, lang_col, step_col, group_col, top_k=top_k)
    return candidates

def _commit_best_swap_if_improves(df: pd.DataFrame, df_baseline: pd.DataFrame,
                                  class_col: str, gender_col: str, lang_col: str,
                                  step_col: str, group_col: str, objective: str, swap_idx: int,
                                  conflict_pairs=None) -> Tuple[pd.DataFrame, bool]:
    """
    Επιχειρεί να βρει και εφαρμόσει τη βέλτιστη ανταλλαγή με πλήρεις ελέγχους συμμόρφωσης.
    ✅ ΔΙΟΡΘΩΣΗ: Περιλαμβάνει baseline constraints checking.
    """
    
    # Παραγωγή υποψηφίων
    if objective == "LANG":
        candidates = _enum_LANG(df, class_col, gender_col, lang_col, step_col, group_col)
    elif objective == "GENDER":
        candidates = _enum_GENDER(df, class_col, gender_col, lang_col, step_col, group_col)
    else:  # BOTH
        candidates = _enum_BOTH(df, class_col, gender_col, lang_col, step_col, group_col)

    ranked = _rank_candidates(df, df_baseline, class_col, gender_col, lang_col, step_col, group_col, candidates, objective)
    if not ranked: 
        return df, False

    base_penalty = penalty_score(df, class_col, gender_col, lang_col)

    # Δοκιμή καλύτερης ανταλλαγής - ήδη φιλτραρισμένη από _rank_candidates
    for (fromA, classA, fromB, classB, reason) in ranked:
        try:
            # Hard constraint: απόρριψη αν το swap δημιουργεί σύγκρουση
            if _swap_creates_conflict(df, class_col, fromA, classB, fromB, classA, conflict_pairs):
                continue

            tmp = _apply_swap(df, class_col, fromA, classB, fromB, classA, reason, swap_idx, step_col, group_col)
            
            # Όλοι οι έλεγχοι έχουν ήδη γίνει στο _rank_candidates
            # Απλά ελέγχουμε τη βελτίωση penalty
            new_penalty = penalty_score(tmp, class_col, gender_col, lang_col)
            if new_penalty < base_penalty:
                return tmp, True
                
        except Exception as e:
            print(f"Warning: Error applying swap: {e}")
            continue
    
    return df, False

# --------------------------
# Public API
# --------------------------
def pick_best_step6(step6_results: Dict[str, Dict]) -> Tuple[str, pd.DataFrame, Dict]:
    """
    Επιλέγει το καλύτερο σενάριο από τα αποτελέσματα του Βήματος 6.
    Κριτήριο: χαμηλότερο penalty (αν υπάρχει στο summary), αλλιώς πρώτο non-ERROR.
    """
    best_name, best_result = None, None
    best_penalty = float("inf")
    for name, result in step6_results.items():
        if result.get("summary", {}).get("status") == "ERROR":
            continue
        pen = result.get("summary", {}).get("final_penalty", float("inf"))
        if pen < best_penalty:
            best_penalty = pen
            best_name = name
            best_result = result
    if best_result is None:
        # Fallback: πρώτο διαθέσιμο
        best_name, best_result = next(iter(step6_results.items()))
    return best_name, best_result["df"], best_result.get("summary", {})


def step6_generate_scenarios(
    step5_scenarios: List[Tuple[str, pd.DataFrame, int]],
    *,
    class_col: str = "ΤΜΗΜΑ",
    id_col: str = "ID",
    gender_col: str = "ΦΥΛΟ",
    lang_col: str = "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ",
    step_col: str = "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ",
    group_col: str = "GROUP_ID",
    max_iter: int = MAX_ITER,
    max_results: int = 5,
) -> List[Tuple[str, pd.DataFrame, Dict]]:
    """
    Εφαρμόζει Βήμα 6 σε έως max_results σενάρια από το Βήμα 5.
    Επιστρέφει List[(label, df, summary)] ταξινομημένα βάσει final_penalty.
    """
    results: List[Tuple[str, pd.DataFrame, Dict]] = []
    for label, df5, _pen5 in step5_scenarios[:max_results]:
        try:
            result = apply_step6(
                df5.copy(),
                class_col=class_col, id_col=id_col,
                gender_col=gender_col, lang_col=lang_col,
                step_col=step_col, group_col=group_col,
                max_iter=max_iter,
            )
            results.append((label, result["df"], result.get("summary", {})))
        except Exception as e:
            print(f"Βήμα 6 σφάλμα για {label}: {e}")

    results.sort(key=lambda x: x[2].get("final_penalty", float("inf")))
    return results


def apply_step6_to_step5_scenarios(step5_outputs: Dict[str, pd.DataFrame],
                                   *, class_col: str = "ΤΜΗΜΑ", id_col: str = "ID", 
                                   gender_col: str = "ΦΥΛΟ", lang_col: str = "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ", 
                                   step_col: str = "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ", group_col: str = "GROUP_ID", 
                                   max_iter: int = MAX_ITER) -> Dict[str, Dict]:
    """
    Εφαρμόζει το Βήμα 6 σε πολλαπλά σενάρια από το Βήμα 5.
    
    Args:
        step5_outputs: Dict με σενάρια {"ΣΕΝΑΡΙΟ_1": df5_1, ...}
        
    Returns:
        Dict με ίδια keys και values {"df": df6, "summary": {...}}
    """
    results = {}
    for name, df5 in step5_outputs.items():
        try:
            result = apply_step6(df5.copy(), class_col=class_col, id_col=id_col, 
                               gender_col=gender_col, lang_col=lang_col, 
                               step_col=step_col, group_col=group_col, max_iter=max_iter)
            results[name] = result
        except Exception as e:
            print(f"Error processing scenario {name}: {e}")
            results[name] = {"df": df5.copy(), "summary": {"status": "ERROR", "error": str(e)}}
    
    return results

def apply_step6(df: pd.DataFrame,
                *, class_col: str = "ΤΜΗΜΑ", id_col: str = "ID", 
                gender_col: str = "ΦΥΛΟ", lang_col: str = "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ",
                step_col: str = "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ", group_col: str = "GROUP_ID", 
                max_iter: int = MAX_ITER, conflict_pairs: Optional[Any] = None) -> Dict[str, Any]:
    """
    Εφαρμογή Βήματος 6: Τελικός Ποιοτικός και Ποσοτικός Έλεγχος.
    
    ✅ 100% σύμφωνος με προδιαγραφές:
    - Απαραβίαστοι περιορισμοί Βημάτων 1-2 σε σχέση με βάση (όχι between swaps)
    - Σωστός έλεγχος φιλιών που επιτρέπει προϋπάρχουσες σπασμένες δυάδες σε swaps
    - Πλήρης audit trail με Population αιτία
    
    Στόχοι:
    - Πληθυσμός: διαφορά ≤2
    - Φύλο: διαφορά ≤3  
    - Γλώσσα: διαφορά ≤3
    
    Κινούνται ΜΟΝΟ:
    - Δυάδες Β4 (αδιαίρετες, ΣΥΜΠΕΡΙΛΑΜΒΑΝΟΜΕΝΩΝ σπασμένων)
    - Μεμονωμένοι Β5
    
    Args:
        df: DataFrame με μαθητές μετά το Βήμα 5
        max_iter: Μέγιστος αριθμός επαναλήψεων
        
    Returns:
        Dict με "df" (βελτιωμένο DataFrame) και "summary" (στατιστικά)
    """
    # Αρχικοποίηση
    global _IDCOL
    _IDCOL = id_col
    
    # Δημιουργία snapshot πριν το Βήμα 6
    if "ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6" not in df.columns and class_col in df.columns:
        df["ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6"] = df[class_col]

    # ΔΙΟΡΘΩΣΗ: υπολογισμός conflict_pairs ΜΙΑ ΦΟΡΑ εδώ, αν δεν έχει ήδη
    # περαστεί έτοιμο από τον καλούντα (π.χ. κοινό Βήμα 0). Χωρίς αυτό, η
    # _swap_creates_conflict() θα το ξαναϋπολόγιζε (fuzzy matching στη
    # ΣΥΓΚΡΟΥΣΗ) για ΚΑΘΕ υποψήφιο swap, σε ΚΑΘΕ iteration έως max_iter.
    if conflict_pairs is None:
        conflict_pairs = _conflict_pairs_for_df(df)

    # Έλεγχος απαραίτητων στηλών
    required_cols = [id_col, class_col, gender_col, lang_col, step_col]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Λείπουν στήλες: {missing_cols}")
    
    # ✅ ΔΙΟΡΘΩΣΗ: Εντοπισμός baseline στηλών ανά κατηγορία για έλεγχο περιορισμών Βημάτων 1-2
    available_baselines = {}
    for category_col in PROTECTED_COLS.keys():
        if category_col in df.columns:
            baseline_col = _find_baseline_col_for_category(df, category_col)
            available_baselines[category_col] = baseline_col or class_col
    
    # Δημιουργία baseline snapshot για τους ελέγχους
    df_baseline = df.copy()
    
    # Προετοιμασία στηλών
    if group_col not in df.columns:
        df = df.copy()
        df[group_col] = np.nan

    # Audit στήλες
    audit_cols = ["ΒΗΜΑ6_ΚΙΝΗΣΗ", "ΑΙΤΙΑ_ΑΛΛΑΓΗΣ", "ΠΗΓΗ_ΒΗΜΑ"]
    for col in audit_cols:
        if col not in df.columns:
            df[col] = None

    if available_baselines:
        print(f"Baseline mapping for protected constraints: {available_baselines}")

    # Έλεγχος διαθεσιμότητας προστατευόμενων στηλών
    available_protected = [col for col in PROTECTED_COLS.keys() if col in df.columns]
    if available_protected:
        print(f"Protecting constraints for: {', '.join(available_protected)}")

    # Κύριος αλγόριθμος
    iterations = 0
    status = "VALID"
    
    try:
        while iterations < max_iter:
            iterations += 1
            metrics = _metrics(df, class_col, gender_col, lang_col)
            deltas = metrics["deltas"]
            
            # Έλεγχος στόχων
            within_targets = (
                deltas["pop"] <= TARGET_POP_DIFF and
                deltas["gender"] <= TARGET_GENDER_DIFF and 
                deltas["lang"] <= TARGET_LANG_DIFF
            )

            # Καθορισμός στόχου με σειριακή προτεραιότητα για ταυτόχρονη απόκλιση
            if not within_targets:
                if deltas["gender"] > TARGET_GENDER_DIFF and deltas["lang"] > TARGET_LANG_DIFF:
                    # Γ: Ταυτόχρονη απόκλιση - προτεραιότητα στο φύλο
                    df_new, changed = _commit_best_swap_if_improves(
                        df, df_baseline, class_col, gender_col, lang_col, 
                        step_col, group_col, "GENDER", iterations, conflict_pairs
                    )
                    if not changed:
                        # Αν δεν βελτιώθηκε το φύλο, δοκίμασε γλώσσα
                        df_new, changed = _commit_best_swap_if_improves(
                            df, df_baseline, class_col, gender_col, lang_col, 
                            step_col, group_col, "LANG", iterations, conflict_pairs
                        )
                elif deltas["gender"] > TARGET_GENDER_DIFF:
                    # Β: Μόνο φύλο εκτός στόχου
                    df_new, changed = _commit_best_swap_if_improves(
                        df, df_baseline, class_col, gender_col, lang_col, 
                        step_col, group_col, "GENDER", iterations, conflict_pairs
                    )
                else:
                    # Α: Μόνο γλώσσα εκτός στόχου
                    df_new, changed = _commit_best_swap_if_improves(
                        df, df_baseline, class_col, gender_col, lang_col, 
                        step_col, group_col, "LANG", iterations, conflict_pairs
                    )
            else:
                # Εντός στόχων: συνέχεια βελτίωσης (θα καταγραφεί ως Population)
                df_new, changed = _commit_best_swap_if_improves(
                    df, df_baseline, class_col, gender_col, lang_col, 
                    step_col, group_col, "BOTH", iterations, conflict_pairs
                )
            
            if not changed:
                break
            df = df_new

    except Exception as e:
        print(f"Error in step 6 iterations: {e}")
        status = "ERROR"

    # Τελικός έλεγχος
    try:
        final_metrics = _metrics(df, class_col, gender_col, lang_col)
        final_penalty = penalty_score(df, class_col, gender_col, lang_col)
        final_deltas = final_metrics["deltas"]
        
        final_within_targets = (
            final_deltas["pop"] <= TARGET_POP_DIFF and
            final_deltas["gender"] <= TARGET_GENDER_DIFF and 
            final_deltas["lang"] <= TARGET_LANG_DIFF
        )
        
        if not final_within_targets and status != "ERROR":
            status = "Αδυναμία Διόρθωσης (Βήμα 6)"
            
    except Exception as e:
        print(f"Error in final metrics calculation: {e}")
        final_metrics = {"deltas": {}, "per_class": {}}
        final_penalty = 9999
        status = "ERROR"

    # Προετοιμασία εξόδων
    try:
        if "ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" not in df.columns and class_col in df.columns:
            df["ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6"] = df[class_col]
            
        # Στήλη μεταβολής
        if "ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6" in df.columns and "ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" in df.columns:
            df["ΜΕΤΑΒΟΛΗ_ΤΜΗΜΑΤΟΣ"] = np.where(
                df["ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6"].astype(str) == df["ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6"].astype(str),
                "STAY",
                df["ΤΜΗΜΑ_ΠΡΙΝ_ΒΗΜΑ6"].astype(str) + "→" + df["ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6"].astype(str)
            )
        
        # Βήμα 6 τμήμα
        df["ΒΗΜΑ6_ΤΜΗΜΑ"] = df.get("ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6", df.get(class_col))
        
        # Εντοπισμός σεναρίου από Βήμα 5
        import re
        scen_num = None
        for col in df.columns:
            match = re.match(r"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_(\d+)__1$", str(col))
            if match:
                scen_num = match.group(1)
                break
        
        if scen_num and f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{scen_num}__1" not in df.columns:
            df[f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{scen_num}__1"] = df["ΒΗΜΑ6_ΤΜΗΜΑ"]
            
    except Exception as e:
        print(f"Warning: Error preparing output columns: {e}")

        # === Ensure N column (ΒΗΜΑ6_ΣΕΝΑΡΙΟ_N) immediately after M (ΒΗΜΑ5_ΣΕΝΑΡΙΟ_N) ===
        try:
            import re as _re
            _step5_col = None
            _scnum = None
            for _c in df.columns:
                _m = _re.match(r"^ΒΗΜΑ5_ΣΕΝΑΡΙΟ_(\\d+)(?:__\\d+)?$", str(_c))
                if _m:
                    _step5_col = str(_c)
                    _scnum = _m.group(1)
                    break
            _src = "ΒΗΜΑ6_ΤΜΗΜΑ" if "ΒΗΜΑ6_ΤΜΗΜΑ" in df.columns else ("ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" if "ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" in df.columns else None)
            if _scnum and _src:
                _newcol = f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{_scnum}"
                if _newcol in df.columns:
                    df.drop(columns=[_newcol], inplace=True)
                _cols = list(df.columns)
                _ins = _cols.index(_step5_col) + 1 if _step5_col in _cols else len(_cols)
                df.insert(_ins, _newcol, df[_src].values)
                # remove any legacy __1 version if present
                _legacy = f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{_scnum}__1"
                if _legacy in df.columns:
                    df.drop(columns=[_legacy], inplace=True)
        except Exception as _e:
            print(f"Warning: postprocess N column failed: {_e}")

    summary = {
        "iterations": iterations,
        "final_deltas": final_metrics.get("deltas", {}),
        "per_class": final_metrics.get("per_class", {}),
        "broken_friendships_per_class": final_metrics.get("broken_friendships_per_class", {}),
        "final_penalty": final_penalty,
        "status": status,
        "targets": {
            "population": TARGET_POP_DIFF,
            "gender": TARGET_GENDER_DIFF, 
            "language": TARGET_LANG_DIFF
        },
        "protected_columns": available_protected,
        "baseline_mapping": available_baselines
    }

    return {"df": df, "summary": summary}


if __name__ == "__main__":
    # Smoke test με 3 τμήματα, προστατευόμενες στήλες και προϋπάρχουσες σπασμένες δυάδες
    test_data = [
        # Αγόρια σε Α1 - ένα με ιδιαιτερότητα που πρέπει να προστατευθεί
        [1, "Α1", "Α", "Ν", 4, "G1", "Ν", "Ν", "Ο", "Α1", "Α1"],  # Ζωηρός, ιδιαιτερότητα
        [2, "Β1", "Α", "Ν", 4, "G1", "Ν", "Ο", "Ο", "Α1", "Α1"],  # Δυάδα G1 σπασμένη (Α1→Β1)
        
        # Κορίτσια με διαφορετικές ιδιότητες
        [3, "Α1", "Κ", "Ο", 5, None, "Ο", "Ο", "Ν", "Α1", "Α1"],  # Παιδί εκπαιδευτικού
        [4, "Α1", "Κ", "Ν", 5, None, "Ο", "Ο", "Ο", "Α1", "Α1"],

        [5, "Β1", "Κ", "Ο", 4, "G2", "Ν", "Ο", "Ο", "Β1", "Β1"],  # Ζωηρή
        [6, "Β1", "Κ", "Ο", 4, "G2", "Ν", "Ο", "Ο", "Β1", "Β1"],  # Δυάδα G2 ενωμένη
        [7, "Β1", "Α", "Ν", 5, None, "Ο", "Ν", "Ο", "Β1", "Β1"],  # Ιδιαιτερότητα
        [8, "Β1", "Α", "Ο", 5, None, "Ο", "Ο", "Ν", "Β1", "Β1"],  # Παιδί εκπαιδευτικού

        [9,  "Γ1", "Α", "Ν", 5, None, "Ν", "Ο", "Ο", "Γ1", "Γ1"],  # Ζωηρός
        [10, "Γ1", "Κ", "Ν", 5, None, "Ο", "Ν", "Ο", "Γ1", "Γ1"],  # Ιδιαιτερότητα
    ]
    
    df_test = pd.DataFrame(test_data, columns=[
        "ID", "ΤΜΗΜΑ", "ΦΥΛΟ", "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ", "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ", 
        "GROUP_ID", "ΖΩΗΡΟΣ", "ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ", "ΤΜΗΜΑ_ΒΗΜΑ1", "ΤΜΗΜΑ_ΒΗΜΑ2"
    ])
    
    result = apply_step6(df_test)
    print("\n=== TEST RESULTS (100% COMPLIANT VERSION) ===")
    print("Status:", result["summary"]["status"])
    print("Iterations:", result["summary"]["iterations"])
    print("Final deltas:", result["summary"]["final_deltas"])
    print("Final penalty:", result["summary"]["final_penalty"])
    print("Protected columns:", result["summary"]["protected_columns"])
    print("Baseline mapping:", result["summary"]["baseline_mapping"])
    print("Broken friendships per class:", result["summary"]["broken_friendships_per_class"])
    
    # Test έλεγχου σπασμένων φιλιών
    print("\nGroup status test:")
    groups_df = df_test.dropna(subset=["GROUP_ID"])
    for gid, group in groups_df.groupby("GROUP_ID"):
        classes = list(group["ΤΜΗΜΑ"])
        print(f"Group {gid}: {classes} -> {'SPLIT' if len(set(classes)) > 1 else 'UNITED'}")


# ========= Helper loaders =========
def _imp(name, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

def _ensure_base(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in BASE:
        if c not in out.columns:
            if c == "Α/Α":
                out[c] = range(1, len(out)+1)
            else:
                out[c] = "" if c != "ΦΙΛΟΙ" else ""
    return out

def _idx(s: str) -> int:
    m = re.search(r"ΣΕΝΑΡΙΟ[_\s]*(\d+)", str(s))
    return int(m.group(1)) if m else 1

# ========= Step 5 (preserve L, write M) — optional dependency =========

def export_single_noaudit(in14_path: str, out_path: str):
    in14 = Path(in14_path)
    if not in14.exists():
        raise FileNotFoundError(f"Δεν βρέθηκε το αρχείο: {in14}")

    xls = pd.ExcelFile(in14)
    sheets = [s for s in xls.sheet_names if s != "Σύνοψη"]

    with pd.ExcelWriter(out_path, engine="xlsxwriter") as w:
        for s in sheets:
            df = pd.read_excel(in14, sheet_name=s)
            df = _ensure_base(df)
            N = _idx(s)
            s1, s2, s3 = f"ΒΗΜΑ1_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{N}"
            s4, s5, s6c = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_{N}", f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{N}"

            # Ensure I..K
            for c in (s1, s2, s3):
                if c not in df.columns:
                    df[c] = np.nan

            # Ensure L from source (exact)
            if s4 not in df.columns:
                c4 = [c for c in df.columns if str(c).startswith("ΒΗΜΑ4_")]
                if c4:
                    df = df.rename(columns={c4[0]: s4})
                else:
                    df[s4] = np.nan

            # Step 5: preserve L, write M
            df5 = df.copy()
            if s5 not in df5.columns:
                c5 = [c for c in df5.columns if str(c).startswith("ΒΗΜΑ5_")]
                if c5:
                    df5 = df5.rename(columns={c5[0]: s5})
                else:
                    df5[s5] = df5[s4]

            # Prepare Step 6 inputs
            if "ΤΜΗΜΑ_ΒΗΜΑ1" not in df5.columns: df5["ΤΜΗΜΑ_ΒΗΜΑ1"] = df5[s1]
            if "ΤΜΗΜΑ_ΒΗΜΑ2" not in df5.columns: df5["ΤΜΗΜΑ_ΒΗΜΑ2"] = df5[s2]
            if "GROUP_ID" not in df5.columns: df5["GROUP_ID"] = np.nan
            if "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ" not in df5.columns:
                df5["ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ"] = [4 if str(l).strip() != "" else (5 if str(m).strip() != "" else np.nan) for l, m in zip(df5[s4], df5[s5])]

            # Run embedded Step 6
            # ΔΙΟΡΘΩΣΗ: υπολογισμός conflict_pairs μία φορά ανά sheet και ρητό
            # πέρασμα, ώστε να μην βασιζόμαστε σιωπηλά στο εσωτερικό default
            # της apply_step6 (η οποία πλέον το υπολογίζει μόνη της αν λείπει,
            # αλλά προτιμούμε ρητή ροή δεδομένων εδώ).
            conflict_pairs = _conflict_pairs_for_df(df5)
            out6 = apply_step6(
                df5.copy(),
                class_col=s5, id_col="Α/Α",
                gender_col="ΦΥΛΟ", lang_col="ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ",
                step_col="ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ", group_col="GROUP_ID",
                max_iter=MAX_ITER, conflict_pairs=conflict_pairs
            )
            df6 = out6["df"].copy()

            # Ensure N column and order strictly A–H + I..N (no audit after)
            if s6c not in df6.columns:
                src = "ΒΗΜΑ6_ΤΜΗΜΑ" if "ΒΗΜΑ6_ΤΜΗΜΑ" in df6.columns else ("ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" if "ΤΜΗΜΑ_ΜΕΤΑ_ΒΗΜΑ6" in df6.columns else s5)
                cols = list(df6.columns); ins = (cols.index(s5)+1) if s5 in cols else len(cols)
                df6.insert(ins, s6c, df6[src].values)

            ordered = BASE + [s1, s2, s3, s4, s5, s6c]
            for c in ordered:
                if c not in df6.columns:
                    df6[c] = np.nan
            out = df6[ordered].copy()

            out.to_excel(w, sheet_name=f"ΣΕΝΑΡΙΟ_{N}", index=False)
            ws = w.sheets[f"ΣΕΝΑΡΙΟ_{N}"]
            for i in range(len(out.columns)):
                ws.set_column(i, i, 22)

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Χρήση: python export_I_to_N_SINGLE_NO_AUDIT.py <STEP1_4.xlsx> <OUT.xlsx>")
        print("Προερ.: αν υπάρχει 'step5_enhanced.py' δίπλα, θα υπολογιστεί Μ. Αλλιώς Μ=L.")
        sys.exit(1)
    export_single_noaudit(sys.argv[1], sys.argv[2])
