"""
Ribbed slab design - Streamlit app
Run:  streamlit run app.py
"""
import base64
import datetime
import json
import os
import tempfile
import zlib

import streamlit as st

import ribbed_slab as rs

st.set_page_config(page_title="Ribbed Slab Design", page_icon=None, layout="wide")

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, "logo.png")
S = st.session_state

# ------------------------------------------------------------------ save / reopen a project
def _decode_token(tok):
    try:
        pad = "=" * (-len(tok) % 4)
        return json.loads(zlib.decompress(base64.urlsafe_b64decode(tok + pad)).decode())
    except Exception:
        return {}


def _encode_token(d):
    return base64.urlsafe_b64encode(zlib.compress(json.dumps(d).encode(), 9)).decode().rstrip("=")


if "_loaded" not in S:
    tok = st.query_params.get("p", "")
    S["_loaded"] = _decode_token(tok) if tok else {}
S["_reg"] = {}


def w(kind, label, key, default, **kw):
    """Widget wrapper: remembers every value so the project can be saved and reopened."""
    val = S["_loaded"].get(key, default)
    if kind == "text":
        out = st.text_input(label, value=str(val), key=key, **kw)
    elif kind == "num":
        typ = type(default)
        try:
            val = typ(val)
        except Exception:
            val = default
        out = st.number_input(label, value=val, key=key, **kw)
    elif kind == "check":
        out = st.checkbox(label, value=bool(val), key=key, **kw)
    else:  # select
        opts = kw.pop("options")
        idx = opts.index(val) if val in opts else opts.index(default)
        out = st.selectbox(label, opts, index=idx, key=key, **kw)
    S["_reg"][key] = out
    return out


# ------------------------------------------------------------------ header
c1, c2 = st.columns([1, 5])
with c1:
    if os.path.exists(LOGO):
        st.image(LOGO, width=180)
with c2:
    st.title("Ribbed Slab Design")
    st.caption("One-way ribbed slab, single-span rib - BS 8110-1:1997. Change any input and the whole design updates.")

# ------------------------------------------------------------------ 1. project
st.header("Step 1 - Project information")
a, b, c = st.columns(3)
with a:
    firm = w("text", "Firm name", "firm", "INFRAS ENGINEERING SOLUTIONS")
    address = w("text", "Address", "addr", "P.O Box 45297-00100 Nairobi")
    tel = w("text", "Tel", "tel", "+254 723703705")
    email = w("text", "Email", "email", "info@infrasengineering.com")
with b:
    title = w("text", "Project", "ptitle", "")
    job = w("text", "Job No.", "job", "")
    designer = w("text", "Designed by", "designer", "")
    checked = w("text", "Checked by", "checked", "")
with c:
    element = w("text", "Element", "element", "Roof terrace ribbed slab (+9000)")
    panel = w("text", "Panel", "panel", "Panel 1")
    grids = w("text", "Between grids", "grids", "")
    date = w("text", "Date", "date", datetime.date.today().strftime("%d/%m/%Y"))

# ------------------------------------------------------------------ 2. geometry
st.header("Step 2 - Slab geometry")
a, b, c = st.columns(3)
with a:
    st.subheader("Rib span")
    clear = w("num", "Clear span (mm)", "clear", 6600.0, step=50.0)
    wa = w("num", "Support A width (mm)", "wa", 200.0, step=25.0)
    wb = w("num", "Support B width (mm)", "wb", 200.0, step=25.0)
    st.caption(f"Effective span L = clear + half of each support = {(clear + (wa + wb) / 2):.0f} mm")
    st.subheader("Panel (for the plan sketch)")
    pw = w("num", "Panel width across the ribs (m)", "pw", 7.4, step=0.1)
    adj = w("check", "Adjacent panel shown", "adj", True)
    aw = w("num", "Adjacent panel width (m)", "aw", 3.2, step=0.1) if adj else 3.2
    ad = w("num", "Adjacent panel length along ribs (m)", "ad", 3.2, step=0.1) if adj else 3.2
with b:
    st.subheader("Section")
    top = w("num", "Topping thickness (mm)", "top", 100.0, step=5.0)
    rd = w("num", "Rib depth below topping (mm)", "rd", 200.0, step=25.0)
    rw = w("num", "Rib width (mm)", "rw", 150.0, step=5.0)
    bkw = w("num", "Hollow block width, across ribs (mm)", "bkw", 375.0, step=5.0)
    bkl = w("num", "Hollow block length, along ribs (mm)", "bkl", 225.0, step=5.0)
    st.caption(f"Overall depth H = {top + rd:.0f} mm;  rib spacing (bf) = {rw + bkw:.0f} mm")
