# -*- coding: utf-8 -*-
"""
step_5_ypoloipoi_mathites_CORRECTED_ENHANCED.py

ΔΙΟΡΘΩΣΕΙΣ & ΒΕΛΤΙΩΣΕΙΣ:
1. Penalty weights σύμφωνα με τις οδηγίες (+1 για όλα εκτός από σπασμένη φιλία +5)
2. Ισορροπία φύλου υπολογίζεται σε όλα τα τμήματα (όχι μόνο στους candidates)
3. Αφαιρέθηκε το RANDOM_SEED για καλύτερη τυχαιότητα στην ισοβαθμία
4. Βελτιώθηκε η λογική επιλογής τμήματος
5. ΠΡΟΣΘΗΚΗ: Προτίμηση υποψηφίων που κρατούν διαφορά πληθυσμού ≤2
6. ΠΡΟΣΘΗΚΗ: Δυναμικός υπολογισμός σπασμένων φιλιών αν λείπει η στήλη
7. ΠΡΟΣΘΗΚΗ: Εμπλουτισμένη επιστροφή με penalty score και όνομα νικητή
"""

from __future__ import annotations
import random, re
from typing import List, Dict, Tuple, Any, Optional
import pandas as pd

# ---------------------------------------------------------------------------
# Προαιρετικός κοινός guard δηλωμένων/εξωτερικών συγκρούσεων
# ---------------------------------------------------------------------------
try:
    from conflict_guard import (
        extract_conflict_pairs as _cg_extract_conflict_pairs,
        can_place_student as _cg_can_place_student,
        norm_name as _cg_norm_name,
    )
except Exception as _cg_import_error:
    print(f"⚠️ conflict_guard δεν βρέθηκε ή δεν φορτώθηκε σωστά στο Step 5: {_cg_import_error}")
    print("⚠️ Το Step 5 θα χρησιμοποιήσει fallback raw έλεγχο χωρίς fuzzy/canon matching.")
    _cg_extract_conflict_pairs = None
    _cg_can_place_student = None
    def _cg_norm_name(x):
        return re.sub(r"\s+", " ", str(x).strip())

def _conflict_pairs_for_df(df: pd.DataFrame):
    """Εξάγει μία φορά τα conflict_pairs με το κοινό conflict_guard, όταν είναι διαθέσιμο."""
    if _cg_extract_conflict_pairs is None:
        return None
    try:
        return _cg_extract_conflict_pairs(df)
    except Exception as e:
        print(f"⚠️ Step 5: αποτυχία extract_conflict_pairs, fallback raw έλεγχος: {e}")
        return None

# ---------------------------------------------------------------------------
# Conflict helper — hard constraint ΣΥΓΚΡΟΥΣΗ
# ---------------------------------------------------------------------------

MAX_RUNS = 100  # default: 100 runs — ρυθμίζεται από το Streamlit (100/300/500)

def _parse_conflicts_list(x: Any) -> List[str]:
    """Parsing ΣΥΓΚΡΟΥΣΗ — ίδια μορφή με ΦΙΛΟΙ."""
    return _parse_list_cell(x)  # forward ref OK (ορίζεται παρακάτω)

def _auto_num_classes(df: pd.DataFrame, override: Optional[int] = None) -> int:
    """Αυτόματος υπολογισμός αριθμού τμημάτων (25 μαθητές/τμήμα, min=2)."""
    import math
    n = len(df)
    k = max(2, math.ceil(n/25))
    return int(k if override is None else override)

# Tokens για boolean parsing
YES_TOKENS = {"Ν", "ΝΑΙ", "YES", "Y", "TRUE", "1"}
NO_TOKENS  = {"Ο", "ΟΧΙ", "NO", "N", "FALSE", "0"}

def _norm_str(x: Any) -> str:
    """Κανονικοποίηση string."""
    return str(x).strip().upper()

def _is_yes(x: Any) -> bool:
    """Έλεγχος αν η τιμή είναι 'ναι'."""
    return _norm_str(x) in YES_TOKENS

