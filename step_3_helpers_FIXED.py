
# -*- coding: utf-8 -*-
"""
step_3_helpers_FIXED.py
- ΦΙΛΟΙ parsing από string ή list
- Έλεγχος ΑΜΟΙΒΑΙΑΣ φιλίας (μόνο ΔΥΑΔΕΣ)
- Μέτρηση «σπασμένων» φιλικών ΔΥΑΔΩΝ (χωρίς διπλομέτρηση)
- Penalty score για Βήμα 3
- Επιλογή σεναρίων βάσει θεωρίας
"""

from typing import List, Tuple, Dict, Set
import pandas as pd
import re, ast

# Προαιρετικό κοινό Βήμα 0 για δηλωμένες/εξωτερικές συγκρούσεις.
# Αν δεν φορτωθεί, μένουμε στο παλιό raw fallback, αλλά με προειδοποίηση στα logs.
try:
    from conflict_guard import extract_conflict_data, can_place_student
except Exception as _cg_err:
    print(f"⚠️ conflict_guard δεν φορτώθηκε στο Step 3 helper: {_cg_err}")
    print("⚠️ Το Step 3 helper θα χρησιμοποιήσει fallback χωρίς fuzzy matching / χωρίς αφαίρεση τόνων.")
    extract_conflict_data = None
    can_place_student = None

SAFE_SEP = re.compile(r"[,\|\;/·\n]+")

def parse_friends_string(x) -> List[str]:
    if isinstance(x, list):
        return [str(s).strip() for s in x if str(s).strip()]
    if pd.isna(x):
        return []
    s = str(x).strip()
    if not s:
        return []
    # Προσπάθεια ως Python list: "['Α','Β']"
    try:
        val = ast.literal_eval(s)
        if isinstance(val, list):
            return [str(t).strip() for t in val if str(t).strip()]
    except Exception:
        pass
    # Διαφορετικά, split με ασφαλές regex
    parts = SAFE_SEP.split(s)
    return [p.strip() for p in parts if p.strip() and p.strip().lower()!="nan"]

def are_mutual_pair(df: pd.DataFrame, a: str, b: str) -> bool:
    ra = df[df["ΟΝΟΜΑ"].astype(str)==str(a)]
    rb = df[df["ΟΝΟΜΑ"].astype(str)==str(b)]
    if ra.empty or rb.empty:
        return False
    fa = set(parse_friends_string(ra.iloc[0].get("ΦΙΛΟΙ","")))
    fb = set(parse_friends_string(rb.iloc[0].get("ΦΙΛΟΙ","")))
    return (str(b).strip() in fa) and (str(a).strip() in fb)

def mutual_dyads(df: pd.DataFrame) -> Set[Tuple[str,str]]:
    names = df["ΟΝΟΜΑ"].astype(str).str.strip().tolist()
    pairs: Set[Tuple[str,str]] = set()
    for i, a in enumerate(names):
        for b in names[i+1:]:
            if are_mutual_pair(df, a, b):
                pairs.add(tuple(sorted([a,b])))
    return pairs

def count_broken_dyads(before_df: pd.DataFrame, after_df: pd.DataFrame, scenario_col: str) -> int:
    """Μετρά πόσες αμοιβαίες ΔΥΑΔΕΣ σπάνε στο after_df (δηλ. κατανέμονται σε διαφορετικές τάξεις)."""
    pairs = mutual_dyads(before_df)
    name2class = {str(r["ΟΝΟΜΑ"]).strip(): str(r.get(scenario_col)) for _, r in after_df.iterrows() if pd.notna(r.get(scenario_col))}
    broken=0
    for a,b in pairs:
        ca = name2class.get(a); cb = name2class.get(b)
        if ca is None or cb is None:
            # αν κάποιος δεν έχει τοποθετηθεί, θεωρούμε ότι η δυάδα δεν διατηρήθηκε
            broken += 1
        elif ca != cb:
            broken += 1
    return broken

