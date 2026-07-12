# -*- coding: utf-8 -*-
# Version: 2025-09-06 Clean stable build — brand: Ψηφιακή Κατανομή Μαθητών Α' Δημοτικού
import sys
SHOW_STATS_EXPORT_BUTTON = False  # κρύβει το κουμπί 'Εξαγωγή ΜΟΝΟ Στατιστικών'
import importlib
import importlib.util

import re, os, json, importlib.util, datetime as dt, math, base64, unicodedata
from pathlib import Path
from io import BytesIO

ROOT = Path(__file__).parent.resolve()

import streamlit as st
import pandas as pd

# --- Embedded logo fallback (base64) - ΚΕΝΟ για μικρότερο αρχείο ---
LOGO_B64 = ""  # Θα διαβάζει από αρχείο
LOGO_MIME = "image/png"

def _get_logo_bytes():
    """Return logo bytes: from file path if available, else from embedded base64."""
    path = None
    try:
        path = _find_logo_path()
    except Exception:
        path = None
    if path:
        try:
            return Path(path).read_bytes()
        except Exception:
            pass
    if LOGO_B64:
        try:
            return base64.b64decode(LOGO_B64)
        except Exception:
            return None
    return None

def _inject_floating_logo(width_px=62):
    """Render a floating logo at bottom-right that stays on screen while scrolling."""
    try:
        if st.session_state.get("auth_ok") and st.session_state.get("accepted_terms"):
            return
    except Exception:
        pass
    data = _get_logo_bytes()
    if not data:
        return
    b64 = base64.b64encode(data).decode('utf-8')
    mime = LOGO_MIME

    st.markdown(f"""
<style>
#floating-logo {{
  position: fixed;
  left: 285px;
  bottom: 16px;
  z-index: 9999;
  opacity: 0.95;
  pointer-events: none;
}}
#floating-logo img {{
  width: {width_px}px;
  height: auto;
  filter: drop-shadow(0 1px 2px rgba(0,0,0,0.20));
  opacity: 0.92;
}}
@media (max-width: 768px) {{
  #floating-logo img {{ width: {max(72, int(0.85*width_px))}px; }}
  #floating-logo {{ left: 285px; bottom: 12px; }}
}}
</style>
<div id="floating-logo">
  <img src="data:{mime};base64,{b64}" alt="logo" />
</div>
""", unsafe_allow_html=True)

from PIL import Image, ImageDraw, ImageFont

def _find_logo_path():
    from pathlib import Path as _P
    here = _P(__file__).parent
    candidates = [
        "logo_sidebar_preview_selected.png",
        "logo_lotus_lilac_sidebar100.png",
        "logo_lotus_lilac_original.png",
        "logo_lotus_lilac_header180.png",
        "logo_violet_white.png",
        "logo.png",
        "assets/logo.png",
        "lotus_appicon_white_1024.png",
    ]
    search_bases = [here, here / "assets", _P("/mnt/data")]
    for base in search_bases:
        for c in candidates:
            p = base / c
            if p.exists():
                return str(p)
    for base in search_bases:
        for p in base.glob("lotus*.png"):
            return str(p)
    return None

