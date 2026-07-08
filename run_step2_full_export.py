# -*- coding: utf-8 -*-
"""
run_step2_full_export.py
---------------------------------
Ασφαλές για import (δεν "τρέχει" αυτόματα). Παρέχει:
  • main(step1_workbook_path, out_xlsx_path, seed=42, max_results=5, sheet_naming="ΣΕΝΑΡΙΟ_{id}")
  • CLI: python run_step2_full_export.py -i <STEP1.xlsx> -o <STEP2.xlsx> [--seed 42] [--max-results 5] [--sheet-naming "ΣΕΝΑΡΙΟ_{id}"]

Επιστρέφει/γράφει το αρχείο STEP2 (ένα φύλλο ανά σενάριο) με τις στήλες του αρχικού + ΒΗΜΑ2_ΣΕΝΑΡΙΟ_N αμέσως δεξιά από ΒΗΜΑ1_ΣΕΝΑΡΙΟ_N.
"""
from __future__ import annotations
import argparse
from pathlib import Path
from typing import Optional

from step2_finalize import export_step2_nextcol_full


def main(
    step1_workbook_path: str,
    out_xlsx_path: str,
    seed: int = 42,
    max_results: int = 5,
    sheet_naming: str = "ΣΕΝΑΡΙΟ_{id}",
) -> None:
    """
    Τρέχει τον πλήρη exporter του Βήματος 2.

    Args:
        step1_workbook_path: Διαδρομή στο Excel εξόδου από το Βήμα 1 (multi-sheet).
        out_xlsx_path: Διαδρομή για αποθήκευση του παραγόμενου αρχείου Βήματος 2.
        seed: Τυχαίος seed για αναπαραγωγιμότητα όπου χρησιμοποιείται.
        max_results: Μέγιστος αριθμός σεναρίων προς εξαγωγή.
        sheet_naming: Pattern ονοματοδοσίας φύλλων (π.χ. "ΣΕΝΑΡΙΟ_{id}").
    """
    in_path = Path(step1_workbook_path)
    if not in_path.exists():
        raise FileNotFoundError(f"Δεν βρέθηκε το αρχείο εισόδου: {in_path}")

    out_path = Path(out_xlsx_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    export_step2_nextcol_full(
        step1_workbook_path=str(in_path),
        out_xlsx_path=str(out_path),
        seed=seed,
        max_results=max_results,
        sheet_naming=sheet_naming,
    )
    print(f"OK: Δημιουργήθηκε το {out_path.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Βήμα 2 — Πλήρης εξαγωγή (κρατά όλες τις στήλες + ΒΗΜΑ2_ΣΕΝΑΡΙΟ_N).",
    )
    parser.add_argument(
        "-i", "--in",
        dest="step1_workbook_path",
        required=True,
        help="Excel από το Βήμα 1 (multi-sheet).",
    )
    parser.add_argument(
        "-o", "--out",
        dest="out_xlsx_path",
        required=True,
        help="Διαδρομή για το αρχείο εξόδου Βήματος 2 (π.χ. STEP2_NEXTCOL_FULL.xlsx).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed (default: 42).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=5,
        help="Μέγιστος αριθμός σεναρίων προς εξαγωγή (default: 5).",
    )
    parser.add_argument(
        "--sheet-naming",
        type=str,
        default="ΣΕΝΑΡΙΟ_{id}",
        help='Pattern ονοματοδοσίας φύλλων (default: "ΣΕΝΑΡΙΟ_{id}").',
    )

    args = parser.parse_args()
    main(
        step1_workbook_path=args.step1_workbook_path,
        out_xlsx_path=args.out_xlsx_path,
        seed=args.seed,
        max_results=args.max_results,
        sheet_naming=args.sheet_naming,
    )