def _is_no(x: Any) -> bool:
    """Έλεγχος αν η τιμή είναι 'όχι'."""
    return _norm_str(x) in NO_TOKENS

def _parse_list_cell(x: Any) -> List[str]:
    """Parsing λίστας από διάφορα formats (string, list, κ.ά.)."""
    if isinstance(x, list):
        return [str(t).strip() for t in x if str(t).strip()]
    
    s = "" if pd.isna(x) else str(x)
    s = s.strip()
    if not s or s.upper() == "NAN":
        return []
    
    # Δοκιμή python list parsing
    try:
        v = eval(s, {}, {})
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()] 
    except Exception:
        pass
    
    # Split με διάφορους διαχωριστές
    parts = re.split(r"[,\|\;/·\n]+", s)
    return [p.strip() for p in parts if p.strip()]


def _has_conflict_in_class(
    df: pd.DataFrame,
    student_name: str,
    class_name: str,
    scenario_col: str,
    conflict_pairs=None,
) -> bool:
    """
    Επιστρέφει True αν ο student_name έχει δηλωμένη/εξωτερική σύγκρουση
    με οποιονδήποτε ήδη τοποθετημένο μαθητή του class_name.

    Όταν υπάρχει conflict_guard.py, χρησιμοποιεί το κοινό can_place_student(),
    άρα έχει ίδια κανονικοποίηση/fuzzy matching με τα υπόλοιπα βήματα.
    Αν δεν φορτωθεί, πέφτει σε raw αμφίδρομο fallback.
    """
    name = str(student_name).strip()
    if not name or not str(class_name).strip():
        return False

    if _cg_can_place_student is not None:
        try:
            pairs = conflict_pairs if conflict_pairs is not None else _conflict_pairs_for_df(df)
            return not _cg_can_place_student(df, name, class_name, scenario_col, pairs)
        except Exception as e:
            print(f"⚠️ Step 5: conflict_guard.can_place_student απέτυχε, fallback raw έλεγχος: {e}")

    # Fallback raw exact/bidirectional check
    if "ΣΥΓΚΡΟΥΣΗ" not in df.columns:
        return False

    in_class = df[df[scenario_col] == class_name]["ΟΝΟΜΑ"].astype(str).str.strip().tolist()
    if not in_class:
        return False

    row_u = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == name]
    conflicts_u: set = set()
    if not row_u.empty:
        conflicts_u = {_cg_norm_name(x) for x in _parse_conflicts_list(row_u.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", ""))}

    name_c = _cg_norm_name(name)
    for member in in_class:
        member_c = _cg_norm_name(member)
        if member_c in conflicts_u:
            return True
        row_m = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == member]
        if not row_m.empty:
            c_m = {_cg_norm_name(x) for x in _parse_conflicts_list(row_m.iloc[0].get("ΣΥΓΚΡΟΥΣΗ", ""))}
            if name_c in c_m:
                return True
    return False

def _is_good_greek(row: pd.Series) -> bool:
    """Έλεγχος καλής γνώσης ελληνικών (backward/forward compatible)."""
    if "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ" in row:
        return _is_yes(row.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ"))
    if "ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ" in row:
        return _norm_str(row.get("ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ")) in {"ΚΑΛΗ", "GOOD", "Ν"}
    return False

def _get_class_labels(df: pd.DataFrame, scenario_col: str) -> List[str]:
    """Επιστρέφει τα labels των τμημάτων (Α1, Α2, ...)."""
    labs = sorted([str(v) for v in df[scenario_col].dropna().unique() 
                   if re.match(r"^Α\d+$", str(v))])
    return labs or [f"Α{i+1}" for i in range(2)]

def _count_broken_pairs(df: pd.DataFrame, scenario_col: str) -> int:
    """Δυναμικός υπολογισμός σπασμένων πλήρως αμοιβαίων φιλιών."""
    by_class = dict(zip(df["ΟΝΟΜΑ"].astype(str).str.strip(), df[scenario_col].astype(str)))
    broken = set()
    
    for _, r in df.iterrows():
        if not _is_yes(r.get("ΠΛΗΡΩΣ_ΑΜΟΙΒΑΙΑ", False)):
            continue
            
        me = str(r["ΟΝΟΜΑ"]).strip()
        c_me = by_class.get(me)
        
        for fr in _parse_list_cell(r.get("ΦΙΛΟΙ", [])):
            if me < fr:  # Αποφυγή διπλής καταμέτρησης
                friend_row = df[df["ΟΝΟΜΑ"].astype(str).str.strip() == fr]
                if not friend_row.empty and _is_yes(friend_row.iloc[0].get("ΠΛΗΡΩΣ_ΑΜΟΙΒΑΙΑ", False)):
                    c_fr = by_class.get(fr)
                    if pd.notna(c_me) and pd.notna(c_fr) and c_me != c_fr:
                        broken.add((me, fr))
    
    return len(broken)

def calculate_penalty_score(df: pd.DataFrame, scenario_col: str, 
                          num_classes: Optional[int] = None) -> int:
    """
    Υπολογισμός penalty score σύμφωνα με τις οδηγίες:
    - Γνώση Ελληνικών: +1 για κάθε διαφορά > 2
    - Πληθυσμός: +1 για κάθε διαφορά > 1  
    - Φύλο: +1 για κάθε διαφορά > 1 (αγόρια ή κορίτσια)
    - Σπασμένη Φιλία: +5 για κάθε σπασμένη πλήρως αμοιβαία φιλία
    """
    labs = _get_class_labels(df, scenario_col)
    if num_classes is None:
        num_classes = _auto_num_classes(df, None)

    penalty = 0

    # 1. Ισορροπία Γνώσης Ελληνικών
    greek_counts = []
    for lab in labs:
        sub = df[df[scenario_col] == lab].copy()
        greek_counts.append(int(sub.apply(_is_good_greek, axis=1).sum()))
    
    if greek_counts:
        greek_diff = max(greek_counts) - min(greek_counts)
        penalty += max(0, greek_diff - 2)  # +1 για κάθε διαφορά > 2

    # 2. Ισορροπία Πληθυσμού  
    class_sizes = [int((df[scenario_col] == lab).sum()) for lab in labs]
    if class_sizes:
        pop_diff = max(class_sizes) - min(class_sizes)
        penalty += max(0, pop_diff - 1)  # +1 για κάθε διαφορά > 1

    # 3. Ισορροπία Φύλου
    boys_counts = [int(((df[scenario_col] == lab) & 
                       (df["ΦΥΛΟ"].astype(str).str.upper() == "Α")).sum()) 
                   for lab in labs]
    girls_counts = [int(((df[scenario_col] == lab) & 
                        (df["ΦΥΛΟ"].astype(str).str.upper() == "Κ")).sum()) 
                    for lab in labs]
    
    if boys_counts:
        boys_diff = max(boys_counts) - min(boys_counts)
        penalty += max(0, boys_diff - 1)  # +1 για κάθε διαφορά > 1
    
    if girls_counts:
        girls_diff = max(girls_counts) - min(girls_counts)
        penalty += max(0, girls_diff - 1)  # +1 για κάθε διαφορά > 1

    # 4. Σπασμένες Πλήρως Αμοιβαίες Φιλίες
    if "ΣΠΑΣΜΕΝΗ_ΦΙΛΙΑ" in df.columns:
        broken_friendships = int(df["ΣΠΑΣΜΕΝΗ_ΦΙΛΙΑ"].apply(_is_yes).sum())
    else:
        broken_friendships = _count_broken_pairs(df, scenario_col)
    
    penalty += 5 * broken_friendships  # +5 για κάθε σπασμένη φιλία

    return penalty

def step5_place_remaining_students(
    df: pd.DataFrame,
    scenario_col: str,
    num_classes: Optional[int] = None,
    seed: int = 42,
    max_results: int = 5,
    num_runs: int = MAX_RUNS,
    conflict_pairs: Optional[Any] = None,
) -> Tuple[pd.DataFrame, int]:
    """
    Βήμα 5: Τοποθέτηση υπολοίπων μαθητών χωρίς (πλήρως αμοιβαίες) φιλίες.

    Τρέχει max_results φορές με διαφορετική σειρά μαθητών (randomized),
    κρατά το σενάριο με το χαμηλότερο penalty score.

    Κριτήρια τοποθέτησης (με σειρά προτεραιότητας):
    1. Τμήμα με μικρότερο πληθυσμό (< 25 μαθητές)
    2. Σε ισοπαλία: προτίμηση όσων κρατούν διαφορά πληθυσμού ≤2
    3. Σε ισοπαλία: καλύτερη ισορροπία φύλου σε ΌΛΑ τα τμήματα

    Παράμετρος conflict_pairs (νέο):
        Αν δοθεί έτοιμο (π.χ. από κοινό Βήμα 0), χρησιμοποιείται ως έχει.
        Αλλιώς υπολογίζεται ΜΙΑ ΦΟΡΑ εδώ, πριν ξεκινήσουν τα runs — όχι
        ξανά σε κάθε ένα από τα num_runs runs.
    """
    rng = random.Random(seed)

    if conflict_pairs is None:
        conflict_pairs = _conflict_pairs_for_df(df)

    def _single_run(df_in: pd.DataFrame, order_seed: int) -> Tuple[pd.DataFrame, int]:
        df_run = df_in.copy()
        labs = _get_class_labels(df_run, scenario_col)
        nc = num_classes if num_classes is not None else _auto_num_classes(df_run, None)

        friends_list = (df_run["ΦΙΛΟΙ"].map(_parse_list_cell) if "ΦΙΛΟΙ" in df_run.columns
                        else pd.Series([[]] * len(df_run)))
        fully_mutual = (df_run["ΠΛΗΡΩΣ_ΑΜΟΙΒΑΙΑ"].apply(_is_yes) if "ΠΛΗΡΩΣ_ΑΜΟΙΒΑΙΑ" in df_run.columns
                        else pd.Series([False] * len(df_run)))
        broken_friendship = (df_run["ΣΠΑΣΜΕΝΗ_ΦΙΛΙΑ"].apply(_is_yes) if "ΣΠΑΣΜΕΝΗ_ΦΙΛΙΑ" in df_run.columns
                             else pd.Series([False] * len(df_run)))

        mask_step5 = (
            df_run[scenario_col].isna() &
            ((friends_list.map(len) == 0) |
             (~fully_mutual) |
             (broken_friendship))
        )

        remaining = df_run[mask_step5].copy()
        # Τυχαία σειρά για αυτό το run
        remaining = remaining.sample(frac=1, random_state=order_seed)

        for _, row in remaining.iterrows():
            name = str(row["ΟΝΟΜΑ"]).strip()
            gender = str(row["ΦΥΛΟ"]).strip().upper()

            class_sizes = {lab: int((df_run[scenario_col] == lab).sum()) for lab in labs}

            # Πρώτα αφαιρούμε όσα τμήματα είναι γεμάτα ή θα δημιουργούσαν δηλωμένη σύγκρουση.
            # Έτσι, αν το μικρότερο τμήμα έχει σύγκρουση, δοκιμάζεται το επόμενο καλύτερο
            # conflict-free τμήμα αντί να μείνει ο μαθητής ατοποθέτητος.
            available_classes = [
                lab for lab, size in class_sizes.items()
                if size < 25 and not _has_conflict_in_class(
                    df_run, name, lab, scenario_col, conflict_pairs
                )
            ]

            if not available_classes:
                continue

            scored_classes = []
            for candidate in available_classes:
                new_sizes = {
                    lab: int((df_run[scenario_col] == lab).sum()) + (1 if lab == candidate else 0)
                    for lab in labs
                }
                pop_diff = max(new_sizes.values()) - min(new_sizes.values())

                boys_counts = []
                girls_counts = []
                for lab in labs:
                    b = int(((df_run[scenario_col] == lab) &
                             (df_run["ΦΥΛΟ"].astype(str).str.upper() == "Α")).sum())
                    g = int(((df_run[scenario_col] == lab) &
                             (df_run["ΦΥΛΟ"].astype(str).str.upper() == "Κ")).sum())
                    if lab == candidate:
                        if gender == "Α": b += 1
                        elif gender == "Κ": g += 1
                    boys_counts.append(b)
                    girls_counts.append(g)

                total_gender_diff = (
                    max(boys_counts) - min(boys_counts) +
                    max(girls_counts) - min(girls_counts)
                )

                scored_classes.append((
                    class_sizes[candidate],          # 1. μικρότερος πληθυσμός
                    0 if pop_diff <= 2 else 1,      # 2. προτίμηση pop diff ≤2
                    pop_diff,                       # 3. μικρότερη πληθυσμιακή διαφορά
                    total_gender_diff,              # 4. καλύτερη ισορροπία φύλου
                    candidate,
                ))

            best_key = min(scored_classes, key=lambda x: x[:-1])[:-1]
            best_classes = [c for *score, c in scored_classes if tuple(score) == best_key]
            chosen_class = rng.choice(best_classes)
            df_run.loc[df_run["ΟΝΟΜΑ"] == name, scenario_col] = chosen_class

        return df_run, calculate_penalty_score(df_run, scenario_col, nc)

    # --- Multi-run: έως num_runs τυχαίες σειρές, κρατάμε max_results καλύτερα ---
    best_df, best_penalty = _single_run(df, seed)
    seen_penalties = {best_penalty}
    candidates: List[Tuple[int, pd.DataFrame]] = [(best_penalty, best_df)]

    for i in range(1, num_runs):
        run_df, run_penalty = _single_run(df, seed + i)
        entry = (run_penalty, run_df)
        candidates.append(entry)
        if run_penalty < best_penalty:
            best_penalty = run_penalty
            best_df = run_df

    # Ταξινόμηση — κρατάμε έως max_results μοναδικά (βάσει penalty)
    candidates.sort(key=lambda x: x[0])
    # deduplicate by penalty value (κρατάμε πρώτο ανά penalty)
    seen: set = set()
    unique_candidates: List[Tuple[int, pd.DataFrame]] = []
    for pen, cdf in candidates:
        if pen not in seen:
            seen.add(pen)
            unique_candidates.append((pen, cdf))
        if len(unique_candidates) >= max_results:
            break

    # Επιστροφή του καλύτερου (backward-compat: Tuple[df, penalty])
    best_penalty, best_df = unique_candidates[0]
    return best_df, best_penalty


def step5_generate_scenarios(
    df: pd.DataFrame,
    scenario_col: str,
    num_classes: Optional[int] = None,
    seed: int = 42,
    max_results: int = 5,
    num_runs: int = MAX_RUNS,
) -> List[Tuple[str, pd.DataFrame, int]]:
    """
    Νέα συνάρτηση: επιστρέφει έως max_results σενάρια ως List[(label, df, penalty)].
    Τρέχει num_runs φορές με τυχαία σειρά μαθητών.
    """
    rng = random.Random(seed)

    # ΔΙΟΡΘΩΣΗ: υπολογισμός μία φορά, πριν από όλα τα num_runs calls παρακάτω,
    # και πέρασμά του σε κάθε step5_place_remaining_students (που πλέον δέχεται
    # έτοιμο conflict_pairs αντί να το ξαναϋπολογίζει).
    conflict_pairs = _conflict_pairs_for_df(df)

    def _single_run(order_seed: int) -> Tuple[pd.DataFrame, int]:
        return step5_place_remaining_students(df, scenario_col, num_classes,
                                              seed=order_seed, max_results=1,
                                              num_runs=1, conflict_pairs=conflict_pairs)

    seen: set = set()
    results: List[Tuple[str, pd.DataFrame, int]] = []

    for i in range(num_runs):
        run_df, run_penalty = _single_run(seed + i)
        if run_penalty not in seen:
            seen.add(run_penalty)
            results.append((f"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_{len(results)+1}", run_df, run_penalty))
        if len(results) >= max_results:
            break

    results.sort(key=lambda x: x[2])
    return results

def apply_step5_to_all_scenarios(scenarios_dict: Dict[str, pd.DataFrame], 
                               scenario_col: str, num_classes: Optional[int] = None) -> Tuple[pd.DataFrame, int, str]:
    """
    Εφαρμογή Βήματος 5 σε όλα τα σενάρια και επιλογή του βέλτιστου.
    
    Returns:
        Tuple[pd.DataFrame, int, str]: Το σενάριο με το χαμηλότερο penalty score, 
                                      το penalty score και το όνομα του σεναρίου
    """
    if not scenarios_dict:
        raise ValueError("Δεν δόθηκαν σενάρια προς επεξεργασία")
    
    results = {}
    for scenario_name, scenario_df in scenarios_dict.items():
        try:
            updated_df, score = step5_place_remaining_students(
                scenario_df, scenario_col, num_classes)
            results[scenario_name] = {"df": updated_df, "penalty_score": score}
        except Exception as e:
            print(f"Σφάλμα στο σενάριο {scenario_name}: {e}")
            continue

    if not results:
        raise ValueError("Κανένα σενάριο δεν επεξεργάστηκε επιτυχώς")

    # Εύρεση βέλτιστου σεναρίου
    min_score = min(v["penalty_score"] for v in results.values())
    best_scenarios = [k for k, v in results.items() if v["penalty_score"] == min_score]
    
    # Τυχαία επιλογή σε ισοβαθμία
    chosen_scenario = random.choice(best_scenarios)
    
    print(f"Επιλέχθηκε σενάριο: {chosen_scenario} με penalty score: {min_score}")
    return results[chosen_scenario]["df"], results[chosen_scenario]["penalty_score"], chosen_scenario


# Compatibility aliases για backward compatibility
step5_filikoi_omades = step5_place_remaining_students

def export_step5_like_template(step34_xlsx_path: str, out_xlsx_path: str) -> str:
    """
    Διαβάζει workbook με φύλλα 'ΣΕΝΑΡΙΟ_k' (12-στήλες template) και
    προσθέτει 'ΒΗΜΑ5_ΣΕΝΑΡΙΟ_k' εφαρμόζοντας το Βήμα 5 πάνω στο 'ΒΗΜΑ4_ΣΕΝΑΡΙΟ_k'.
    """
    xls = pd.ExcelFile(step34_xlsx_path)
    with pd.ExcelWriter(out_xlsx_path, engine="xlsxwriter") as writer:
        for sh in xls.sheet_names:
            if not str(sh).startswith("ΣΕΝΑΡΙΟ_"):
                continue
            df = xls.parse(sh)
            m = re.search(r"(\d+)$", sh)
            sid = int(m.group(1)) if m else 1
            col4 = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"
            col5 = f"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_{sid}"
            if col4 not in df.columns:
                df.to_excel(writer, index=False, sheet_name=sh)
                continue
            # Δημιουργούμε ξεχωριστή στήλη Βήματος 5 ως ακριβές αντίγραφο
            # της ολοκληρωμένης στήλης του Βήματος 4. Οι νέες αναθέσεις του
            # Βήματος 5 γράφονται πλέον απευθείας στη col5, ώστε η col4 να
            # παραμένει αμετάβλητη και να διατηρείται καθαρή ιχνηλασιμότητα.
            df_step5 = df.copy()
            df_step5[col5] = df_step5[col4]

            updated_df, score = step5_place_remaining_students(
                df_step5,
                scenario_col=col5,
                num_classes=None,
            )
            base = ['Α/Α','ΟΝΟΜΑ','ΦΥΛΟ','ΖΩΗΡΟΣ','ΙΔΙΑΙΤΕΡΟΤΗΤΑ','ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ','ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ','ΦΙΛΟΙ']
            step_cols = [f'ΒΗΜΑ1_ΣΕΝΑΡΙΟ_{sid}', f'ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}', f'ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}', f'ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}']
            out_cols = [c for c in base + step_cols if c in updated_df.columns]
            out_df = updated_df[out_cols].copy()
            out_df[col5] = updated_df[col5]
            out_df.to_excel(writer, index=False, sheet_name=sh)
    return out_xlsx_path