def _make_logo_with_overlay(img_path, width=140, text="«No man is an island»"):
    try:
        im = Image.open(img_path).convert("RGBA")
    except Exception:
        return None
    scale = width / im.width
    target_h = int(im.height * scale)
    im = im.resize((width, target_h), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
    draw = ImageDraw.Draw(im, "RGBA")
    font_candidates = [
        ("DejaVuSans.ttf", 20),
        ("Arial.ttf", 20),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20),
    ]
    font = None
    for fname, fsize in font_candidates:
        try:
            font = ImageFont.truetype(fname, fsize)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()
    max_w = int(width * 0.92)
    fsize = getattr(font, "size", 18)
    while True:
        bbox = draw.textbbox((0,0), text, font=font, stroke_width=2)
        tw, th = bbox[2], bbox[3]
        if tw <= max_w or fsize <= 11:
            break
        fsize -= 1
        try:
            font = ImageFont.truetype(font.path, fsize) if hasattr(font, "path") else ImageFont.truetype("DejaVuSans.ttf", fsize)
        except Exception:
            font = ImageFont.truetype("DejaVuSans.ttf", fsize)
    bbox = draw.textbbox((0,0), text, font=font, stroke_width=2)
    tw, th = bbox[2], bbox[3]
    tx = max(0, (width - tw)//2)
    ty = target_h - th - 6
    draw.text((tx, ty), text, font=font, fill=(255,255,255,255), stroke_width=2, stroke_fill=(0,0,0,220))
    return im

_logo_path = _find_logo_path()
_logo_img = None
if _logo_path:
    try:
        _logo_img = Image.open(_logo_path)
    except Exception:
        _logo_img = None

_logo_bytes = _get_logo_bytes()
_logo_img = None
if _logo_bytes:
    try:
        _logo_img = Image.open(BytesIO(_logo_bytes))
    except Exception:
        _logo_img = None

st.set_page_config(page_title="Ψηφιακή Κατανομή Μαθητών Α' Δημοτικού", page_icon="🧩", layout="wide")

st.title("Ψηφιακή Κατανομή Μαθητών Α' Δημοτικού")

try:
    _logo_inline_bytes = _get_logo_bytes()
    _logo_inline_b64 = base64.b64encode(_logo_inline_bytes).decode("ascii") if _logo_inline_bytes else ""
except Exception:
    _logo_inline_b64 = ""

st.markdown(f"""
<div style="display:flex; align-items:center; gap:8px; opacity:0.85;">
  <span>«Για μια παιδεία που βλέπει το φως σε όλα τα παιδιά»</span>
  <img src="data:image/png;base64,{_logo_inline_b64}" alt="lotus" style="width:18px; height:auto; margin-top:-2px; " />
</div>
""", unsafe_allow_html=True)

try:
    _auth = bool(st.session_state.get("auth_ok", False))
    _terms = bool(st.session_state.get("accepted_terms", False))
except Exception:
    _auth, _terms = (False, False)
if not (_auth and _terms):
    _inject_floating_logo(width_px=62)


def _load_module(name: str, file_path: Path):
    """Load a local module by name, ensuring its folder is on sys.path.
    We avoid exec_module here because dataclasses/typing may rely on
    sys.modules[name] being registered during import.
    """
    parent = str(file_path.parent)
    if parent not in sys.path:
        sys.path.insert(0, parent)
    # Remove any stale module
    if name in sys.modules:
        del sys.modules[name]
    return importlib.import_module(name)
def _read_file_bytes(path: Path) -> bytes:
    with open(path, "rb") as f:
        return f.read()

def _timestamped(base: str, ext: str) -> str:
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    import re as _re
    safe = _re.sub(r"[^A-Za-z0-9_\-\.]+", "_", base)
    return f"{safe}_{ts}{ext}"

def _find_latest_step6():
    try:
        candidates = sorted((p for p in ROOT.glob("STEP1_6_PER_SCENARIO*.xlsx") if p.is_file()),
                            key=lambda p: p.stat().st_mtime,
                            reverse=True)
        return candidates[0] if candidates else None
    except Exception:
        return None

def _check_required_files(paths):
    missing = [str(p) for p in paths if not p.exists()]
    return missing

def _inject_logo(logo_bytes: bytes, width_px: int = 140, mime: str = "image/png"):
    b64 = base64.b64encode(logo_bytes).decode("ascii")
    html = f"""
    <div style="position: fixed; bottom: 38px; right: 38px; z-index: 1000;">
        <img src="data:{mime};base64,{b64}" style="width:{width_px}px; height:auto; opacity:0.95; border-radius:12px;" />
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def _restart_app():
    for k in list(st.session_state.keys()):
        if k.startswith("uploader_") or k in ("auth_ok","accepted_terms","app_enabled","last_final_path"):
            try:
                del st.session_state[k]
            except Exception:
                pass
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    try:
        for pat in ("STEP7_FINAL_SCENARIO*.xlsx", "STEP1_6_PER_SCENARIO*.xlsx", "INPUT_STEP1*.xlsx", "STEP8_*.xlsx"):
            for f in ROOT.glob(pat):
                try:
                    f.unlink()
                except Exception:
                    pass
    except Exception:
        pass
    st.rerun()

def _terms_md():
    return """
**Υποχρεωτική Αποδοχή Όρων Χρήσης**  
Χρησιμοποιώντας την εφαρμογή δηλώνετε ότι:  
- Δεν τροποποιείτε τη λογική των αλγορίθμων και δεν αναδιανέμετε τα αρχεία χωρίς άδεια.  
- Αναλαμβάνετε την ευθύνη για την ορθότητα των εισαγόμενων δεδομένων.  
- Η εφαρμογή παρέχεται «ως έχει», χωρίς εγγύηση για οποιαδήποτε χρήση.  

**Πνευματικά Δικαιώματα & Νομική Προστασία**  
© 2025 Γιαννίτσαρου Παναγιώτα — όλα τα δικαιώματα διατηρούνται.  
Για άδεια χρήσης/συνεργασίες: *panayiotayiannitsarou@gmail.com*.
"""

def _story_md():
    return """
**Η εφαρμογή αυτή γεννήθηκε από μια εσωτερική ανάγκη:** να θυμίσει ότι **κανένα παιδί δεν πρέπει να μένει στο περιθώριο**. Το παιδί δεν είναι απλώς ένα όνομα σε λίστα. Είναι παρουσία, ψυχή, μέλος μιας ομάδας. Μια απερίσκεπτη κατανομή ή ένας λανθασμένος παιδαγωγικός χειρισμός μπορεί να ταράξει την ευθραυστη ψυχική ισορροπία ενός παιδιού — και μαζί της, την ηρεμία μιας οικογένειας.

Όπως έγραψε ο John Donne, «Κανένας άνθρωπος δεν είναι νησί» ("No man is an island")¹: κανείς δεν υπάρχει απομονωμένος· ό,τι συμβαίνει σε έναν, αφορά όλους. Είμαστε μέρος ενός ευρύτερου συνόλου· η μοίρα, η χαρά ή ο πόνος του άλλου μας αγγίζουν, γιατί είμαστε συνδεδεμένοι.

Στο σχολείο αυτό γίνεται πράξη: κάθε απόφαση είναι πράξη παιδαγωγικής ευθύνης. Ένα πρόγραμμα κατανομής δεν είναι ποτέ απλώς ένα τεχνικό εργαλείο. Είναι **έκφραση παιδαγωγικής ευθύνης** και **κοινωνικής ευαισθησίας**. Δεν είναι μόνο αλγόριθμος· είναι έκφραση κοινωνικής ευαισθησίας και εμπιστοσύνης στο μέλλον — των παιδιών και της κοινωνίας.

*¹ Η φράση υπογραμμίζει ότι κανείς δεν είναι πλήρως ανεξάρτητος.*

— Με εκτίμηση,  
**Γιαννίτσαρου Παναγιώτα**

**Απόσπασμα από τον John Donne**
> No man is an island,
> Entire of itself;
> Every man is a piece of the continent,
> A part of the main.
> If a clod be washed away by the sea,
> Europe is the less,
> As well as if a promontory were,
> As well as if a manor of thy friend's
> Or of thine own were.
> Any man's death diminishes me,
> Because I am involved in mankind.
> And therefore never send to know for whom the bell tolls;
> It tolls for thee.

— *John Donne*
"""

REQUIRED = [
    ROOT / "conflict_guard.py",
    ROOT / "export_step1_6_per_scenario.py",
    ROOT / "step1_immutable_ALLINONE.py",
    ROOT / "step_2_helpers_FIXED.py",
    ROOT / "step_2_zoiroi_idiaterotites_FIXED_v3_PATCHED.py",
    ROOT / "step3_amivaia_filia_FIXED.py",
    ROOT / "step4_corrected.py",
    ROOT / "step5_enhanced.py",
    ROOT / "step6_compliant.py",
    ROOT / "step7_fixed_final.py",
    ROOT / "step8_fixed_final.py",  # ΝΕΟ
]

with st.sidebar:
    st.header("🔐 Πρόσβαση & Ρυθμίσεις")
    
    if "auth_ok" not in st.session_state:
        st.session_state.auth_ok = False
    pwd = st.text_input("Κωδικός πρόσβασης", type="password")
    if pwd:
        st.session_state.auth_ok = (pwd.strip() == "katanomi2025")
        if not st.session_state.auth_ok:
            st.error("Λανθασμένος κωδικός.")
    
    if "accepted_terms" not in st.session_state:
        st.session_state.accepted_terms = False
    st.session_state.accepted_terms = st.checkbox(
        "✅ Αποδέχομαι τους Όρους Χρήσης",
        value=st.session_state.get("accepted_terms", False)
    )
    
    with st.expander("📄 Όροι Χρήσης & Πνευματικά Δικαιώματα", expanded=False):
        st.markdown(_terms_md())
    
    if "show_story" not in st.session_state:
        st.session_state.show_story = False
    if st.button("🧭 Η Ιστορία της Δημιουργίας & Πηγή Έμπνευσης", use_container_width=True, key="btn_story"):
        st.session_state.show_story = not st.session_state.show_story
    if st.session_state.show_story:
        st.markdown(_story_md())

st.divider()

if not st.session_state.auth_ok:
    st.warning("🔒 Εισάγετε τον σωστό κωδικό για πρόσβαση (αριστερά).")
    st.stop()

if not st.session_state.accepted_terms:
    st.warning("✅ Για να συνεχίσετε, αποδεχθείτε τους Όρους Χρήσης (αριστερά).")
    st.stop()

st.subheader("📦 Έλεγχος αρχείων")
missing = _check_required_files(REQUIRED)
if missing:
    st.error("❌ Λείπουν αρχεία:\n" + "\n".join(f"- {m}" for m in missing))
else:
    st.success("✅ Όλα τα απαραίτητα αρχεία βρέθηκαν.")

st.divider()

st.header("🚀 Εκτέλεση Κατανομής")

up_all = st.file_uploader("Ανέβασε αρχικό Excel (για 1→7)", type=["xlsx"], key="uploader_all")
colA, colB, colC = st.columns([1,1,1])
with colA:
    pick_step4_all = st.selectbox("Κανόνας επιλογής στο Βήμα 4", ["best", "first", "strict"], index=0, key="pick_all")
with colB:
    final_name_all = st.text_input("Όνομα αρχείου Τελικού Αποτελέσματος", value=_timestamped("STEP7_FINAL_SCENARIO", ".xlsx"))
with colC:
    if up_all is not None:
        try:
            df_preview = pd.read_excel(up_all, sheet_name=0)
            N = df_preview.shape[0]
            min_classes = max(2, math.ceil(N/25)) if N else 0
            st.metric("Μαθητές / Ελάχιστα τμήματα", f"{N} / {min_classes}")
        except Exception:
            st.caption("Δεν ήταν δυνατή η ανάγνωση για προεπισκόπηση.")

if st.button("🚀 ΕΚΤΕΛΕΣΗ ΚΑΤΑΝΟΜΗΣ", type="primary", use_container_width=True):
    if missing:
        st.error("Δεν είναι δυνατή η εκτέλεση: λείπουν modules.")
    elif up_all is None:
        st.warning("Πρώτα ανέβασε ένα Excel.")
    else:
        try:
            input_path = ROOT / _timestamped("INPUT_STEP1", ".xlsx")
            with open(input_path, "wb") as f:
                f.write(up_all.getbuffer())

            m = _load_module("export_step1_6_per_scenario", ROOT / "export_step1_6_per_scenario.py")
            s7 = _load_module("step7_fixed_final", ROOT / "step7_fixed_final.py")
            cg = _load_module("conflict_guard", ROOT / "conflict_guard.py")

            # Δηλωμένες/εξωτερικές συγκρούσεις: υπολογίζονται ΜΙΑ φορά από το πλήρες αρχικό Excel.
            # Δεν αλλάζουμε το step7_fixed_final.py εδώ· απλώς προστατεύουμε την τελική επιλογή μέσα στο app.
            df_input_full = pd.read_excel(input_path, sheet_name=0)
            conflict_data = cg.extract_conflict_data(df_input_full, warn_if_missing_col=True, warn_unresolved=True)
            conflict_pairs = conflict_data.pairs

            if conflict_data.unresolved:
                st.warning(f"⚠️ Υπάρχουν {len(conflict_data.unresolved)} ονόματα στη ΣΥΓΚΡΟΥΣΗ που δεν αναγνωρίστηκαν. Έλεγξε τα δεδομένα εισόδου.")
                try:
                    with st.expander("🔎 Μη αναγνωρισμένα ονόματα στη ΣΥΓΚΡΟΥΣΗ", expanded=False):
                        st.dataframe(cg.unresolved_to_dataframe(conflict_data), use_container_width=True)
                except Exception:
                    pass

            step6_path = ROOT / _timestamped("STEP1_6_PER_SCENARIO", ".xlsx")
            with st.spinner("Τρέχουν τα Βήματα 1→6..."):
                m.build_step1_6_per_scenario(str(input_path), str(step6_path), pick_step4=pick_step4_all)

            with st.spinner("Τρέχει η τελική επιλογή σεναρίου..."):
                xls = pd.ExcelFile(step6_path)
                sheet_names = [s for s in xls.sheet_names if s != "Σύνοψη"]
                if not sheet_names:
                    st.error("Δεν βρέθηκαν sheets σεναρίων (εκτός από 'Σύνοψη').")
                else:
                    candidates = []
                    rejected_conflict_rows = []
                    total_scenario_cols = 0
                    import random as _rnd
                    for sheet in sheet_names:
                        df_sheet = pd.read_excel(step6_path, sheet_name=sheet)
                        scen_cols = [c for c in df_sheet.columns if re.match(r"^ΒΗΜΑ6_ΣΕΝΑΡΙΟ_\d+$", str(c))]
                        for col in scen_cols:
                            total_scenario_cols += 1

                            # Hard constraint: κανένα τελικό υποψήφιο σενάριο με δηλωμένη σύγκρουση.
                            try:
                                viol = cg.list_conflict_violations(df_sheet, col, conflict_pairs=conflict_pairs)
                            except Exception as _e:
                                st.error(f"Σφάλμα ελέγχου δηλωμένων συγκρούσεων στο {sheet}/{col}: {_e}")
                                continue

                            if not viol.empty:
                                for _, vr in viol.iterrows():
                                    rejected_conflict_rows.append({
                                        "ΦΥΛΛΟ": sheet,
                                        "ΣΕΝΑΡΙΟ": col,
                                        "ΜΑΘΗΤΗΣ_A": vr.get("ΜΑΘΗΤΗΣ_A", ""),
                                        "ΜΑΘΗΤΗΣ_B": vr.get("ΜΑΘΗΤΗΣ_B", ""),
                                        "ΤΜΗΜΑ": vr.get("ΤΜΗΜΑ", ""),
                                    })
                                continue

                            s = s7.score_one_scenario(df_sheet, col)
                            s["sheet"] = sheet
                            s["declared_conflict_violations"] = 0
                            candidates.append(s)

                    if rejected_conflict_rows:
                        rej_df = pd.DataFrame(rejected_conflict_rows)
                        st.warning(
                            f"⚠️ Απορρίφθηκαν {rej_df[['ΦΥΛΛΟ','ΣΕΝΑΡΙΟ']].drop_duplicates().shape[0]} "
                            f"από {total_scenario_cols} υποψήφια σενάρια λόγω δηλωμένων συγκρούσεων."
                        )
                        with st.expander("📋 Audit απορριφθέντων σεναρίων λόγω δηλωμένων συγκρούσεων", expanded=False):
                            st.dataframe(rej_df, use_container_width=True)

                    if not candidates:
                        if total_scenario_cols == 0:
                            st.error("Δεν βρέθηκαν σενάρια Βήματος 6 σε κανένα φύλλο.")
                        else:
                            st.error("Δεν έμεινε κανένα έγκυρο σενάριο χωρίς δηλωμένες συγκρούσεις. Χρειάζεται ο έλεγχος να μπει νωρίτερα στα βήματα παραγωγής σεναρίων.")
                    else:
                        pool_sorted = sorted(
                            candidates,
                            key=lambda s: (
                                int(s["total_score"]),
                                int(s.get("broken_friendships", 0)),
                                int(s["diff_population"]),
                                int(s["diff_gender_total"]),
                                int(s["diff_greek"]),
                                str(s["scenario_col"]),
                            )
                        )

                        head = pool_sorted[0]
                        ties = [s for s in pool_sorted if (
                            int(s["total_score"]) == int(head["total_score"]) and
                            int(s.get("broken_friendships", 0)) == int(head.get("broken_friendships", 0)) and
                            int(s["diff_population"]) == int(head["diff_population"]) and
                            int(s["diff_gender_total"]) == int(head["diff_gender_total"]) and
                            int(s["diff_greek"]) == int(head["diff_greek"])
                        )]

                        _rnd.seed(42)
                        best = _rnd.choice(ties) if len(ties) > 1 else head

                        winning_sheet = best["sheet"]
                        winning_col = best["scenario_col"]
                        final_out = ROOT / final_name_all

                        full_df = pd.read_excel(step6_path, sheet_name=winning_sheet).copy()
                        with pd.ExcelWriter(final_out, engine="xlsxwriter") as w:
                            labels = sorted(
                                [str(v) for v in full_df[winning_col].dropna().unique() if re.match(r"^Α\d+$", str(v))],
                                key=lambda x: int(re.search(r"\d+", x).group(0))
                            )
                            for lab in labels:
                                sub = full_df.loc[full_df[winning_col] == lab, ["ΟΝΟΜΑ", winning_col]].copy()
                                sub = sub.rename(columns={winning_col: "ΤΜΗΜΑ"})
                                sub.to_excel(w, index=False, sheet_name=str(lab))

                        st.session_state["last_final_path"] = str(final_out.resolve())
                        st.session_state["last_step6_path"] = str(step6_path)
                        st.session_state["last_winning_sheet"] = str(winning_sheet)
                        st.session_state["last_winning_col"] = str(winning_col)
                        st.session_state["last_input_path"] = str(input_path)  # ΝΕΟ: αποθήκευση input

                        st.success(f"✅ Ολοκληρώθηκε. Νικητής χωρίς δηλωμένες συγκρούσεις: φύλλο {winning_sheet} — στήλη {winning_col}")
                        SHOW_FINAL_DOWNLOAD = False
                        if SHOW_FINAL_DOWNLOAD:
                            st.download_button(
                                "⬇️ Κατέβασε Τελικό Αποτέλεσμα (1→7)",
                                data=_read_file_bytes(final_out),
                                file_name=final_out.name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                use_container_width=True
                            )
                        st.caption("ℹ️ Το αρχείο αποθηκεύτηκε και θα χρησιμοποιηθεί **αυτόματα** από τα «📊 Στατιστικά».")
        except Exception as e:
            st.exception(e)

st.divider()

def _find_latest_final_path() -> Path | None:
    p = st.session_state.get("last_final_path")
    if p and Path(p).exists():
        return Path(p)
    return None

xl = None
st.header("📊 Στατιστικά τμημάτων")

final_path = _find_latest_final_path()
if not final_path:
    st.warning("Δεν βρέθηκε αρχείο Βήματος 7. Πρώτα τρέξε «ΕΚΤΕΛΕΣΗ ΚΑΤΑΝΟΜΗΣ».")
else:
    try:
        xl = pd.ExcelFile(final_path)
        sheets = xl.sheet_names
        st.success(f"✅ Βρέθηκε: **{final_path.name}** | Sheets: {', '.join(sheets)}")
    except Exception as e:
        xl = None
        st.error(f"❌ Σφάλμα ανάγνωσης: {e}")

if xl is not None:
    used_df = None
    if "FINAL_SCENARIO" in sheets:
        used_df = xl.parse("FINAL_SCENARIO")
        scen_cols = [c for c in used_df.columns if re.match(r"^ΒΗΜΑ6_ΣΕΝΑΡΙΟ_\d+$", str(c))]
        if len(scen_cols) != 1:
            st.error("❌ Απαιτείται **ακριβώς μία** στήλη `ΒΗΜΑ6_ΣΕΝΑΡΙΟ_N` στο FINAL_SCENARIO.")
            used_df = None
        else:
            used_df["ΤΜΗΜΑ"] = used_df[scen_cols[0]].astype(str).str.strip()

    if used_df is None:
        class_sheets = [s for s in sheets if re.match(r"^Α\d+$", str(s))]
        if not class_sheets:
            st.error("❌ Δεν βρέθηκε ούτε 'FINAL_SCENARIO' ούτε φύλλα τύπου Α1, Α2, ...")
        else:
            frames = []
            for sh in class_sheets:
                df_sh = xl.parse(sh).copy()
                if "ΤΜΗΜΑ" not in df_sh.columns:
                    df_sh["ΤΜΗΜΑ"] = str(sh)
                keep_cols = [c for c in ["ΟΝΟΜΑ","ΤΜΗΜΑ"] if c in df_sh.columns]
                frames.append(df_sh[keep_cols])
            used_df = pd.concat(frames, axis=0, ignore_index=True)

            step6_path = st.session_state.get("last_step6_path")
            win_sheet = st.session_state.get("last_winning_sheet")
            win_col = st.session_state.get("last_winning_col")
            if step6_path and win_sheet and Path(step6_path).exists():
                try:
                    base_df = pd.read_excel(step6_path, sheet_name=win_sheet).copy()
                    def _canon_name_for_merge(s: str) -> str:
                        s = unicodedata.normalize("NFKC", str(s)).strip().lower()
                        s = re.sub(r"\s+", " ", s)
                        return s
                    used_df["__C"] = used_df["ΟΝΟΜΑ"].map(_canon_name_for_merge)
                    if "ΟΝΟΜΑ" in base_df.columns:
                        base_df["__C"] = base_df["ΟΝΟΜΑ"].map(_canon_name_for_merge)
                        class_by_name = dict(zip(used_df["__C"], used_df["ΤΜΗΜΑ"]))
                        base_df["ΤΜΗΜΑ"] = base_df["__C"].map(class_by_name)
                        used_df = base_df[base_df["ΤΜΗΜΑ"].notna()].drop(columns=["__C"])
                except Exception as _e:
                    st.info(f"⚠️ Δεν κατέστη δυνατός ο εμπλουτισμός από Βήμα 6 ({_e}). Θα χρησιμοποιηθούν μόνο ΟΝΟΜΑ/ΤΜΗΜΑ.")

    def auto_rename_columns(df: pd.DataFrame):
        mapping = {}
        if "ΦΙΛΟΙ" not in df.columns:
            for c in df.columns:
                if "ΦΙΛ" in str(c).upper():
                    mapping[c] = "ΦΙΛΟΙ"
                    break
        if "ΣΥΓΚΡΟΥΣΗ" not in df.columns and "ΣΥΓΚΡΟΥΣΕΙΣ" in df.columns:
            mapping["ΣΥΓΚΡΟΥΣΕΙΣ"] = "ΣΥΓΚΡΟΥΣΗ"
        return df.rename(columns=mapping), mapping
    
    used_df, rename_map = auto_rename_columns(used_df)

    def _strip_diacritics(s: str) -> str:
        nfkd = unicodedata.normalize("NFD", s)
        return "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    
    def _canon_name(s: str) -> str:
        s = (str(s) if s is not None else "").strip()
        s = s.strip("[]'\" ")
        s = re.sub(r"\s+", " ", s)
        s = _strip_diacritics(s).upper()
        return s
    
    def _tokenize_name(canon: str):
        return [t for t in re.split(r"[^A-Z0-9]+", canon) if t]
    
    def _best_name_match(target_canon: str, candidates: list[str]) -> str | None:
        if target_canon in candidates:
            return target_canon
        tks = set(_tokenize_name(target_canon))
        if not tks:
            return None
        best = None; best_score = 0.0
        for c in candidates:
            cks = set(_tokenize_name(c))
            if not cks:
                continue
            inter = tks & cks
            jacc = len(inter) / max(1, len(tks | cks))
            prefix = any(c.startswith(tok) or target_canon.startswith(tok) for tok in inter) if inter else False
            score = jacc + (0.2 if prefix else 0.0)
            if score > best_score:
                best = c; best_score = score
        if best_score >= 0.34:
            return best
        return None

    def compute_conflict_counts_and_names(df: pd.DataFrame):
        if "ΟΝΟΜΑ" not in df.columns or "ΤΜΗΜΑ" not in df.columns:
            return pd.Series([0]*len(df), index=df.index), pd.Series([""]*len(df), index=df.index)
        if "ΣΥΓΚΡΟΥΣΗ" not in df.columns:
            return pd.Series([0]*len(df), index=df.index), pd.Series([""]*len(df), index=df.index)
        df = df.copy()
        df["__C"] = df["ΟΝΟΜΑ"].map(_canon_name)
        cls = df["ΤΜΗΜΑ"].astype(str).str.strip()
        canon_names = list(df["__C"].astype(str).unique())
        index_by = {cn: i for i, cn in enumerate(df["__C"])}
        def parse_targets(cell):
            raw = str(cell) if cell is not None else ""
            parts = [p.strip() for p in re.split(r"[;,/|\n]", raw) if p.strip()]
            return [_canon_name(p) for p in parts]
        counts = [0]*len(df); names = [""]*len(df)
        for i, row in df.iterrows():
            my_class = cls.iloc[i]
            targets = parse_targets(row.get("ΣΥΓΚΡΟΥΣΗ",""))
            same = []
            for t in targets:
                j = index_by.get(t)
                if j is None:
                    match = _best_name_match(t, canon_names)
                    j = index_by.get(match) if match else None
                if j is not None and cls.iloc[j] == my_class and df.loc[i, "__C"] != df.loc[j, "__C"]:
                    same.append(df.loc[j, "ΟΝΟΜΑ"])
            counts[i] = len(same)
            names[i] = ", ".join(same)
        return pd.Series(counts, index=df.index), pd.Series(names, index=df.index)

    def list_broken_mutual_pairs(df: pd.DataFrame) -> pd.DataFrame:
        fcol = next((c for c in ["ΦΙΛΟΙ","ΦΙΛΟΣ","ΦΙΛΙΑ"] if c in df.columns), None)
        if fcol is None or "ΟΝΟΜΑ" not in df.columns or "ΤΜΗΜΑ" not in df.columns:
            return pd.DataFrame(columns=["A","A_ΤΜΗΜΑ","B","B_ΤΜΗΜΑ"])
        df = df.copy()
        df["__C"] = df["ΟΝΟΜΑ"].map(_canon_name)
        name_to_original = dict(zip(df["__C"], df["ΟΝΟΜΑ"].astype(str)))
        class_by_name = dict(zip(df["__C"], df["ΤΜΗΜΑ"].astype(str).str.strip()))
        canon_names = list(df["__C"].astype(str).unique())
        def parse_list(cell):
            raw = str(cell) if cell is not None else ""
            parts = [p.strip() for p in re.split(r"[;,/|\n]", raw) if p.strip()]
            return [_canon_name(p) for p in parts]
        friends_map = {}
        for i, cn in enumerate(df["__C"]):
            raw_targets = parse_list(df.loc[i, fcol])
            resolved = []
            for t in raw_targets:
                if t in canon_names:
                    resolved.append(t)
                else:
                    match = _best_name_match(t, canon_names)
                    if match:
                        resolved.append(match)
            friends_map[cn] = set(resolved)
        rows = []
        for a, fa in friends_map.items():
            for b in fa:
                fb = friends_map.get(b, set())
                if a in fb and class_by_name.get(a) != class_by_name.get(b):
                    rows.append({
                        "A": name_to_original.get(a, a), "A_ΤΜΗΜΑ": class_by_name.get(a,""),
                        "B": name_to_original.get(b, b), "B_ΤΜΗΜΑ": class_by_name.get(b,"")
                    })
        return pd.DataFrame(rows).drop_duplicates()

    def generate_stats(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        if "ΤΜΗΜΑ" in df:
            df["ΤΜΗΜΑ"] = df["ΤΜΗΜΑ"].astype(str).str.strip()
        boys = df[df.get("ΦΥΛΟ","").astype(str).str.upper().eq("Α")].groupby("ΤΜΗΜΑ").size() if "ΦΥΛΟ" in df else pd.Series(dtype=int)
        girls = df[df.get("ΦΥΛΟ","").astype(str).str.upper().eq("Κ")].groupby("ΤΜΗΜΑ").size() if "ΦΥΛΟ" in df else pd.Series(dtype=int)
        edus = df[df.get("ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ","").astype(str).str.upper().eq("Ν")].groupby("ΤΜΗΜΑ").size() if "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ" in df else pd.Series(dtype=int)
        z = df[df.get("ΖΩΗΡΟΣ","").astype(str).str.upper().eq("Ν")].groupby("ΤΜΗΜΑ").size() if "ΖΩΗΡΟΣ" in df else pd.Series(dtype=int)
        id_ = df[df.get("ΙΔΙΑΙΤΕΡΟΤΗΤΑ","").astype(str).str.upper().eq("Ν")].groupby("ΤΜΗΜΑ").size() if "ΙΔΙΑΙΤΕΡΟΤΗΤΑ" in df else pd.Series(dtype=int)
        g = df[df.get("ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","").astype(str).str.upper().eq("Ν")].groupby("ΤΜΗΜΑ").size() if "ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ" in df else pd.Series(dtype=int)
        total = df.groupby("ΤΜΗΜΑ").size() if "ΤΜΗΜΑ" in df else pd.Series(dtype=int)

        try:
            c_counts, _ = compute_conflict_counts_and_names(df)
            cls = df["ΤΜΗΜΑ"].astype(str).str.strip()
            conf_by_class = c_counts.groupby(cls).sum().astype(int)
        except Exception:
            conf_by_class = pd.Series(dtype=int)

        try:
            pairs = list_broken_mutual_pairs(df)
            if pairs.empty:
                broken = pd.Series({tm: 0 for tm in df["ΤΜΗΜΑ"].dropna().astype(str).str.strip().unique()})
            else:
                counts = {}
                for _, row in pairs.iterrows():
                    counts[row["A_ΤΜΗΜΑ"]] = counts.get(row["A_ΤΜΗΜΑ"], 0) + 1
                    counts[row["B_ΤΜΗΜΑ"]] = counts.get(row["B_ΤΜΗΜΑ"], 0) + 1
                broken = pd.Series(counts).astype(int)
        except Exception:
            broken = pd.Series(dtype=int)

        stats = pd.DataFrame({
            "ΑΓΟΡΙΑ": boys,
            "ΚΟΡΙΤΣΙΑ": girls,
            "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ": edus,
            "ΖΩΗΡΟΙ": z,
            "ΙΔΙΑΙΤΕΡΟΤΗΤΑ": id_,
            "ΓΝΩΣΗ ΕΛΛΗΝΙΚΩΝ": g,
            "ΣΥΓΚΡΟΥΣΗ": conf_by_class,
            "ΣΠΑΣΜΕΝΗ ΦΙΛΙΑ": broken,
            "ΣΥΝΟΛΟ ΜΑΘΗΤΩΝ": total,
        }).fillna(0).astype(int)

        try:
            stats = stats.sort_index(key=lambda x: x.str.extract(r"(\d+)")[0].astype(float))
        except Exception:
            stats = stats.sort_index()
        return stats

    def export_stats_to_excel(stats_df: pd.DataFrame) -> BytesIO:
        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            stats_df.to_excel(writer, index=True, sheet_name="Στατιστικά", index_label="ΤΜΗΜΑ")
            wb = writer.book; ws = writer.sheets["Στατιστικά"]
            header_fmt = wb.add_format({"bold": True, "valign":"vcenter", "text_wrap": True, "border":1})
            for col_idx, value in enumerate(["ΤΜΗΜΑ"] + list(stats_df.columns)):
                ws.write(0, col_idx, value, header_fmt)
            for i in range(0, len(stats_df.columns)+1):
                ws.set_column(i, i, 18)
        output.seek(0)
        return output

    tab1, tab2, tab3 = st.tabs([
        "📊 Στατιστικά (1 sheet)",
        "❌ Σπασμένες αμοιβαίες (όλα τα sheets) — Έξοδος: Πλήρες αντίγραφο + Σύνοψη",
        "⚠️ Μαθητές με σύγκρουση στην ίδια τάξη",
    ])

    with tab1:
        st.subheader("📈 Υπολογισμός Στατιστικών για Επιλεγμένο Sheet")
        st.selectbox("Διάλεξε sheet", ["FINAL_SCENARIO"], key="sheet_choice", index=0)
        with st.expander("🔎 Διάγνωση/Μετονομασίες", expanded=False):
            st.write("Αυτόματες μετονομασίες:", rename_map if rename_map else "—")
            required_cols = ["ΟΝΟΜΑ","ΦΥΛΟ","ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ","ΖΩΗΡΟΣ","ΙΔΙΑΙΤΕΡΟΤΗΤΑ","ΚΑΛΗ_ΓΝΩΣΗ_ΕΛΛΗΝΙΚΩΝ","ΦΙΛΟΙ","ΣΥΓΚΡΟΥΣΗ",]
            missing_cols = [c for c in required_cols if c not in used_df.columns]
            st.write("Λείπουν στήλες:", missing_cols if missing_cols else "—")
        if missing_cols:
            st.info("Συμπλήρωσε/διόρθωσε τις στήλες που λείπουν στο Excel και ξαναφόρτωσέ το.")
        stats_df = generate_stats(used_df)
        stats_display = stats_df[[
            "ΠΑΙΔΙ_ΕΚΠΑΙΔΕΥΤΙΚΟΥ",
            "ΖΩΗΡΟΙ",
            "ΙΔΙΑΙΤΕΡΟΤΗΤΑ",
            "ΣΥΓΚΡΟΥΣΗ",
            "ΣΠΑΣΜΕΝΗ ΦΙΛΙΑ",
        ]]
        st.dataframe(stats_display, use_container_width=True)

        if SHOW_STATS_EXPORT_BUTTON:
            st.download_button(
                "📥 Εξαγωγή ΜΟΝΟ Στατιστικών (Excel)",
                data=export_stats_to_excel(stats_df).getvalue(),
                file_name=f"statistika_STEP7_FINAL_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary"
            )

    with tab2:
        st.subheader("💔 Σπασμένες αμοιβαίες φιλίες")
        pairs = list_broken_mutual_pairs(used_df)
        if pairs.empty:
            st.success("Δεν βρέθηκαν σπασμένες αμοιβαίες φιλίες.")
        else:
            st.dataframe(pairs, use_container_width=True)
            counts = {}
            for _, row in pairs.iterrows():
                counts[row["A_ΤΜΗΜΑ"]] = counts.get(row["A_ΤΜΗΜΑ"], 0) + 1
                counts[row["B_ΤΜΗΜΑ"]] = counts.get(row["B_ΤΜΗΜΑ"], 0) + 1
            summary = pd.DataFrame.from_dict(counts, orient="index", columns=["Σπασμένες Αμοιβαίες"]).sort_index()
            st.write("Σύνοψη ανά τμήμα:")
            st.dataframe(summary, use_container_width=True)

    with tab3:
        st.subheader("⚠️ Μαθητές με σύγκρουση στην ίδια τάξη")
        counts, names = compute_conflict_counts_and_names(used_df)
        conflict_students = used_df.copy()
        conflict_students["ΣΥΓΚΡΟΥΣΗ_ΠΛΗΘΟΣ"] = counts.astype(int)
        conflict_students["ΣΥΓΚΡΟΥΣΗ_ΟΝΟΜΑ"] = names
        conflict_students = conflict_students.loc[conflict_students["ΣΥΓΚΡΟΥΣΗ_ΠΛΗΘΟΣ"] > 0, ["ΟΝΟΜΑ","ΤΜΗΜΑ","ΣΥΓΚΡΟΥΣΗ_ΠΛΗΘΟΣ","ΣΥΓΚΡΟΥΣΗ_ΟΝΟΜΑ"]]
        if conflict_students.empty:
            st.success("Δεν βρέθηκαν συγκρούσεις εντός της ίδιας τάξης.")
        else:
            st.dataframe(conflict_students.sort_values(["ΤΜΗΜΑ","ΟΝΟΜΑ"]), use_container_width=True)

st.divider()

# ---------------------------
# 🎯 ΝΕΟ ΚΟΥΜΠΙ: Βέλτιστη Κατανομή (ΒΗΜΑ 8)
# ---------------------------
if st.session_state.get("last_final_path"):
    st.header("🎯 Βέλτιστη Κατανομή")
    st.write("Εφαρμογή **Βήματος 8**: Βελτιστοποίηση με asymmetric swaps για ισοκατανομή επίδοσης, φύλου και γνώσης ελληνικών.")
    
    if st.button("🎯 Βέλτιστη Κατανομή", type="primary", use_container_width=True, key="run_step8"):
        try:
            # Έλεγχος απαραίτητων αρχείων
            input_source = st.session_state.get("last_input_path")
            template_path = st.session_state.get("last_final_path")
            
            if not input_source or not Path(input_source).exists():
                st.error("❌ Δεν βρέθηκε το αρχικό αρχείο εισόδου. Τρέξε πρώτα 'ΕΚΤΕΛΕΣΗ ΚΑΤΑΝΟΜΗΣ'.")
            elif not template_path or not Path(template_path).exists():
                st.error("❌ Δεν βρέθηκε το STEP7 template. Τρέξε πρώτα 'ΕΚΤΕΛΕΣΗ ΚΑΤΑΝΟΜΗΣ'.")
            else:
                st.info(f"📂 Source: {Path(input_source).name}")
                st.info(f"📂 Template: {Path(template_path).name}")
                
                # Load step8 module
                s8 = _load_module("step8_fixed_final", ROOT / "step8_fixed_final.py")
                
                processor = s8.UnifiedProcessor()
                
                # Phase 1: Fill
                with st.spinner("📋 Phase 1/2: Filling template..."):
                    processor.read_source_data(str(input_source))
                    temp_filled = ROOT / _timestamped("STEP8_TEMP_FILLED", ".xlsx")
                    processor.fill_target_excel(str(template_path), str(temp_filled))
                    st.success(f"✅ Phase 1 ολοκληρώθηκε: {len(processor.students_data)} μαθητές")
                
                # Phase 2: Optimize
                with st.spinner("🎯 Phase 2/2: Optimizing..."):
                    processor.load_filled_data(str(temp_filled))
                    
                    spreads_before = processor.calculate_spreads()
                    st.write("**📊 ΠΡΙΝ την βελτιστοποίηση:**")
                    st.write(f"- EP3 spread: {spreads_before['ep3']}")
                    st.write(f"- Boys spread: {spreads_before['boys']}")
                    st.write(f"- Girls spread: {spreads_before['girls']}")
                    st.write(f"- Greek spread: {spreads_before['greek_yes']}")
                    
                    swaps, spreads_after = processor.optimize(max_iterations=100)
                    
                    st.write("**📊 ΜΕΤΑ τη βελτιστοποίηση:**")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("EP3 spread", spreads_after['ep3'], 
                                 delta=spreads_after['ep3'] - spreads_before['ep3'],
                                 delta_color="inverse")
                    with col2:
                        st.metric("Boys spread", spreads_after['boys'],
                                 delta=spreads_after['boys'] - spreads_before['boys'],
                                 delta_color="inverse")
                    with col3:
                        st.metric("Girls spread", spreads_after['girls'],
                                 delta=spreads_after['girls'] - spreads_before['girls'],
                                 delta_color="inverse")
                    with col4:
                        st.metric("Greek spread", spreads_after['greek_yes'],
                                 delta=spreads_after['greek_yes'] - spreads_before['greek_yes'],
                                 delta_color="inverse")
                    
                    # Export
                    final_optimized = ROOT / _timestamped("STEP8_OPTIMIZED", ".xlsx")
                    processor.export_optimized_excel(swaps, spreads_after, str(final_optimized))
                    
                    # Cleanup temp
                    temp_filled.unlink(missing_ok=True)
                    
                    st.success(f"🎉 Ολοκληρώθηκε! Συνολικά {len(swaps)} swaps εφαρμόστηκαν.")
                    
                    # Display warnings
                    if processor.warnings:
                        with st.expander(f"⚠️ {len(processor.warnings)} warnings", expanded=False):
                            for w in processor.warnings[:20]:
                                st.caption(w)
                    
                    # 🎈 CELEBRATION - Built-in Streamlit balloons
                    st.balloons()
                    
                    # 🎊 EXTRA CELEBRATION ANIMATION με JavaScript
                    st.components.v1.html("""
<div id="celebration-container"></div>
<style>
@keyframes balloon-rise {
  0% { transform: translateY(0) rotate(0deg); opacity: 1; }
  100% { transform: translateY(-1000px) rotate(360deg); opacity: 0; }
}
@keyframes confetti-drop {
  0% { transform: translateY(-100px) rotate(0deg); opacity: 1; }
  100% { transform: translateY(1000px) rotate(720deg); opacity: 0; }
}
.balloon-element {
  position: fixed;
  width: 40px;
  height: 50px;
  border-radius: 50% 50% 50% 50% / 60% 60% 40% 40%;
  animation: balloon-rise 8s ease-out forwards;
  z-index: 99999;
}
.confetti-element {
  position: fixed;
  animation: confetti-drop 6s linear forwards;
  z-index: 99999;
}
</style>
<script>
(function() {
  const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#FFA07A', '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E2'];
  const container = document.getElementById('celebration-container');
  
  for (let i = 0; i < 15; i++) {
    const balloon = document.createElement('div');
    balloon.className = 'balloon-element';
    balloon.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    balloon.style.left = Math.random() * 90 + 5 + '%';
    balloon.style.bottom = '-60px';
    balloon.style.animationDelay = Math.random() * 2 + 's';
    document.body.appendChild(balloon);
    setTimeout(() => balloon.remove(), 9000);
  }
  
  for (let i = 0; i < 40; i++) {
    const confetti = document.createElement('div');
    confetti.className = 'confetti-element';
    const size = Math.random() * 10 + 8 + 'px';
    confetti.style.width = size;
    confetti.style.height = size;
    confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    confetti.style.left = Math.random() * 100 + '%';
    confetti.style.top = '-20px';
    confetti.style.animationDelay = Math.random() * 1.5 + 's';
    document.body.appendChild(confetti);
    setTimeout(() => confetti.remove(), 7000);
  }
})();
</script>
""", height=0)
                    
                    # Download button
                    st.download_button(
                        "⬇️ Κατέβασε ΒΕΛΤΙΣΤΟΠΟΙΗΜΕΝΟ Αποτέλεσμα (Βήμα 8)",
                        data=_read_file_bytes(final_optimized),
                        file_name=final_optimized.name,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="dl_step8"
                    )
                    
        except Exception as e:
            st.exception(e)

st.divider()

# ---------------------------
# ♻️ Επανεκκίνηση (μία και καλή)
# ---------------------------
st.header("♻️ Επανεκκίνηση")
st.write("Καθαρίζει προσωρινά δεδομένα και ξαναφορτώνει το app.")
if st.button("♻️ Επανεκκίνηση τώρα", type="secondary", use_container_width=True, key="restart_btn"):
    _restart_app()

st.divider()
