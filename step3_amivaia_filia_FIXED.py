# -*- coding: utf-8 -*-
"""
step3_amivaia_filia_FIXED.py
- Επεξεργάζεται ΟΛΑ τα sheets "ΒΗΜΑ2_ΣΕΝΑΡΙΟ_*" από workbook Βήμα 2
- Φτιάχνει ανά sheet μια νέα στήλη "ΒΗΜΑ3_ΣΕΝΑΡΙΟ_k" με τοποθέτηση ΜΟΝΟ ΔΥΑΔΩΝ
  όπου ο 1 είναι ήδη τοποθετημένος (στο Βήμα 2) και ο 2 είναι ατοποθέτητος.
- Δεν «σπάει» καμία δυάδα: αν δεν χωράει λόγω ορίου 25, η δυάδα μετρά ως broken και ο ατοποθέτητος παραμένει κενός.
- Υπολογίζει broken δυάδες & penalty, επιλέγει έως 5 καλύτερα σενάρια.
"""
from typing import List, Tuple, Dict, Optional
import pandas as pd
import re
from pathlib import Path
from step_3_helpers_FIXED import (
    parse_friends_string, are_mutual_pair, mutual_dyads,
    count_broken_dyads, calculate_penalty_score_step3, select_best_scenarios,
    has_declared_conflict_in_class,
    extract_conflict_data,
)

def _auto_num_classes(df, override=None):
    import math
    n = len(df)
    # Keep a safe minimum of 2 to match downstream assumptions
    k = max(2, math.ceil(n/25))
    return int(k if override is None else override)

def _class_fits(df: pd.DataFrame, col: str, class_name: str, add: int=1) -> bool:
    return (df[col]==class_name).sum() + add <= 25

def apply_step3_on_sheet(
    df2: pd.DataFrame,
    scenario_col: str,
    num_classes: Optional[int] = None) -> Tuple[pd.DataFrame, Dict]:
    """
    Παίρνει ένα DataFrame από Βήμα 2 (ένα sheet) και επιστρέφει:
    - df_after: με νέα στήλη ΒΗΜΑ3_ΣΕΝΑΡΙΟ_k (ίδιο όνομα με το sheet αλλά με 'ΒΗΜΑ3')
    - meta: {"broken": int, "penalty": int}
    Κανόνας: τοποθετούμε ΜΟΝΟ δυάδες (u,v) όπου u είναι unplaced, v είναι placed, και είναι αμοιβαία φίλοι.
    """
    df = df2.copy()
    # νέα στήλη
    new_col = re.sub(r"^ΒΗΜΑ2", "ΒΗΜΑ3", scenario_col)
    df[new_col] = df[scenario_col]

    # Δηλωμένες/εξωτερικές συγκρούσεις: υπολογίζονται μία φορά για το Step 3.
    # Εδώ χρησιμοποιείται όλος ο πληθυσμός του df, όχι μόνο οι μαθητές που θα τοποθετηθούν στο Step 3.
    conflict_pairs = None
    unresolved_conflicts = 0
    if extract_conflict_data is not None:
        try:
            conflict_data = extract_conflict_data(df)
            conflict_pairs = conflict_data.pairs
            unresolved_conflicts = len(getattr(conflict_data, "unresolved", []) or [])
        except Exception as e:
            print(f"⚠️ Step 3: αποτυχία extract_conflict_data — χρήση fallback: {e}")

    placed = df[df[scenario_col].notna()][["ΟΝΟΜΑ", scenario_col]].set_index("ΟΝΟΜΑ")[scenario_col].to_dict()
    # unplaced υποψήφιοι (γενικά όλοι οι κενές αναθέσεις)
    unplaced_names = df[df[new_col].isna()]["ΟΝΟΜΑ"].astype(str).tolist()

    # δώσε προτεραιότητα σε όσους έχουν ΑΚΡΙΒΩΣ 1 αμοιβαίο φίλο (μονοσήμαντες δυάδες)
    def mutual_friends_of(u: str) -> list:
        cell = df.loc[df["ΟΝΟΜΑ"]==u, "ΦΙΛΟΙ"]
        friends = parse_friends_string(cell.values[0] if not cell.empty else "")
        return [v for v in friends if are_mutual_pair(df, u, v)]
    # κατασκεύασε λίστα (u, v, class_v) για v ήδη placed
    candidates = []
    for u in unplaced_names:
        for v in mutual_friends_of(u):
            if v in placed:
                candidates.append((u, v, placed[v]))

    # Ταξινόμηση: λιγότερες επιλογές πρώτα → μειώνει αδιέξοδα
    degree = {u: len([1 for x in candidates if x[0]==u]) for u in unplaced_names}
    candidates.sort(key=lambda t: (degree.get(t[0], 99), t[2]))

    used_u = set()
    for u, v, cl in candidates:
        if u in used_u:
            continue
        if not _class_fits(df, new_col, cl, add=1):
            continue
        if has_declared_conflict_in_class(df, u, cl, new_col, conflict_pairs=conflict_pairs):
            continue  # hard constraint: δηλωμένη/εξωτερική σύγκρουση → απόρριψη
        df.loc[df["ΟΝΟΜΑ"] == u, new_col] = cl
        used_u.add(u)
        placed[u] = cl

    # Μετρικά
    broken = count_broken_dyads(df2, df, new_col)
    num_classes = _auto_num_classes(df, num_classes)
    penalty = calculate_penalty_score_step3(df, new_col, num_classes)
    meta = {"broken": int(broken), "penalty": int(penalty), "declared_conflict_pairs": int(len(conflict_pairs) if conflict_pairs is not None else 0), "unresolved_conflicts": int(unresolved_conflicts)}
    return df, meta