with c:
    st.subheader("Blocks and ribs per m\u00b2")
    rpm = w("num", "Ribs per metre", "rpm", 2, step=1, min_value=1)
    bal = w("num", "Blocks along 1 m", "bal", 5, step=1, min_value=1)
    bac = w("num", "Blocks across 1 m", "bac", 2, step=1, min_value=1)
    bkg = w("num", f"Weight of one {rd:.0f} mm block (kg)", f"bkg_{rd:.0f}", round(0.1025 * rd * 2) / 2.0, step=0.5)
    st.caption("Default weight is only an estimate (15.5 kg at 150 mm, 20.5 kg at 200 mm). "
               "Enter the supplier's figure.")

# ------------------------------------------------------------------ 3. loading
st.header("Step 3 - Loading")
a, b, c = st.columns(3)
with a:
    plabel = w("text", "Other dead load - description", "plabel", "Partitions / Solar panels")
    pload = w("num", "Other dead load (kN/m\u00b2)", "pload", 0.12, step=0.01)
with b:
    fin = w("select", "Finishes", "fin", "Open areas (APP & interlocking blocks)", options=list(rs.FINISHES_OPTIONS))
    fval = rs.FINISHES_OPTIONS[fin]
    if fval is None:
        fval = w("num", "Finishes (kN/m\u00b2)", "fin_c", 2.5, step=0.1)
with c:
    liv = w("select", "Live load", "liv", "Open areas - water tanks (BS 6399-1 Table 1)", options=list(rs.LIVE_OPTIONS))
    lval = rs.LIVE_OPTIONS[liv]
    if lval is None:
        lval = w("num", "Live load (kN/m\u00b2)", "liv_c", 5.0, step=0.1)
a, b, c = st.columns(3)
with a:
    gam_c = w("num", "Concrete density (kN/m\u00b3)", "gc", 24.0, step=0.5)
with b:
    gg = w("num", "Dead load factor", "gg", 1.4, step=0.05)
with c:
    gq = w("num", "Live load factor", "gq", 1.6, step=0.05)

# ------------------------------------------------------------------ 4. materials and design basis
st.header("Step 4 - Materials, reinforcement and design basis")
a, b, c = st.columns(3)
with a:
    st.subheader("Materials")
    fcu = w("select", "Concrete grade fcu (N/mm\u00b2)", "fcu", 25, options=rs.CONCRETE_GRADES)
    fy = w("select", "Main steel fy (N/mm\u00b2)", "fy", 460, options=rs.STEEL_GRADES)
    fyv = w("select", "Link steel fyv (N/mm\u00b2)", "fyv", 460, options=rs.LINK_STEEL_GRADES)
    cover = w("num", "Cover (mm)", "cover", 25.0, step=5.0)
    phi = w("num", "Bar diameter assumed for d (mm)", "phi", 16.0, step=2.0)
with b:
    st.subheader("Reinforcement")
    md = w("select", "Midspan bottom bar diameter", "md", 12, options=rs.BAR_DIAS)
    omid = w("num", "Bottom bars per rib (0 = automatic)", "omid", 0, step=1, min_value=0)
    sd = w("select", "Support top bar diameter", "sd", 12, options=rs.BAR_DIAS)
    osp = w("num", "Support bar spacing (0 = automatic)", "osp", 0, step=25, min_value=0)
    ld = w("select", "Link diameter", "ld", 8, options=rs.LINK_DIAS)
    legs = w("num", "Link legs", "legs", 2, step=1, min_value=2)
    mesh = w("select", "Topping mesh", "mesh", "A142", options=rs.MESH_OPTIONS)
with c:
    st.subheader("Analysis and checks")
    cref = w("text", "Coefficient table reference", "cref", "BS 8110-1:1997 Table 3.12")
    cs = w("num", "Support moment coefficient (x FL)", "cs", 0.086, step=0.001, format="%.3f")
    cm = w("num", "Midspan moment coefficient (x FL)", "cm", 0.063, step=0.001, format="%.3f")
    sa = w("num", "Shear coefficient at A (x F)", "sa", 0.6, step=0.01)
    sb = w("num", "Shear coefficient at B (x F)", "sb", 0.6, step=0.01)
    cond = w("select", "Span condition for deflection", "cond", "Continuous", options=list(rs.SUPPORT_CONDITIONS))
    sbasis = w("select", "Steel used for vc", "sbasis", rs.SHEAR_STEEL_BASIS[0], options=rs.SHEAR_STEEL_BASIS)
    lrule = w("select", "Maximum link spacing", "lrule", rs.LINK_SPACING_RULES[0], options=rs.LINK_SPACING_RULES)

