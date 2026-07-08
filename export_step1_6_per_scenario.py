import pandas as pd
# -*- coding: utf-8 -*-
"""
export_step1_6_per_scenario.py — ΔΙΟΡΘΩΜΕΝΟΣ exporter (1→6)

Εκθέτει τη συνάρτηση:
    build_step1_6_per_scenario(input_excel, output_excel, pick_step4="best")

Τρέχει ΟΛΟΚΛΗΡΗ τη ροή: Βήματα 1→6
"""

from typing import Optional, List, Tuple
import importlib.util, sys, re, numpy as np, pandas as pd
from pathlib import Path

CORE_COLUMNS = [
    "ΟΝΟΜΑ","ΦΥΛΟ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ",
    "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ","ΣΥΓΚΡΟΥΣΗ"
]

def _import(modname: str, path: Path):
    spec = importlib.util.spec_from_file_location(modname, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return mod

def _sid(col: str) -> int:
    m = re.search(r"ΣΕΝΑΡΙΟ[_\s]*(\d+)", str(col))
    return int(m.group(1)) if m else 1

def _dedup(df: pd.DataFrame) -> pd.DataFrame:
    if df.columns.duplicated().any():
        df = df.loc[:, ~df.columns.duplicated(keep="first")]
    return df


def _safe_conflict_violations(m_conflict, df: pd.DataFrame, scenario_col: str, conflict_pairs):
    """Επιστρέφει λίστα παραβιάσεων δηλωμένων συγκρούσεων για μία στήλη σεναρίου.
    Δεν αλλάζει το DataFrame και δεν απορρίπτει σενάρια· χρησιμοποιείται για audit.
    """
    if m_conflict is None or scenario_col not in df.columns:
        return []
    try:
        viol_df = m_conflict.list_conflict_violations(df, scenario_col, conflict_pairs)
        if hasattr(viol_df, "to_dict"):
            return viol_df.to_dict("records")
        return list(viol_df)
    except Exception as e:
        return [{"error": f"conflict audit failed: {e}", "scenario_col": scenario_col}]


def _append_conflict_audit_rows(audit_rows: list, m_conflict, df: pd.DataFrame, scenario_col: str,
                                conflict_pairs, sheet_name: str, step_name: str):
    """Προσθέτει γραμμές audit για τις δηλωμένες συγκρούσεις που εμφανίζονται στο συγκεκριμένο σενάριο."""
    violations = _safe_conflict_violations(m_conflict, df, scenario_col, conflict_pairs)
    for v in violations:
        audit_rows.append({
            "SHEET": sheet_name,
            "STEP": step_name,
            "SCENARIO_COL": scenario_col,
            "ΜΑΘΗΤΗΣ_A": v.get("ΜΑΘΗΤΗΣ_A", "") if isinstance(v, dict) else "",
            "ΜΑΘΗΤΗΣ_B": v.get("ΜΑΘΗΤΗΣ_B", "") if isinstance(v, dict) else "",
            "ΤΜΗΜΑ": v.get("ΤΜΗΜΑ", "") if isinstance(v, dict) else "",
            "ΣΕΝΑΡΙΟ": v.get("ΣΕΝΑΡΙΟ", scenario_col) if isinstance(v, dict) else scenario_col,
            "DETAILS": str(v),
        })
    return len(violations)

def build_step1_6_per_scenario(input_excel: str, output_excel: str, pick_step4: str = "best") -> None:
    root = Path(__file__).parent
    
    # Import όλων των modules
    m_step1 = _import("step1_immutable_ALLINONE", root / "step1_immutable_ALLINONE.py")
    m_help2 = _import("step_2_helpers_FIXED", root / "step_2_helpers_FIXED.py")
    m_step2 = _import("step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED", root / "step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED.py")
    m_h3    = _import("step3_amivaia_filia_FIXED", root / "step3_amivaia_filia_FIXED.py")
    m_step4 = _import("step4_corrected", root / "step4_corrected.py")
    m_step5 = _import("step5_enhanced", root / "step5_enhanced.py")
    m_step6 = _import("step6_compliant", root / "step6_compliant.py")
    m_conflict = _import("conflict_guard", root / "conflict_guard.py")

    # Συμβατότητα υπογραφής στο Step4
    if hasattr(m_step4, "count_groups_by_category_per_class_strict"):
        _orig = m_step4.count_groups_by_category_per_class_strict
        def _count_wrapper(df, assigned_column, classes, step1_results=None, detected_pairs=None):
            return _orig(df, assigned_column, classes, step1_results, detected_pairs)
        m_step4.count_groups_by_category_per_class_strict = _count_wrapper

    xls = pd.ExcelFile(input_excel)
    df0 = xls.parse(xls.sheet_names[0])

    # Δηλωμένες/εξωτερικές συγκρούσεις: υπολογίζονται ΜΙΑ φορά από το πλήρες αρχικό Excel.
    conflict_data = m_conflict.extract_conflict_data(df0)
    conflict_pairs = conflict_data.pairs
    conflict_audit_rows = []

    # STEP 1
    df1, _ = m_step1.create_immutable_step1(df0, num_classes=None)

    # Κενά -> NaN
    for c in [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")]:
        mask = df1[c].astype(str).str.strip() == ""
        df1.loc[mask, c] = np.nan

    step1_cols = sorted(
        [c for c in df1.columns if str(c).startswith("ΒΗΜΑ1_ΣΕΝΑΡΙΟ_")],
        key=_sid
    )

    with pd.ExcelWriter(output_excel, engine="xlsxwriter") as w:
        for s1col in step1_cols:
            sid = _sid(s1col)

            # STEP 2
            options2 = m_step2.step2_apply_FIXED_v3(df1.copy(), step1_col_name=s1col, seed=42, max_results=5)
            if options2:
                df2 = options2[0][1]
                s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}"
                if s2col not in df2.columns:
                    cands = [c for c in df2.columns if str(c).startswith("ΒΗΜΑ2_")]
                    s2col = cands[0] if cands else s2col
                    if s2col not in df2.columns:
                        df2[s2col] = ""
            else:
                df2 = df1.copy(); s2col = f"ΒΗΜΑ2_ΣΕΝΑΡΙΟ_{sid}"; df2[s2col] = ""

            base = df1.copy()
            base = base.merge(df2[["ΟΝΟΜΑ", s2col]], on="ΟΝΟΜΑ", how="left")

            # Βάλε τη ΒΗΜΑ2 δίπλα στη ΒΗΜΑ1
            cols = base.columns.tolist()
            if s2col in cols: cols.remove(s2col)
            idx = cols.index(s1col) + 1 if s1col in cols else len(cols)
            cols = cols[:idx] + [s2col] + cols[idx:]
            base = base[cols]

            # STEP 3
            df3, _ = m_h3.apply_step3_on_sheet(base.copy(), scenario_col=s2col, num_classes=None)
            s3col = f"ΒΗΜΑ3_ΣΕΝΑΡΙΟ_{sid}"
            cands3 = [c for c in df3.columns if str(c).startswith("ΒΗΜΑ3_")]
            if cands3 and s3col not in cands3:
                df3 = df3.rename(columns={cands3[0]: s3col})
            elif s3col not in df3.columns:
                df3[s3col] = ""

            # Βάλε τη ΒΗΜΑ3 δίπλα στη ΒΗΜΑ2
            cols3 = df3.columns.tolist()
            if s3col in cols3: cols3.remove(s3col)
            idx2 = cols3.index(s2col) + 1 if s2col in cols3 else len(cols3)
            cols3 = cols3[:idx2] + [s3col] + cols3[idx2:]
            df3 = df3[cols3]

            # Προετοιμασία ΦΙΛΟΙ για Step4
            if "ΦΙΛΟΙ" in df3.columns:
                try:
                    df3["ΦΙΛΟΙ"] = df3["ΦΙΛΟΙ"].apply(m_help2.parse_friends_cell)
                except Exception:
                    pass

            # STEP 4
            res4 = m_step4.apply_step4_with_enhanced_strategy(
                df3.copy(), assigned_column=s3col, num_classes=None, max_results=5
            )
            
            s4final = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid}"
            if (res4 is not None) and not (isinstance(res4, pd.DataFrame) and res4.empty):
                # If step4 returns a DataFrame (new API), use it directly; else expect legacy list-of-(df,penalty)
                if isinstance(res4, pd.DataFrame):
                    df4_mat = res4
                    # Decide the source Step4 column
                    if str(pick_step4).lower() == "best":
                        try:
                            _k, best_col = m_step4._pick_best_step4_col(df4_mat) if hasattr(m_step4, "_pick_best_step4_col") else (None, None)
                        except Exception:
                            best_col = None
                        # fallback: first ΒΗΜΑ4_ΣΕΝΑΡΙΟ_k
                        if best_col is None or best_col not in df4_mat.columns:
                            cands4 = [c for c in df4_mat.columns if str(c).startswith("ΒΗΜΑ4_ΣΕΝΑΡΙΟ_")]
                            best_col = cands4[0] if cands4 else None
                        src = best_col if best_col else None
                    else:
                        try:
                            idx_pick = max(1, min(int(pick_step4), 99))
                        except Exception:
                            idx_pick = 1
                        src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{idx_pick}"
                else:
                    # Legacy behavior: res4 is iterable of scenarios with penalties
                    df4_mat = m_step4.export_step4_scenarios(df3.copy(), res4, assigned_column=s3col)
                    if str(pick_step4).lower() == "best":
                        penalties = [p for (_, p) in res4]
                        best_idx = int(min(range(len(penalties)), key=lambda i: penalties[i]))
                        src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{best_idx+1}"
                    else:
                        try:
                            idx_pick = max(1, min(int(pick_step4), len(res4)))
                        except Exception:
                            idx_pick = 1
                        src = f"ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{idx_pick}"
                # Build df4 using the chosen src
                cands4 = [c for c in df4_mat.columns if str(c).startswith("ΒΗΜΑ4_")]
                if src and (src in df4_mat.columns):
                    df4 = df4_mat.rename(columns={src: s4final})
                elif cands4:
                    df4 = df4_mat.rename(columns={cands4[0]: s4final})
                else:
                    # 🚑 SAFETY FALLBACK:
                    # If Step 4 didn't produce any usable column (no ΒΗΜΑ4_* and no 'src'),
                    # create ΒΗΜΑ4_ΣΕΝΑΡΙΟ_{sid} by copying Step 3 assignments (or empty strings if missing).
                    df4 = df3.copy()
                    df4[s4final] = df3[s3col] if s3col in df3.columns else ""
            else:
                df4 = df3.copy(); df4[s4final] = ""

            # Βάλε τη ΒΗΜΑ4 δίπλα στη ΒΗΜΑ3
            cols4 = df4.columns.tolist()
            if s4final in cols4: cols4.remove(s4final)
            idx3 = cols4.index(s3col) + 1 if s3col in cols4 else len(cols4)
            cols4 = cols4[:idx3] + [s4final] + cols4[idx3:]
            df4 = df4[cols4]
            df4 = _dedup(df4)

            
            # STEP 5
            df5_tmp, _pen5 = m_step5.step5_place_remaining_students(df4.copy(), scenario_col=s4final, num_classes=None)
            s5col = f"ΒΗΜΑ5_ΣΕΝΑΡΙΟ_{sid}"
            # Κρατάμε το ΒΗΜΑ4 από το df4 (πριν το Βήμα 5) και προσθέτουμε ΝΕΑ στήλη ΒΗΜΑ5 με τα αποτελέσματα του Βήματος 5
            df5 = df4.copy()
            df5[s5col] = df5_tmp[s4final]
            cols5 = df5.columns.tolist()
            if s5col in cols5: cols5.remove(s5col)
            idx4 = cols5.index(s4final) + 1 if s4final in cols5 else len(cols5)
            cols5 = cols5[:idx4] + [s5col] + cols5[idx4:]

            df5 = df5[cols5]

            # STEP 6 - ΠΡΟΣΘΗΚΗ
            # Προετοιμασία δεδομένων για Step 6
            df5_prep = df5.copy()
            if "Α/Α" not in df5_prep.columns:
                df5_prep["Α/Α"] = range(1, len(df5_prep) + 1)
            if "ΤΜΗΜΑ_ΒΗΜΑ1" not in df5_prep.columns: 
                df5_prep["ΤΜΗΜΑ_ΒΗΜΑ1"] = df5_prep[s1col]
            if "ΤΜΗΜΑ_ΒΗΜΑ2" not in df5_prep.columns: 
                df5_prep["ΤΜΗΜΑ_ΒΗΜΑ2"] = df5_prep[s2col]
            if "GROUP_ID" not in df5_prep.columns: 
                df5_prep["GROUP_ID"] = np.nan
            if "ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ" not in df5_prep.columns:
                df5_prep["ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ"] = [
                    4 if str(l).strip() != "" else (5 if str(m).strip() != "" else np.nan) 
                    for l, m in zip(df5_prep[s4final], df5_prep[s5col])
                ]

            # Εκτέλεση Step 6
            try:
                step6_result = m_step6.apply_step6(
                    df5_prep.copy(),
                    class_col=s5col, 
                    id_col="Α/Α",
                    gender_col="ΦΥΛΟ", 
                    lang_col="ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ",
                    step_col="ΒΗΜΑ_ΤΟΠΟΘΕΤΗΣΗΣ", 
                    group_col="GROUP_ID",
                    max_iter=5
                )
                df6 = step6_result["df"]
                
                s6col = f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{sid}"
                # Χρήση του τελικού αποτελέσματος από Step 6
                if "ΒΗΜΑ6_ΤΜΗΜΑ" in df6.columns:
                    df6[s6col] = df6["ΒΗΜΑ6_ΤΜΗΜΑ"]
                elif f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{sid}" in df6.columns:
                    pass  # Ήδη υπάρχει
                else:
                    df6[s6col] = df6[s5col]  # Fallback
                
                # Βάλε τη ΒΗΜΑ6 δίπλα στη ΒΗΜΑ5
                cols6 = df6.columns.tolist()
                if s6col in cols6: cols6.remove(s6col)
                idx5 = cols6.index(s5col) + 1 if s5col in cols6 else len(cols6)
                cols6 = cols6[:idx5] + [s6col] + cols6[idx5:]
                df6 = df6[cols6]
                
            except Exception as e:
                print(f"Σφάλμα στο Step 6 για σενάριο {sid}: {e}")
                df6 = df5.copy()
                s6col = f"ΒΗΜΑ6_ΣΕΝΑΡΙΟ_{sid}"
                df6[s6col] = df6[s5col]  # Fallback: ΒΗΜΑ6 = ΒΗΜΑ5

            # Κράτα CORE στήλες + όλα τα βήματα
            keep = [c for c in CORE_COLUMNS if c in df6.columns] + [s1col, s2col, s3col, s4final, s5col, s6col]
            out_df = _dedup(df6[keep].copy())

            sheet_name = f"ΣΕΝΑΡΙΟ_{sid}"

            # Audit δηλωμένων συγκρούσεων για κάθε παραγόμενη στήλη βήματος.
            # Δεν απορρίπτουμε εδώ το σενάριο· η τελική επιλογή γίνεται στο app.py.
            for _step_name, _col in [
                ("STEP1", s1col),
                ("STEP2", s2col),
                ("STEP3", s3col),
                ("STEP4", s4final),
                ("STEP5", s5col),
                ("STEP6", s6col),
            ]:
                if _col in out_df.columns:
                    _append_conflict_audit_rows(
                        conflict_audit_rows, m_conflict, out_df, _col, conflict_pairs, sheet_name, _step_name
                    )

            out_df.to_excel(w, sheet_name=sheet_name[:31], index=False)

        # Extra φύλλα διαφάνειας για το workbook 1→6.
        if conflict_audit_rows:
            pd.DataFrame(conflict_audit_rows).to_excel(w, sheet_name="CONFLICT_AUDIT"[:31], index=False)
        else:
            pd.DataFrame([{"STATUS": "OK", "MESSAGE": "Δεν βρέθηκαν δηλωμένες συγκρούσεις στα σενάρια 1→6."}]).to_excel(
                w, sheet_name="CONFLICT_AUDIT"[:31], index=False
            )

        try:
            unresolved_df = m_conflict.unresolved_to_dataframe(conflict_data)
            if unresolved_df is not None and not unresolved_df.empty:
                unresolved_df.to_excel(w, sheet_name="UNRESOLVED_CONFLICTS"[:31], index=False)
        except Exception:
            pass

# Aliases για συμβατότητα
build_step1_4_per_scenario = build_step1_6_per_scenario
build_step1_5_per_scenario = build_step1_6_per_scenario