def apply_step3_to_dataframe(df_step2: pd.DataFrame, num_classes: Optional[int] = None) -> pd.DataFrame:
    """
    ΝΕΑ ΣΥΝΑΡΤΗΣΗ: Εφαρμόζει το Βήμα 3 σε DataFrame (για Streamlit)
    
    Args:
        df_step2: DataFrame από το Βήμα 2 με στήλες ΒΗΜΑ2_ΣΕΝΑΡΙΟ_*
        num_classes: Αριθμός τμημάτων
    
    Returns:
        DataFrame με επιπλέον στήλες ΒΗΜΑ3_ΣΕΝΑΡΙΟ_*
    """
    df_result = df_step2.copy()
    
    # Εύρεση στηλών ΒΗΜΑ2_ΣΕΝΑΡΙΟ_*
    step2_columns = [col for col in df_step2.columns if col.startswith('ΒΗΜΑ2_ΣΕΝΑΡΙΟ_')]
    
    if not step2_columns:
        raise ValueError("Δεν βρέθηκαν στήλες ΒΗΜΑ2_ΣΕΝΑΡΙΟ_* στο DataFrame")
    
    results = []
    
    # Εφαρμογή Βήματος 3 σε κάθε στήλη ΒΗΜΑ2
    for scenario_col in step2_columns:
        df_after, meta = apply_step3_on_sheet(df_step2, scenario_col, num_classes)
        
        # Εξαγωγή της νέας στήλης ΒΗΜΑ3
        new_col = re.sub(r"^ΒΗΜΑ2", "ΒΗΜΑ3", scenario_col)
        if new_col in df_after.columns:
            df_result[new_col] = df_after[new_col]
        
        results.append((scenario_col, df_after, meta))
    
    # Επιλογή καλύτερων σεναρίων (προαιρετικό - κρατάμε όλα για το Streamlit)
    selected = select_best_scenarios(results)
    
    print(f"Βήμα 3: Επεξεργάστηκαν {len(step2_columns)} σενάρια, επιλέχθηκαν {len(selected)}")
    for name, _, meta in selected:
        print(f"  {name}: Broken={meta['broken']}, Penalty={meta['penalty']}")
    
    return df_result

def step3_run_all_from_step2(step2_xlsx_path: str, output_xlsx_path: str) -> str:
    """
    Διαβάζει το workbook του Βήμα 2 και παράγει νέο workbook για το Βήμα 3
    με ένα sheet ανά σενάριο. Επιστρέφει το path του αρχείου.
    """
    p = Path(step2_xlsx_path)
    assert p.exists(), f"Δεν βρέθηκε: {p}"
    xls = pd.ExcelFile(p)
    s2_sheets = [s for s in xls.sheet_names if s.startswith("ΒΗΜΑ2_ΣΕΝΑΡΙΟ_")]
    if not s2_sheets:
        raise ValueError("Δεν βρέθηκαν sheets 'ΒΗΜΑ2_ΣΕΝΑΡΙΟ_*' στο αρχείο Βήμα 2.")

    # ΔΙΟΡΘΩΣΗ: Φόρτωση οποιουδήποτε sheet για να πάρουμε το μέγεθος
    df0 = pd.read_excel(p, sheet_name=s2_sheets[0])
    N = len(df0)
    num_classes = _auto_num_classes(df0, None)

    results = []
    for s in s2_sheets:
        df2 = pd.read_excel(p, sheet_name=s)
        df3, meta = apply_step3_on_sheet(df2, scenario_col=s, num_classes=num_classes)
        results.append((re.sub(r"^ΒΗΜΑ2", "ΒΗΜΑ3", s), df3, meta))

    # Επιλογή έως 5 καλύτερων
    selected = select_best_scenarios(results)

    # Γράψε αρχείο
    out = Path(output_xlsx_path)
    with pd.ExcelWriter(out, engine="openpyxl") as w:
        for name, df3, meta in selected:
            df3.to_excel(w, index=False, sheet_name=name[:31])
        # και ένα sheet "Σύνοψη"
        rows = [{"Sheet": name, "Broken_dyads": meta["broken"], "Penalty": meta["penalty"]}
                for name, _, meta in selected]
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name="Σύνοψη")

    return out.as_posix()

