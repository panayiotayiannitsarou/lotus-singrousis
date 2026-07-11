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
    candidate_pool_size: int = 100,
    max_search_nodes: Optional[int] = None,
) -> List[Tuple[str, pd.DataFrame, Dict[str, Any]]]:
    """
    Βελτιστοποιημένο ακριβές Branch-and-Bound για το Βήμα 2.

    Η παιδαγωγική σειρά παραμένει ίδια:
    1. καμία δηλωμένη σύγκρουση (hard constraint),
    2. τήρηση των στόχων ΖΩΗΡΩΝ/ΙΔΙΑΙΤΕΡΟΤΗΤΩΝ,
    3. αν υπάρχει λύση με 0 παιδαγωγικά δύσκολες συνυπάρξεις, προτιμάται,
    4. λιγότερες σπασμένες αμοιβαίες φιλίες,
    5. μικρότερο συνολικό penalty.

    Η διαφορά από την παλιά έκδοση είναι τεχνική: δεν αντιγράφει DataFrame σε
    κάθε κόμβο, χρησιμοποιεί incremental counters και κόβει νωρίς κλαδιά που
    δεν μπορούν πλέον να φτάσουν τους ελάχιστους/μέγιστους στόχους.
    """
    random.seed(seed)
    df = normalize_columns(df_in).copy()
    num_classes = _auto_num_classes(df, num_classes)
    class_labels = [f"Α{i+1}" for i in range(num_classes)]
    scope = scope_step2(df, step1_col=step1_col_name)

    # Ανθεκτική αντιμετώπιση κενών: NaN, "" και strings με spaces.
    step1_clean = df[step1_col_name].apply(
        lambda x: "" if pd.isna(x) else str(x).strip()
    )
    df[step1_col_name] = step1_clean.replace("", pd.NA)

    conflict_pairs, unresolved_conflicts = _extract_declared_conflict_pairs(df)

    rows_by_name = {
        str(r["ΟΝΟΜΑ"]).strip(): r
        for _, r in df.iterrows()
    }
    names = list(rows_by_name)
    z_flag = {
        n: str(rows_by_name[n].get("ΖΩΗΡΟΣ", "")).strip() == "Ν"
        for n in names
    }
    i_flag = {
        n: str(rows_by_name[n].get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ", "")).strip() == "Ν"
        for n in names
    }

    fixed_class = {}
    for _, r in df.iterrows():
        n = str(r["ΟΝΟΜΑ"]).strip()
        cl = r.get(step1_col_name)
        if pd.notna(cl) and str(cl).strip() in class_labels:
            fixed_class[n] = str(cl).strip()

    to_place = [
        n for n in names
        if n not in fixed_class and (z_flag[n] or i_flag[n])
    ]
    targets = _compute_targets_global(df, step1_col=step1_col_name, class_labels=class_labels)

    # Canonical conflict adjacency για O(1) έλεγχο χωρίς προσωρινά DataFrames.
    def _canon(x):
        if _conflict_guard is not None and hasattr(_conflict_guard, "canon_name"):
            return _conflict_guard.canon_name(x)
        return str(x).strip().upper()

    canon_to_name = {_canon(n): n for n in names}
    conflict_adj = {n: set() for n in names}
    for a, b in conflict_pairs or []:
        na = canon_to_name.get(_canon(a))
        nb = canon_to_name.get(_canon(b))
        if na and nb and na != nb:
            conflict_adj[na].add(nb)
            conflict_adj[nb].add(na)

    # Ασφαλές fallback όταν το conflict_guard δεν είναι διαθέσιμο ή δεν επέστρεψε
    # ζεύγη. Διαβάζει και τις μονόπλευρες δηλώσεις της στήλης ΣΥΓΚΡΟΥΣΗ και
    # τις μετατρέπει σε συμμετρική adjacency, ώστε η σύγκρουση να παραμένει hard constraint.
    if "ΣΥΓΚΡΟΥΣΗ" in df.columns:
        for _, r in df.iterrows():
            src_name = str(r.get("ΟΝΟΜΑ", "")).strip()
            if src_name not in conflict_adj:
                continue
            for token in parse_friends_cell(r.get("ΣΥΓΚΡΟΥΣΗ", "")):
                dst_name = canon_to_name.get(_canon(token))
                if dst_name and dst_name != src_name:
                    conflict_adj[src_name].add(dst_name)
                    conflict_adj[dst_name].add(src_name)

    def _scenario_has_conflict(scenario_df: pd.DataFrame, scenario_col: str) -> bool:
        """Τελικός καθολικός έλεγχος δηλωμένων συγκρούσεων για ολόκληρο το σενάριο."""
        if scenario_col not in scenario_df.columns:
            return True

        # Πρώτα χρησιμοποιείται ο κοινός guard, όταν είναι διαθέσιμος.
        if _conflict_guard is not None and conflict_pairs:
            try:
                if _conflict_guard.has_conflict_violation(
                    scenario_df, scenario_col, conflict_pairs
                ):
                    return True
            except Exception as e:
                print(f"⚠️ Αποτυχία τελικού conflict_guard ελέγχου στο Step 2: {e}")

        # Ανεξάρτητη δεύτερη δικλείδα με την adjacency (λειτουργεί και ως fallback).
        class_of = {}
        for _, rr in scenario_df.iterrows():
            name = str(rr.get("ΟΝΟΜΑ", "")).strip()
            cl = rr.get(scenario_col)
            if name and pd.notna(cl) and str(cl).strip():
                class_of[name] = str(cl).strip()
        for a, neighbours in conflict_adj.items():
            cl_a = class_of.get(a)
            if cl_a is None:
                continue
            for b in neighbours:
                if a < b and class_of.get(b) == cl_a:
                    return True
        return False

    # Έλεγχος πριν από την αναζήτηση: αν δύο ήδη κλειδωμένοι μαθητές του Step 1
    # συγκρούονται στο ίδιο τμήμα, το Step 2 δεν μπορεί να διορθώσει το πρόβλημα.
    fixed_conflict_pairs = []
    for a, neighbours in conflict_adj.items():
        cl_a = fixed_class.get(a)
        if cl_a is None:
            continue
        for b in neighbours:
            if a < b and fixed_class.get(b) == cl_a:
                fixed_conflict_pairs.append((a, b, cl_a))

    def deg(name: str) -> int:
        row = rows_by_name[name]
        return len(conflict_adj.get(name, ())) + len(parse_friends_cell(row.get("ΦΙΛΟΙ", "")))

    # Δυσκολότεροι/περισσότερο περιορισμένοι μαθητές πρώτα.
    to_place_sorted = sorted(
        to_place,
        key=lambda n: (
            -(z_flag[n] and i_flag[n]),
            -i_flag[n],
            -z_flag[n],
            -deg(n),
            n,
        ),
    )

    # Suffix counts για exact feasibility pruning.
    m = len(to_place_sorted)
    rem_z = [0] * (m + 1)
    rem_i = [0] * (m + 1)
    for idx in range(m - 1, -1, -1):
        n = to_place_sorted[idx]
        rem_z[idx] = rem_z[idx + 1] + int(z_flag[n])
        rem_i[idx] = rem_i[idx + 1] + int(i_flag[n])

    z_counts = targets["Z_step1"].copy()
    i_counts = targets["I_step1"].copy()
    assign: Dict[str, str] = {}

    members_by_class = {cl: [] for cl in class_labels}
    for n, cl in fixed_class.items():
        members_by_class[cl].append(n)

    # Οι αμοιβαίες φιλίες που επηρεάζονται από το Step 2.
    mutual_pairs = list(mutual_pairs_in_scope(df, scope))

    # Κρατάμε μικρό pool από τις καλύτερες πλήρεις λύσεις, όχι εκατομμύρια DataFrames.
    pool_limit = max(int(candidate_pool_size), int(max_results), 10)
    pool: List[Tuple[Tuple[int, int, int, int], Dict[str, str], int, int, int, int]] = []
    nodes_visited = 0
    complete_solutions = 0
    search_stopped_early = False

    def _pair_penalty(a: str, b: str) -> int:
        return _pair_conflict_penalty(z_flag[a], i_flag[a], z_flag[b], i_flag[b])

    def _broken_count_full() -> int:
        class_of = dict(fixed_class)
        class_of.update(assign)
        return sum(1 for a, b in mutual_pairs if class_of.get(a) != class_of.get(b))

    def _rank(ped_cnt: int, broken: int, total: int) -> Tuple[int, int, int, int]:
        # Ακριβώς η τελική λογική της παλιάς έκδοσης.
        if ped_cnt == 0:
            return (0, broken, total, ped_cnt)
        return (1, total, broken, ped_cnt)

    def _store_solution(ped_cnt: int, conf_sum: int) -> None:
        nonlocal complete_solutions
        complete_solutions += 1
        broken = _broken_count_full()
        total = conf_sum + 5 * broken
        rank = _rank(ped_cnt, broken, total)
        pool.append((rank, dict(assign), ped_cnt, broken, total, conf_sum))
        pool.sort(key=lambda x: x[0])
        if len(pool) > pool_limit:
            del pool[pool_limit:]

    def _targets_still_reachable(next_i: int) -> bool:
        """True αν οι υπόλοιποι μαθητές μπορούν ακόμη να καλύψουν όλα τα q/max."""
        rz = rem_z[next_i]
        ri = rem_i[next_i]
        for cl in class_labels:
            if z_counts[cl] > targets["Z"]["max"]:
                return False
            if i_counts[cl] > targets["I"]["max"]:
                return False
            # Ακόμη κι αν ΟΛΟΙ οι υπόλοιποι Ζ/I πάνε εδώ, φτάνουμε το ελάχιστο;
            if z_counts[cl] + rz < targets["Z"]["q"]:
                return False
            if i_counts[cl] + ri < targets["I"]["q"]:
                return False
        return True

    def _class_order(name: str) -> List[str]:
        """Δοκιμάζει πρώτα τα τμήματα με μεγαλύτερη ανάγκη στις κατηγορίες του μαθητή."""
        def key(cl: str):
            z_need = targets["Z"]["q"] - z_counts[cl] if z_flag[name] else 0
            i_need = targets["I"]["q"] - i_counts[cl] if i_flag[name] else 0
            load = len(members_by_class[cl])
            return (-(z_need + i_need), load, cl)
        return sorted(class_labels, key=key)

    def backtrack(i: int, ped_cnt: int, conf_sum: int) -> None:
        nonlocal nodes_visited, search_stopped_early
        nodes_visited += 1
        if max_search_nodes is not None and nodes_visited > int(max_search_nodes):
            search_stopped_early = True
            return

        if not _targets_still_reachable(i):
            return

        # Αν έχουμε ήδη λύση με 0 δύσκολες συνυπάρξεις, κλαδί με ped>0 δεν μπορεί να κερδίσει.
        if pool and pool[0][0][0] == 0 and ped_cnt > 0:
            return

        if i == m:
            for cl in class_labels:
                if not (targets["Z"]["q"] <= z_counts[cl] <= targets["Z"]["max"]):
                    return
                if not (targets["I"]["q"] <= i_counts[cl] <= targets["I"]["max"]):
                    return
            # Αποφυγή εκφυλιστικής λύσης όπου όλοι οι νέοι μπαίνουν στο ίδιο τμήμα.
            if m and len(set(assign.values())) == 1:
                return
            _store_solution(ped_cnt, conf_sum)
            return

        name = to_place_sorted[i]
        for cl in _class_order(name):
            # Hard conflict check με fixed + ήδη assigned μέλη του τμήματος.
            if any(member in conflict_adj.get(name, ()) for member in members_by_class[cl]):
                continue

            new_z = z_counts[cl] + int(z_flag[name])
            new_i = i_counts[cl] + int(i_flag[name])
            if new_z > targets["Z"]["max"] or new_i > targets["I"]["max"]:
                continue

            add_conf = 0
            add_ped = 0
            for member in members_by_class[cl]:
                p = _pair_penalty(name, member)
                add_conf += p
                if p > 0:
                    add_ped += 1

            assign[name] = cl
            members_by_class[cl].append(name)
            z_counts[cl] = new_z
            i_counts[cl] = new_i

            backtrack(i + 1, ped_cnt + add_ped, conf_sum + add_conf)

            i_counts[cl] -= int(i_flag[name])
            z_counts[cl] -= int(z_flag[name])
            members_by_class[cl].pop()
            del assign[name]

            if search_stopped_early and max_search_nodes is not None:
                return

    # Baseline penalties μεταξύ ήδη fixed μαθητών του Step 1.
    base_ped = 0
    base_conf = 0
    for cl in class_labels:
        members = members_by_class[cl]
        for a_i in range(len(members)):
            for b_i in range(a_i + 1, len(members)):
                p = _pair_penalty(members[a_i], members[b_i])
                base_conf += p
                if p > 0:
                    base_ped += 1

    # Δεν ξεκινά η δαπανηρή αναζήτηση όταν το εισερχόμενο Step 1 είναι ήδη
    # ασύμβατο με hard constraint που το Step 2 δεν επιτρέπεται να αλλάξει.
    if not fixed_conflict_pairs:
        backtrack(0, base_ped, base_conf)

    base_id = _extract_step1_id(step1_col_name)
    final_col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{base_id}"

    if fixed_conflict_pairs:
        tmp = df.copy()
        tmp[final_col] = tmp[step1_col_name]
        return [("option_1", tmp, {
            "ped_conflicts": None,
            "broken": None,
            "penalty": None,
            "declared_conflict_pairs": int(len(conflict_pairs)),
            "unresolved_conflicts": int(unresolved_conflicts),
            "fixed_conflict_violations": int(len(fixed_conflict_pairs)),
            "infeasible_reason": "STEP1_FIXED_CONFLICT",
            "search_nodes": 0,
            "complete_solutions": 0,
            "search_stopped_early": False,
        })]

    if not pool:
        tmp = df.copy()
        tmp[final_col] = tmp[step1_col_name]
        return [("option_1", tmp, {
            "ped_conflicts": None,
            "broken": None,
            "penalty": None,
            "declared_conflict_pairs": int(len(conflict_pairs)),
            "unresolved_conflicts": int(unresolved_conflicts),
            "search_nodes": int(nodes_visited),
            "complete_solutions": int(complete_solutions),
            "search_stopped_early": bool(search_stopped_early),
            "fixed_conflict_violations": 0,
            "infeasible_reason": (
                "SEARCH_NODE_LIMIT" if search_stopped_early else "NO_FEASIBLE_STEP2_ASSIGNMENT"
            ),
        })]

    # Μόνο οι ισόβαθμες καλύτερες λύσεις, έως max_results.
    best_rank = pool[0][0]
    selected = [x for x in pool if x[0] == best_rank][:max_results]

    results: List[Tuple[str, pd.DataFrame, Dict[str, Any]]] = []
    for k, (_rank_key, assignment, ped_cnt, broken, total, conf_sum) in enumerate(selected, start=1):
        out = df.copy()
        out[final_col] = out[step1_col_name]
        for n, cl in assignment.items():
            out.loc[out["ΟΝΟΜΑ"].astype(str).str.strip() == n, final_col] = cl
        # Τελική καθολική επαλήθευση πριν επιστραφεί οποιοδήποτε αποτέλεσμα.
        # Καλύπτει fixed-fixed, fixed-new και new-new συγκρούσεις.
        if _scenario_has_conflict(out, final_col):
            continue

        results.append((f"option_{k}", out, {
            "ped_conflicts": int(ped_cnt),
            "broken": int(broken),
            "penalty": int(total),
            "conflict_sum": int(conf_sum),
            "declared_conflict_pairs": int(len(conflict_pairs)),
            "unresolved_conflicts": int(unresolved_conflicts),
            "fixed_conflict_violations": 0,
            "final_conflict_check_passed": True,
            "search_nodes": int(nodes_visited),
            "complete_solutions": int(complete_solutions),
            "candidate_pool_size": int(len(pool)),
            "search_stopped_early": bool(search_stopped_early),
        }))

    # Θεωρητικά δεν πρέπει να συμβεί, αλλά δεν επιστρέφεται ποτέ υποψήφιο
    # που απέτυχε στον τελικό hard-constraint έλεγχο.
    if not results:
        tmp = df.copy()
        tmp[final_col] = tmp[step1_col_name]
        return [("option_1", tmp, {
            "ped_conflicts": None,
            "broken": None,
            "penalty": None,
            "declared_conflict_pairs": int(len(conflict_pairs)),
            "unresolved_conflicts": int(unresolved_conflicts),
            "fixed_conflict_violations": 0,
            "infeasible_reason": "FINAL_CONFLICT_CHECK_FAILED",
            "search_nodes": int(nodes_visited),
            "complete_solutions": int(complete_solutions),
            "candidate_pool_size": int(len(pool)),
            "search_stopped_early": bool(search_stopped_early),
        })]
    return results