slab = rs.RibbedSlab(
    clear_span_mm=clear, support_a_mm=wa, support_b_mm=wb, panel_width_m=pw, has_adjacent=adj,
    adj_width_m=aw, adj_depth_m=ad, topping_mm=top, rib_depth_mm=rd, rib_width_mm=rw,
    block_width_mm=bkw, block_length_mm=bkl, ribs_per_m=int(rpm), blocks_along=int(bal),
    blocks_across=int(bac), block_kg=bkg, partition_label=plabel, partition_kNm2=pload,
    finishes_kNm2=fval, live_kNm2=lval, live_label=liv.split(" (")[0].split(" - ")[-1],
    concrete_density=gam_c, gamma_g=gg, gamma_q=gq, fcu=int(fcu), fy=int(fy), fyv=int(fyv),
    cover_mm=cover, phi_assumed_mm=phi, mid_dia=int(md), sup_dia=int(sd), link_dia=int(ld),
    link_legs=int(legs), mesh=mesh, override_mid_bars=int(omid), override_sup_spacing=int(osp),
    coeff_ref=cref, c_support=cs, c_mid=cm, c_shear_a=sa, c_shear_b=sb, support_condition=cond,
    shear_basis=sbasis, link_rule=lrule)
project = rs.ProjectInfo(
    firm_name=firm, address=address, tel=tel, email=email, logo_path=LOGO, project_title=title,
    job_no=job, designer=designer, checked_by=checked, date=date, element=element,
    panel_name=panel, grids=grids)

# ------------------------------------------------------------------ 5. results
st.header("Step 5 - Design results")
try:
    r = rs.analyse(slab)
except ValueError as e:
    st.error(str(e))
    st.stop()

for msg in r["warnings"]:
    st.warning(msg)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Design load n", f"{r['n']:.2f} kN/m\u00b2")
m2.metric("Load on span F", f"{r['F']:.2f} kN")
m3.metric("Moment at B / C", f"{r['Msup']:.2f} / {r['Mmid']:.2f} kN.m")
m4.metric("Shear at A / B", f"{r['VA']:.2f} / {r['VB']:.2f} kN")

t1, t2 = st.columns(2)
with t1:
    st.subheader("Reinforcement")
    st.table({
        "Item": ["Midspan bottom (per rib)", "Support top (per metre)", "Links", "Topping mesh", "Overall depth"],
        "Provide": [
            f"{r['n_mid']}Y{slab.mid_dia}  ({r['As_mid_prov']} mm\u00b2, req. {r['mid']['As']:.2f})",
            f"Y{slab.sup_dia}@{r['sp']}  ({r['As_m_prov']} mm\u00b2/m, req. {r['As_m_req']:.2f})",
            "None required" if r["case"] == "none" else f"Y{slab.link_dia} @ {r['sv_prov']}",
            f"{slab.mesh} BRC",
            f"{r['h']:.0f} mm ({slab.topping_mm:.0f} + {slab.rib_depth_mm:.0f})"],
    })
with t2:
    st.subheader("Checks")
    st.table({
        "Check": ["Loading Gk / Qk", "Midspan K", "Support K", "Shear v / vc", "Deflection span/d (allow / actual)",
                  "Equivalent slab depth"],
        "Result": [f"{r['Gk']:.2f} / {r['Qk']:.2f} kN/m\u00b2", f"{r['mid']['K']:.4f}",
                   f"{r['sup']['K']:.4f}" + ("  (compression steel)" if r["sup"]["comp"] else ""),
                   f"{r['v']:.3f} / {r['vc']:.2f} N/mm\u00b2",
                   f"{r['allow']:.2f} / {r['actual']:.2f}  " + ("OK" if r["defl_ok"] else "FAIL"),
                   f"{r['eq']:.0f} mm  (\u2248 {r['eq_round']:.0f} mm)"],
    })

with st.expander("Sketches", expanded=False):
    k1, k2 = st.columns(2)
    k1.pyplot(rs.figure_of(lambda a: rs.draw_plan(a, slab, label=panel.upper()), 5, 3.2), width="stretch")
    k2.pyplot(rs.figure_of(lambda a: rs.draw_along(a, slab), 5, 1.6), width="stretch")
    k3, k4, k5 = st.columns(3)
    k3.pyplot(rs.figure_of(lambda a: rs.draw_section(a, slab), 4, 2.4), width="stretch")
    k4.pyplot(rs.figure_of(lambda a: rs.draw_detail(a, slab, r, "mid"), 4, 2.8), width="stretch")
    k5.pyplot(rs.figure_of(lambda a: rs.draw_detail(a, slab, r, "sup"), 4, 2.8), width="stretch")

# ------------------------------------------------------------------ 6. PDF + save
st.header("Step 6 - Calculation sheet")
d1, d2 = st.columns(2)
with d1:
    if st.button("Generate PDF calculation sheet", type="primary"):
        path = os.path.join(tempfile.gettempdir(), project.pdf_filename())
        rs.generate_pdf(slab, project, r, path)
        with open(path, "rb") as f:
            S["_pdf"] = (project.pdf_filename(), f.read())
    if "_pdf" in S:
        st.download_button("Download PDF", S["_pdf"][1], file_name=S["_pdf"][0], mime="application/pdf")
with d2:
    token = _encode_token(S["_reg"])
    st.write("Save this project: bookmark or copy the link below and open it later to restore every input.")
    if st.button("Update project link"):
        st.query_params["p"] = token
    st.code(f"?p={token}", language=None)