# === EXTRA: FULL exporter that works with "ΣΕΝΑΡΙΟ_*" sheets from Step 2 FULL ===
def export_step3_nextcol_full(step2_xlsx_path: str, out_xlsx_path: str) -> str:
    """
    Διαβάζει workbook του Βήματος 2 (FULL: φύλλα τύπου 'ΣΕΝΑΡΙΟ_k' που περιέχουν στήλες ΒΗΜΑ2_ΣΕΝΑΡΙΟ_k)
    και παράγει νέο workbook για το Βήμα 3 κρατώντας ΟΛΕΣ τις αρχικές στήλες.
    - Προσθέτει τη στήλη 'ΒΗΜΑ3_ΣΕΝΑΡΙΟ_k' ακριβώς δεξιά από τη 'ΒΗΜΑ2_ΣΕΝΑΡΙΟ_k' για κάθε σενάριο.
    - Ονόματα φύλλων εξόδου: 'ΒΗΜΑ3_ΣΕΝΑΡΙΟ_k'.
    """
    import pandas as pd, re
    from pathlib import Path

    p = Path(step2_xlsx_path)
    assert p.exists(), f"Δεν βρέθηκε: {p}"
    xls = pd.ExcelFile(p)

    outputs = []
    for sh in xls.sheet_names:
        # Δουλεύουμε με κάθε "ΣΕΝΑΡΙΟ_k" sheet
        df2 = pd.read_excel(p, sheet_name=sh)
        # βρες τη στήλη ΒΗΜΑ2_ΣΕΝΑΡΙΟ_k
        s2_cols = [c for c in df2.columns if str(c).strip().upper().startswith("ΒΗΜΑ2_ΣΕΝΑΡΙΟ_")]
        if not s2_cols:
            # αν δεν υπάρχει, συνέχισε στο επόμενο sheet
            continue
        scenario_col = s2_cols[0]
        # Εφάρμοσε ΒΗΜΑ 3
        df3, meta = apply_step3_on_sheet(df2, scenario_col=scenario_col, num_classes=None)
        # Βάλε τη νέα στήλη δίπλα στη ΒΗΜΑ2
        new_col = re.sub(r"^ΒΗΜΑ2", "ΒΗΜΑ3", scenario_col)
        cols = df3.columns.tolist()
        # μετακίνησε new_col δίπλα στη scenario_col
        if new_col in cols:
            cols.remove(new_col)
        idx = cols.index(scenario_col) + 1 if scenario_col in cols else len(cols)
        cols = cols[:idx] + [new_col] + cols[idx:]
        df3 = df3[cols]
        # sheet name εξόδου
        sid = re.search(r"ΣΕΝΑΡΙΟ[_\s]*(\d+)", scenario_col)
        sid = sid.group(1) if sid else "1"
        out_sheet = f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}"
        outputs.append((out_sheet, df3, meta))

    if not outputs:
        raise ValueError("Δεν βρέθηκαν στήλες ΒΗΜΑ2_ΣΕΝΑΡΙΟ_* στο αρχείο Βήμα 2.")

    out = Path(out_xlsx_path)
    with pd.ExcelWriter(out, engine="xlsxwriter") as w:
        for name, df3, meta in outputs:
            df3.to_excel(w, index=False, sheet_name=name[:31])
        # Σύνοψη
        import pandas as pd
        rows = [{"Sheet": name, "Broken_dyads": meta["broken"], "Penalty": meta["penalty"]}
                for name, _, meta in outputs]
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name="Σύνοψη")
    return out.as_posix()