def calculate_penalty_score_step3(df: pd.DataFrame, scenario_col: str, num_classes: int) -> int:
    """+1 για κάθε μονάδα διαφοράς >2 σε αγόρια, κορίτσια, πληθυσμό."""
    penalty = 0
    boys_counts=[]; girls_counts=[]; pop_counts=[]
    for i in range(num_classes):
        cl = f"Α{i+1}"
        sub = df[df[scenario_col]==cl]
        boys_counts.append(int((sub["ΦΥΛΟ"].astype(str).str.upper()=="Α").sum()))
        girls_counts.append(int((sub["ΦΥΛΟ"].astype(str).str.upper()=="Κ").sum()))
        pop_counts.append(len(sub))
    if boys_counts:
        penalty += max(0, max(boys_counts)-min(boys_counts)-2)
    if girls_counts:
        penalty += max(0, max(girls_counts)-min(girls_counts)-2)
    if pop_counts:
        penalty += max(0, max(pop_counts)-min(pop_counts)-2)
    return int(penalty)

def parse_conflicts_string(x) -> List[str]:
    """Parsing ΣΥΓΚΡΟΥΣΗ — ίδια μορφή με ΦΙΛΟΙ."""
    return parse_friends_string(x)


def has_declared_conflict_in_class(
    df: pd.DataFrame,
    student_name: str,
    class_name: str,
    scenario_col: str,
    conflict_pairs=None,
) -> bool:
    """
    True αν η τοποθέτηση του student_name στο class_name θα δημιουργήσει
    δηλωμένη/εξωτερική σύγκρουση με μαθητή που βρίσκεται ήδη στο class_name.

    Προτεραιότητα: κοινό conflict_guard.py, ώστε Step 3, app.py και exporter
    να χρησιμοποιούν ίδια κανονικοποίηση ονομάτων/fuzzy matching.
    Fallback: παλιός raw έλεγχος δύο κατευθύνσεων.
    """
    # Κοινός guard — πλήρες conflict_pairs για όλο τον πληθυσμό.
    if extract_conflict_data is not None and can_place_student is not None:
        try:
            pairs = conflict_pairs
            if pairs is None:
                pairs = extract_conflict_data(df).pairs
            return not bool(can_place_student(df, student_name, class_name, scenario_col, pairs))
        except Exception as e:
            print(f"⚠️ Step 3 conflict_guard check απέτυχε — χρήση fallback: {e}")

    # Fallback: raw exact matching, δύο κατευθύνσεις.
    name = str(student_name).strip()

    if "ΣΥΓΚΡΟΥΣΗ" not in df.columns:
        return False

    in_class = df[df[scenario_col] == class_name]["ΟΝΟΜΑ"].astype(str).str.strip().tolist()
    if not in_class:
        return False

    row_u = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == name]
    conflicts_of_u: Set[str] = set()
    if not row_u.empty:
        conflicts_of_u = set(parse_conflicts_string(row_u.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", "")))

    for member in in_class:
        if member in conflicts_of_u:
            return True
        row_m = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == member]
        if not row_m.empty:
            conflicts_of_m = set(parse_conflicts_string(row_m.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", "")))
            if name in conflicts_of_m:
                return True

    return False


def select_best_scenarios(results: List[Tuple[str, pd.DataFrame, Dict]]) -> List[Tuple[str,pd.DataFrame,Dict]]:
    """
    results: [(sheet_name, df_after, meta), ...], όπου meta περιέχει:
       {"broken": int, "penalty": int}
    Κανόνες:
      - Αν υπάρχουν σενάρια με broken==0 → επέλεξε όσα έχουν το μικρότερο penalty (έως 5)
      - Αλλιώς → επέλεξε όσα έχουν το μικρότερο broken, και tie-break με penalty (έως 5)
    """
    if not results:
        return []
    zero = [t for t in results if t[2].get("broken", 0)==0]
    if zero:
        zero.sort(key=lambda x: x[2].get("penalty", 0))
        return zero[:5]
    # αλλιώς
    results.sort(key=lambda x: (x[2].get("broken", 1_000_000), x[2].get("penalty", 1_000_000)))
    return results[:5]
