"""
ribbed_slab.py  -  One-way ribbed slab design (single-span rib) to BS 8110-1:1997
-------------------------------------------------------------------------------
Self-contained engine:  inputs  ->  design calculations  ->  sketches  ->  PDF calc sheet.

One continuous design: change the rib depth, topping, bar sizes etc. and the whole
sheet (loads, moments, steel, shear, deflection, sketches) is recalculated.

Intermediate values are carried at the precision that is printed on the sheet
(n, udl, F, M, V, As to 2 d.p.; provided areas to the nearest mm2; lever arm ratio
to 2 d.p.), so every printed line can be reproduced by hand.
"""
from dataclasses import dataclass, field, asdict
import datetime
import math
import re
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.backends.backend_pdf import PdfPages

matplotlib.rcParams["mathtext.default"] = "regular"
matplotlib.rcParams["font.family"] = "DejaVu Sans"

BLUE = "#1F4E78"
RED = "#8B1E2E"
GREY = "#555555"

# ------------------------------------------------------------------ options
CONCRETE_GRADES = [20, 25, 30]              # fcu, N/mm2
STEEL_GRADES = [410, 425, 460, 500]         # fy, N/mm2
LINK_STEEL_GRADES = [250, 410, 425, 460, 500]
BAR_DIAS = [8, 10, 12, 16, 20, 25, 32]
LINK_DIAS = [6, 8, 10, 12]
MESH_OPTIONS = ["A98", "A142", "A193", "A252", "A393"]
SUPPORT_SPACINGS = [300, 250, 225, 200, 175, 150, 125, 100, 75]   # mm, tried largest first

FINISHES_OPTIONS = {
    "Open areas (APP & interlocking blocks)": 2.5,
    "Residential floors": 1.5,
    "Iron sheets": 0.15,
    "Custom": None,
}
LIVE_OPTIONS = {
    "Open areas - water tanks (BS 6399-1 Table 1)": 5.0,
    "Residential": 1.5,
    "Offices": 2.5,
    "Corridors / balconies": 5.0,
    "Roof (iron sheets)": 0.6,
    "Custom": None,
}
# basic span/effective depth: (rectangular, flanged bw/b <= 0.3)  - BS 8110-1 Table 3.9
SUPPORT_CONDITIONS = {
    "Continuous": (26.0, 20.8),
    "Simply supported": (20.0, 16.0),
    "Cantilever": (7.0, 5.6),
}
LINK_SPACING_RULES = ["4 x bw (as hand design)", "0.75 d"]
SHEAR_STEEL_BASIS = ["Support steel per rib", "Support steel per metre (as hand sheet)"]

G_ACC = 10.0       # N/kg, as on the hand sheet
K_LIM = 0.156


def bar_area(dia):
    return math.pi * dia * dia / 4.0


# ------------------------------------------------------------------ inputs
@dataclass
class ProjectInfo:
    firm_name: str = "INFRAS ENGINEERING SOLUTIONS"
    address: str = "P.O Box 45297-00100 Nairobi"
    tel: str = "+254 723703705"
    email: str = "info@infrasengineering.com"
    logo_path: str = "logo.png"
    project_title: str = ""
    job_no: str = ""
    designer: str = ""
    checked_by: str = ""
    date: str = field(default_factory=lambda: datetime.date.today().strftime("%d/%m/%Y"))
    element: str = "Roof terrace ribbed slab"
    panel_name: str = "Panel 1"
    grids: str = ""

    def title(self):
        p = self.panel_name.strip().upper()
        g = re.sub(r"^\s*grids?\s+", "", self.grids.strip(), flags=re.I).upper()
        return " ".join(x for x in [p, f"BETWEEN GRIDS {g}" if g else ""] if x)

    def pdf_filename(self):
        name = re.sub(r'[\\/:*?"<>|]', "-", self.panel_name.strip() or "design")
        return f"Ribbed slab {name}.pdf"


@dataclass
class RibbedSlab:
    # geometry (mm unless stated)
    clear_span_mm: float = 6600.0
    support_a_mm: float = 200.0
    support_b_mm: float = 200.0
    panel_width_m: float = 7.4          # panel width across the ribs (for the plan sketch)
    has_adjacent: bool = True
    adj_width_m: float = 3.2
    adj_depth_m: float = 3.2
    topping_mm: float = 100.0
    rib_depth_mm: float = 200.0
    rib_width_mm: float = 150.0
    block_width_mm: float = 375.0       # across the ribs
    block_length_mm: float = 225.0      # along the ribs
    # blocks / ribs per m2
    ribs_per_m: int = 2
    blocks_along: int = 5
    blocks_across: int = 2
    block_kg: float = 20.5
    # loads
    partition_label: str = "Partitions / Solar panels"
    partition_kNm2: float = 0.12
    finishes_kNm2: float = 2.5
    live_kNm2: float = 5.0
    live_label: str = "Tanks"
    concrete_density: float = 24.0
    gamma_g: float = 1.4
    gamma_q: float = 1.6
    # materials / cover
    fcu: int = 25
    fy: int = 460
    fyv: int = 460
    cover_mm: float = 25.0
    phi_assumed_mm: float = 16.0
    # reinforcement choices
    mid_dia: int = 12
    sup_dia: int = 12
    link_dia: int = 8
    link_legs: int = 2
    mesh: str = "A142"
    override_mid_bars: int = 0          # 0 = automatic
    override_sup_spacing: int = 0       # 0 = automatic
    # analysis coefficients (as used on the hand design)
    coeff_ref: str = "BS 8110-1:1997 Table 3.12"
    c_support: float = 0.086            # hogging moment at B  (x F L)
    c_mid: float = 0.063                # sagging moment at C  (x F L)
    c_shear_a: float = 0.6              # shear at A (x F)
    c_shear_b: float = 0.6              # shear at B (x F)
    # checks
    support_condition: str = "Continuous"
    shear_basis: str = SHEAR_STEEL_BASIS[0]
    link_rule: str = LINK_SPACING_RULES[0]

    @property
    def span_m(self):
        return (self.clear_span_mm + (self.support_a_mm + self.support_b_mm) / 2.0) / 1000.0

    @property
    def bf_mm(self):
        return self.rib_width_mm + self.block_width_mm

    @property
    def h_mm(self):
        return self.topping_mm + self.rib_depth_mm

    @property
    def d_mm(self):
        return self.h_mm - self.cover_mm - self.phi_assumed_mm / 2.0


# ------------------------------------------------------------------ calculations
def _flexure(M, b, d, dp, fcu, fy):
    """M in N.mm. Returns singly / doubly reinforced result (BS 8110 cl 3.4.4.4)."""
    K = M / (fcu * b * d * d)
    if K > 0.225:
        raise ValueError(
            f"K = {K:.3f} is too high - the section is too small. Increase the rib depth or width.")
    if K <= K_LIM:
        zr_raw = 0.5 + math.sqrt(0.25 - K / 0.9)
        zr = min(round(zr_raw, 2), 0.95)
        z = zr * d
        As = round(M / (0.95 * fy * z), 2)
        return dict(K=K, comp=False, zr_raw=zr_raw, zr=zr, z=z, As=As, Asc=0.0, dp=dp)
    zr_raw = 0.5 + math.sqrt(0.25 - K_LIM / 0.9)
    zr = round(zr_raw, 2)
    z = zr * d
    Asc = round((K - K_LIM) * fcu * b * d * d / (0.95 * fy * (d - dp)), 2)
    As = round(K_LIM * fcu * b * d * d / (0.95 * fy * z) + Asc, 2)
    return dict(K=K, comp=True, zr_raw=zr_raw, zr=zr, z=z, As=As, Asc=Asc, dp=dp)


def analyse(s: RibbedSlab) -> dict:
    r = {"warnings": []}
    L = s.span_m
    Lmm = L * 1000.0
    bf, bw, hf, hr, h = s.bf_mm, s.rib_width_mm, s.topping_mm, s.rib_depth_mm, s.h_mm
    d = round(s.d_mm, 1)
    dp = s.cover_mm + s.phi_assumed_mm / 2.0
    if d <= 0 or hf <= 0 or hr <= 0:
        raise ValueError("Check the slab dimensions.")
    r.update(L=L, Lmm=Lmm, bf=bf, bw=bw, hf=hf, hr=hr, h=h, d=d, dp=dp)

    # ---- loading
    top = round(hf / 1000 * s.concrete_density, 2)
    rib_area = bw / 1000 * hr / 1000
    rib_area_m = rib_area * s.ribs_per_m
    rib_sw = round(rib_area_m * s.concrete_density, 2)
    blk_kgm2 = s.blocks_along * s.blocks_across * s.block_kg
    blk = round(blk_kgm2 * G_ACC / 1000.0, 2)
    parts = [("Topping self-weight", top), ("Ribs", rib_sw), ("Hollow blocks", blk),
             (s.partition_label, round(s.partition_kNm2, 2)), ("Finishes", round(s.finishes_kNm2, 2))]
    Gk = round(sum(v for _, v in parts), 2)
    Qk = round(s.live_kNm2, 2)
    n = round(s.gamma_g * Gk + s.gamma_q * Qk, 2)
    udl = round(n * bf / 1000.0, 2)
    F = round(udl * L, 2)
    r.update(top=top, rib_area=rib_area, rib_area_m=rib_area_m, rib_sw=rib_sw, blk_kgm2=blk_kgm2,
             blk=blk, parts=parts, Gk=Gk, Qk=Qk, n=n, udl=udl, F=F)

    # ---- forces
    Msup = round(s.c_support * F * L, 2)
    Mmid = round(s.c_mid * F * L, 2)
    VA = round(s.c_shear_a * F, 2)
    VB = round(s.c_shear_b * F, 2)
    Vmax = max(VA, VB)
    r.update(Msup=Msup, Mmid=Mmid, VA=VA, VB=VB, Vmax=Vmax)

    # ---- midspan (T-section)
    MR = round(0.45 * s.fcu * bf * hf * (d - 0.5 * hf) / 1e6, 2)
    r["MR"] = MR
    if Mmid > MR:
        raise ValueError(
            f"Midspan moment {Mmid} kN.m exceeds the flange capacity {MR} kN.m: the neutral axis falls "
            "below the flange. Increase the topping thickness (T-section design is not covered).")
    mid = _flexure(Mmid * 1e6, bf, d, dp, s.fcu, s.fy)
    a1 = bar_area(s.mid_dia)
    n_mid = s.override_mid_bars if s.override_mid_bars > 0 else max(2, math.ceil(mid["As"] / a1))
    As_mid_prov = round(n_mid * a1)
    r.update(mid=mid, n_mid=n_mid, As_mid_prov=As_mid_prov)
    if mid["comp"]:
        r["warnings"].append("Midspan needs compression steel - increase the rib depth.")
    if As_mid_prov < mid["As"]:
        r["warnings"].append("Bottom bars provided are less than required.")
    clear_gap = bw - 2 * (s.cover_mm + s.link_dia) - n_mid * s.mid_dia
    if n_mid > 1 and clear_gap / (n_mid - 1) < max(s.mid_dia, 20):
        r["warnings"].append(f"{n_mid}Y{s.mid_dia} will not fit comfortably in a {bw:.0f} mm rib - "
                             "use fewer / smaller bars or a wider rib.")

    # ---- support (rectangular, b = bw)
    sup = _flexure(Msup * 1e6, bw, d, dp, s.fcu, s.fy)
    As_m_req = round(sup["As"] * 1000.0 / bf, 2)
    a2 = bar_area(s.sup_dia)
    if s.override_sup_spacing > 0:
        sp = s.override_sup_spacing
    else:
        sp = next((x for x in SUPPORT_SPACINGS if 1000.0 / x * a2 >= As_m_req), None)
        if sp is None:
            sp = SUPPORT_SPACINGS[-1]
            r["warnings"].append("Support bars are too small even at 75 mm spacing - use a larger diameter.")
    As_m_prov = round(1000.0 / sp * a2)
    As_rib_prov = As_m_prov * bf / 1000.0
    r.update(sup=sup, As_m_req=As_m_req, sp=sp, As_m_prov=As_m_prov, As_rib_prov=As_rib_prov)
    if As_m_prov < As_m_req:
        r["warnings"].append("Top bars at the support are less than required.")
    if sup["comp"]:
        r["sup_comp_ok"] = As_mid_prov >= sup["Asc"]
        if not r["sup_comp_ok"]:
            r["warnings"].append("Bottom bars are less than the compression steel needed at the support.")

    # ---- shear
    v = round(Vmax * 1000.0 / (bw * d), 3)
    v_lim = min(0.8 * math.sqrt(s.fcu), 5.0)
    As_sh = As_m_prov if s.shear_basis == SHEAR_STEEL_BASIS[1] else As_rib_prov
    rho = min(100.0 * As_sh / (bw * d), 3.0)
    f_rho = rho ** (1 / 3)
    f_d = max(400.0 / d, 1.0) ** 0.25
    f_fcu = (s.fcu / 25.0) ** (1 / 3) if s.fcu > 25 else 1.0
    vc = 0.79 * f_rho * f_d * f_fcu / 1.25
    Asv = round(s.link_legs * bar_area(s.link_dia))
    sv_lim = 4 * bw if s.link_rule == LINK_SPACING_RULES[0] else 0.75 * d
    if v > v_lim:
        raise ValueError(f"Shear stress {v:.2f} N/mm2 exceeds the maximum {v_lim:.2f} N/mm2 - enlarge the ribs.")
    if v < 0.5 * vc:
        case, sv_req, sv_prov = "none", None, None
    else:
        if v <= vc + 0.4:
            case = "minimal"
            sv_req = Asv * 0.95 * s.fyv / (0.4 * bw)
        else:
            case = "design"
            sv_req = Asv * 0.95 * s.fyv / (bw * (v - vc))
        sv_prov = max(25, int(min(sv_req, sv_lim) // 25 * 25))
    r.update(v=v, v_lim=v_lim, As_sh=As_sh, rho=rho, f_rho=f_rho, f_d=f_d, f_fcu=f_fcu, vc=vc,
             Asv=Asv, sv_lim=sv_lim, case=case, sv_req=sv_req, sv_prov=sv_prov)
    if case == "design":
        r["warnings"].append("Shear links are designed (v > vc + 0.4) - check the spacing and bar fit.")

    # ---- deflection
    ratio = bw / bf
    rect, flg = SUPPORT_CONDITIONS[s.support_condition]
    if ratio <= 0.3:
        basic = flg
    elif ratio >= 1.0:
        basic = rect
    else:
        basic = flg + (rect - flg) * (ratio - 0.3) / 0.7
    M_bd2 = Mmid * 1e6 / (bf * d * d)
    fs = round(2.0 / 3.0 * s.fy * mid["As"] / As_mid_prov, 2)
    MF = min(0.55 + (477.0 - fs) / (120.0 * (0.9 + M_bd2)), 2.0)
    allow = basic * MF * (10.0 / L if L > 10 else 1.0)
    actual = Lmm / d
    r.update(ratio=ratio, basic=basic, M_bd2=M_bd2, fs=fs, MF=MF, allow=allow, actual=actual,
             defl_ok=allow >= actual)
    if not r["defl_ok"]:
        r["warnings"].append("Deflection check fails - increase the rib depth.")

    # ---- equivalent slab depth
    eq_load = top + rib_sw + blk
    eq = eq_load / s.concrete_density * 1000.0
    r.update(eq_load=eq_load, eq=eq, eq_round=math.ceil(eq / 10.0 - 1e-9) * 10)
    return r


# ------------------------------------------------------------------ text helpers
def _sb(b, sub):
    return f"${b}_{{{sub}}}$"


GK, QK = _sb("G", "k"), _sb("Q", "k")
FCU, FY, FYV = _sb("f", "cu"), _sb("f", "y"), _sb("f", "yv")
BF, HF, BW = _sb("b", "f"), _sb("h", "f"), _sb("b", "w")
AS, ASC = _sb("A", "s"), "$A_{s}'$"
ASREQ, ASPROV = _sb("A", "s,req"), _sb("A", "s,prov")
ASV, SV = _sb("A", "sv"), _sb("s", "v")
MR_, VC = _sb("M", "R"), _sb("v", "c")


OUT_TOKENS = {"G_k": GK, "Q_k": QK, "M_B": "$M_B$", "M_C": "$M_C$", "V_A": "$V_A$", "V_B": "$V_B$",
              "As,req": ASREQ, "As,prov": ASPROV, "A's": ASC, "vc ": "$v_c$ "}


def _bars(n, dia):
    return f"{n}Y{dia}"


# ------------------------------------------------------------------ sketches (all dims in mm)
def _dimh(ax, x0, x1, y, txt, off, fs=6.5, above=False, color=GREY):
    ax.annotate("", xy=(x1, y), xytext=(x0, y),
                arrowprops=dict(arrowstyle="<|-|>", lw=0.6, color=color, mutation_scale=5,
                                shrinkA=0, shrinkB=0))
    ax.text((x0 + x1) / 2, y + (off if above else -off), txt, ha="center",
            va="bottom" if above else "top", fontsize=fs, color=color)


def _dimv(ax, x, y0, y1, txt, off, fs=6.5, left=True, color=GREY):
    ax.annotate("", xy=(x, y1), xytext=(x, y0),
                arrowprops=dict(arrowstyle="<|-|>", lw=0.6, color=color, mutation_scale=5,
                                shrinkA=0, shrinkB=0))
    ax.text(x - off if left else x + off, (y0 + y1) / 2, txt, rotation=90,
            ha="right" if left else "left", va="center", fontsize=fs, color=color)


def _frame(ax, xlim, ylim):
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)


def draw_plan(ax, s, fs=7, label=""):
    W = s.panel_width_m * 1000
    L = s.span_m * 1000
    aw = s.adj_width_m * 1000 if s.has_adjacent else 0
    ad = min(s.adj_depth_m * 1000, L) if aw else 0
    u = 0.03 * max(W + aw, L)
    _frame(ax, (-6 * u, W + aw + 3 * u), (-5 * u, L + 3 * u))
    ax.add_patch(patches.Rectangle((0, 0), W, L, fill=False, ec=BLUE, lw=1.3))
    arrow = dict(arrowstyle="<|-|>", lw=1.5, color=RED, mutation_scale=9, shrinkA=0, shrinkB=0)
    ax.annotate("", xy=(W / 2, 0.82 * L), xytext=(W / 2, 0.18 * L), arrowprops=arrow)
    ax.text(W / 2 + u, L / 2, "ribs", fontsize=fs, color=RED, va="center")
    ax.text(W * 0.05, L * 0.94, label, fontsize=fs + 1, color=BLUE, weight="bold")
    if aw:
        ax.add_patch(patches.Rectangle((W, L - ad), aw, ad, fill=False, ec=BLUE, lw=1.3))
        ax.annotate("", xy=(W + aw / 2, L - 0.2 * ad), xytext=(W + aw / 2, L - 0.8 * ad), arrowprops=arrow)
        ax.plot([W, W], [L - ad, L], color=BLUE, lw=3)
        y = L - ad
        while y < L - u:
            ax.plot([W, W - 1.3 * u], [y, y + 1.3 * u], color=BLUE, lw=0.7)
            y += 1.6 * u
        _dimh(ax, W, W + aw, -2 * u, f"{aw:.0f}", u, fs)
    _dimh(ax, 0, W, -2 * u, f"{W:.0f}", u, fs)
    _dimv(ax, -2 * u, 0, L, f"$l_y$ = {L:.0f}", u, fs)


def draw_along(ax, s, fs=7):
    wa, wb, c = s.support_a_mm, s.support_b_mm, s.clear_span_mm
    T = wa + c + wb
    u = 0.02 * T
    ts, sd = 1.4 * u, 3.0 * u
    _frame(ax, (-3 * u, T + 3 * u), (-sd - 9 * u, ts + 6 * u))
    ax.add_patch(patches.Rectangle((0, 0), T, ts, fc="#E6E6E6", ec=BLUE, lw=1))
    for x0, w in ((0, wa), (wa + c, wb)):
        ax.add_patch(patches.Rectangle((x0, -sd), w, sd, fc="white", ec=BLUE, lw=1, hatch="///"))
    for lab, x in (("A", wa / 2), ("C", T / 2), ("B", T - wb / 2)):
        ax.plot([x, x], [ts, ts + 1.2 * u], color=BLUE, lw=0.8)
        ax.text(x, ts + 1.6 * u, lab, ha="center", va="bottom", fontsize=fs + 1, weight="bold", color=BLUE)
    y = -sd - 1.5 * u
    _dimh(ax, 0, wa, y, f"{wa:.0f}", 0.6 * u, fs - 0.5)
    _dimh(ax, wa, wa + c, y, f"{c:.0f}", 0.6 * u, fs)
    _dimh(ax, wa + c, T, y, f"{wb:.0f}", 0.6 * u, fs - 0.5)
    _dimh(ax, wa / 2, T - wb / 2, y - 5 * u, f"L = {s.span_m * 1000:.0f} (c/c)", 0.6 * u, fs)


def draw_section(ax, s, fs=7):
    rw, bk, t, hr = s.rib_width_mm, s.block_width_mm, s.topping_mm, s.rib_depth_mm
    T = 3 * rw + 2 * bk
    u = 0.04 * T
    _frame(ax, (-5 * u, T + 4 * u), (-4 * u, hr + t + 3 * u))
    xs = [0, rw, rw + bk, 2 * rw + bk, 2 * rw + 2 * bk, T]
    ax.add_patch(patches.Rectangle((0, hr), T, t, fc="#E6E6E6", ec=BLUE, lw=1))
    for i in (0, 2, 4):
        ax.add_patch(patches.Rectangle((xs[i], 0), xs[i + 1] - xs[i], hr, fc="#E6E6E6", ec=BLUE, lw=1))
    for i in (1, 3):
        ax.add_patch(patches.Rectangle((xs[i], 0), xs[i + 1] - xs[i], hr, fc="white", ec=BLUE, lw=0.8,
                                       hatch="//", alpha=1))
    y = -1.4 * u
    for i, w in enumerate((rw, bk, rw, bk, rw)):
        _dimh(ax, xs[i], xs[i + 1], y, f"{w:.0f}", 0.5 * u, fs - 0.5)
    _dimv(ax, -1.2 * u, hr, hr + t, f"{t:.0f}", 0.5 * u, fs)
    _dimv(ax, -1.2 * u, 0, hr, f"{hr:.0f}", 0.5 * u, fs)
    ax.text(T / 2, hr + t + 0.8 * u, "Hollow blocks hatched", ha="center", fontsize=fs - 1.5, color=GREY)


def draw_block3d(ax, s, fs=7):
    W, H, Ld = s.block_width_mm, s.rib_depth_mm, s.block_length_mm
    ang = math.radians(35)
    ox, oy = 0.55 * Ld * math.cos(ang), 0.55 * Ld * math.sin(ang)
    u = 0.05 * W
    _frame(ax, (-5 * u, W + ox + 5 * u), (-3 * u, H + oy + 3 * u))
    ax.add_patch(patches.Rectangle((0, 0), W, H, fc="white", ec=BLUE, lw=1.1))
    ax.add_patch(patches.Polygon([(0, H), (W, H), (W + ox, H + oy), (ox, H + oy)], fc="#F0F0F0", ec=BLUE, lw=1.1))
    ax.add_patch(patches.Polygon([(W, 0), (W + ox, oy), (W + ox, H + oy), (W, H)], fc="#DCDCDC", ec=BLUE, lw=1.1))
    for fx in (0.17, 0.60):
        ax.add_patch(patches.Rectangle((fx * W, 0.2 * H), 0.22 * W, 0.5 * H, fc="white", ec=BLUE, lw=0.8))
    _dimh(ax, 0, W, -1.2 * u, f"{W:.0f}", 0.4 * u, fs)
    _dimv(ax, -1.2 * u, 0, H, f"{H:.0f}", 0.4 * u, fs)
    ax.text(W + ox / 2 + 0.6 * u, oy / 2 - 1.6 * u, f"{Ld:.0f}", fontsize=fs, color=GREY, ha="left")


def draw_block_plan(ax, s, fs=7):
    na, nb = s.blocks_across, s.blocks_along
    u = 40.0
    _frame(ax, (-200, 1180), (-170, 1130))
    ax.add_patch(patches.Rectangle((0, 0), 1000, 1000, fill=False, ec=BLUE, lw=1.2))
    cw = (1000 - (na + 1) * u) / na
    rh = (1000 - (nb + 1) * u) / nb
    for i in range(na):
        for j in range(nb):
            x, y = u + i * (cw + u), u + j * (rh + u)
            ax.add_patch(patches.Rectangle((x, y), cw, rh, fc="#EFEFEF", ec=BLUE, lw=0.7))
            ax.plot([x + 0.2 * cw, x + 0.8 * cw], [y + 0.2 * rh, y + 0.8 * rh], color=BLUE, lw=0.5)
    _dimh(ax, 0, 1000, -60, f"1 m ({na} hollow blocks)", 30, fs)
    _dimv(ax, 1060, 0, 1000, f"1 m ({nb} hollow blocks)", 30, fs, left=False)


def draw_tsection(ax, s, r, fs=7):
    bf, hf, bw, h, d = r["bf"], r["hf"], r["bw"], r["h"], r["d"]
    u = 0.05 * bf
    _frame(ax, (-5 * u, bf + 7 * u), (-4 * u, h + 4 * u))
    ax.add_patch(patches.Rectangle((0, h - hf), bf, hf, fc="#E6E6E6", ec=BLUE, lw=1.1))
    ax.add_patch(patches.Rectangle(((bf - bw) / 2, 0), bw, h - hf, fc="#E6E6E6", ec=BLUE, lw=1.1))
    yb = h - d
    for fx in (0.3, 0.7):
        ax.plot((bf - bw) / 2 + fx * bw, yb, "o", color=BLUE, ms=3)
    ax.plot([0, bf], [h - hf, h - hf], color=GREY, lw=0.5, ls="--")
    _dimh(ax, 0, bf, h + 1.2 * u, f"{BF} = {bf:.0f}", 0.3 * u, fs, above=True)
    _dimv(ax, bf + 1.2 * u, h - hf, h, f"{HF} = {hf:.0f}", 0.4 * u, fs, left=False)
    _dimv(ax, bf + 3.6 * u, yb, h, f"d = {d:.0f}", 0.4 * u, fs, left=False)
    _dimv(ax, -1.2 * u, 0, h, f"h = {h:.0f}", 0.4 * u, fs)
    _dimh(ax, (bf - bw) / 2, (bf + bw) / 2, -1.4 * u, f"{BW} = {bw:.0f}", 0.4 * u, fs)


def draw_detail(ax, s, r, kind, fs=7):
    """kind = 'mid' or 'sup' : section through a rib."""
    bf, hf, bw, h, c = r["bf"], r["hf"], r["bw"], r["h"], s.cover_mm
    u = 0.05 * bf
    _frame(ax, (-5 * u, bf + 15 * u), (-8 * u, h + 3 * u))
    x0, x1 = (bf - bw) / 2, (bf + bw) / 2
    ax.add_patch(patches.Rectangle((x0, 0), bw, h - hf, fc="white", ec=BLUE, lw=1.1))
    ax.plot([0, bf], [h, h], color=BLUE, lw=1.1)
    ax.plot([0, x0], [h - hf, h - hf], color=BLUE, lw=1.1)
    ax.plot([x1, bf], [h - hf, h - hf], color=BLUE, lw=1.1)
    ax.plot([0, 0], [h - hf, h], color=BLUE, lw=0.8, ls=":")
    ax.plot([bf, bf], [h - hf, h], color=BLUE, lw=0.8, ls=":")
    ax.plot([x0, x0], [0, h - hf], color=BLUE, lw=1.1)
    ax.plot([x1, x1], [0, h - hf], color=BLUE, lw=1.1)
    ax.plot([x0, x1], [0, 0], color=BLUE, lw=1.1)
    # link
    lx0, lx1, ly0, ly1 = x0 + c, x1 - c, c, h - c
    ax.add_patch(patches.Rectangle((lx0, ly0), lx1 - lx0, ly1 - ly0, fill=False, ec=RED, lw=1.2))
    # bottom bars
    n = r["n_mid"]
    xs = [lx0 + s.link_dia + s.mid_dia / 2 + i * (lx1 - lx0 - 2 * s.link_dia - s.mid_dia) / max(n - 1, 1)
          for i in range(n)]
    yb = ly0 + s.link_dia + s.mid_dia / 2
    for x in xs:
        ax.plot(x, yb, "o", color=BLUE, ms=4)
    lab_x = bf + 2 * u
    ax.annotate(f"{_bars(n, s.mid_dia)}", xy=(xs[-1], yb), xytext=(lab_x, yb), fontsize=fs, va="center",
                arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))
    if r["case"] != "none":
        ax.annotate(f"Y{s.link_dia}@{r['sv_prov']} links", xy=(lx1, (ly0 + ly1) / 2 - 20),
                    xytext=(lab_x, (ly0 + ly1) / 2 - 20), fontsize=fs, va="center",
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))
    if kind == "mid":
        ym = h - hf + 0.55 * hf
        ax.plot([0, bf], [ym, ym], color=RED, lw=1.4, ls="--")
        ax.annotate(f"{s.mesh} BRC mesh", xy=(bf, ym), xytext=(lab_x, ym + 0.6 * hf), fontsize=fs,
                    va="center", arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))
        ax.text(bf / 2, -6.5 * u, "SECTION AT MIDSPAN", ha="center", fontsize=fs, weight="bold", color=BLUE)
    else:
        yt = h - c - 8
        k = max(2, int(bf // r["sp"]))
        x = (bf - (k - 1) * r["sp"]) / 2
        for i in range(k):
            ax.plot(x + i * r["sp"], yt, "o", color=BLUE, ms=3.2)
        ax.annotate(f"Y{s.sup_dia}@{r['sp']} (top)", xy=(bf, yt), xytext=(lab_x, h - 0.2 * hf),
                    fontsize=fs, va="center", arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))
        ax.text(bf / 2, -6.5 * u, "SECTION AT SUPPORT", ha="center", fontsize=fs, weight="bold", color=BLUE)
    _dimv(ax, -1.2 * u, 0, h, f"{h:.0f}", 0.4 * u, fs)
    _dimh(ax, x0, x1, -1.4 * u, f"{bw:.0f}", 0.4 * u, fs)


# ------------------------------------------------------------------ PDF
def generate_pdf(slab: RibbedSlab, project: ProjectInfo, res=None, filename="design.pdf"):
    s, p = slab, project
    r = res or analyse(s)
    PW, PH = 8.27, 11.69
    LEFT, RIGHT = 0.05, 0.95
    X0, X1 = LEFT + 0.14, RIGHT - 0.15
    TOP, BOTTOM, STEP = 0.868, 0.05, 0.0148
    ROWS = [0.985, 0.957, 0.934, 0.911, 0.891]
    st = {}
    pages = []

    def fit(ax, txt, x0, x1, y, fs0, **kw):
        fig = ax.figure
        rend = fig.canvas.get_renderer()
        fs = fs0
        t = ax.text((x0 + x1) / 2, y, txt, fontsize=fs, ha="center", va="center", **kw)
        while fs > 4.5:
            bb = t.get_window_extent(rend).transformed(ax.transAxes.inverted())
            if bb.width <= (x1 - x0) - 0.006:
                break
            fs -= 0.3
            t.set_fontsize(fs)
        return t

    def new_page():
        fig = plt.figure(figsize=(PW, PH))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.axis("off")
        pages.append((fig, ax))
        st.update(fig=fig, ax=ax, y=TOP, ref_y=2.0, out_y=2.0)
        ax.add_patch(patches.Rectangle((LEFT, BOTTOM - 0.012), RIGHT - LEFT, ROWS[0] + 0.006 - BOTTOM + 0.012,
                                       fill=False, ec="black", lw=1.0))
        # title block
        for y in ROWS[1:]:
            ax.plot([LEFT, RIGHT], [y, y], color="black", lw=0.6)
        cx = [LEFT, 0.21, 0.55, 0.75, RIGHT]
        for x in cx[1:-1]:
            ax.plot([x, x], [ROWS[4], ROWS[1]], color="black", lw=0.6)
        ax.plot([0.55, 0.55], [ROWS[1], ROWS[0] + 0.006], color="black", lw=0.6)
        try:
            img = plt.imread(p.logo_path)
            lax = ax.inset_axes([LEFT + 0.005, ROWS[1] + 0.002, 0.15, ROWS[0] - ROWS[1] + 0.002])
            lax.imshow(img)
            lax.axis("off")
        except Exception:
            ax.text(LEFT + 0.01, (ROWS[0] + ROWS[1]) / 2, "LOGO", fontsize=9, va="center")
        ax.text(0.57, 0.9795, p.firm_name, fontsize=8.5, weight="bold", color=BLUE, va="center")
        ax.text(0.57, 0.9665, f"{p.address}   Tel: {p.tel}", fontsize=6, va="center")
        ax.text(0.57, 0.9605, p.email, fontsize=6, va="center", color=BLUE)
        cells = [
            (ROWS[1], ROWS[2], "Project", p.project_title, cx[0], cx[2]),
            (ROWS[1], ROWS[2], "Job No.", p.job_no, cx[2], cx[3]),
            (ROWS[1], ROWS[2], "Sheet", "", cx[3], cx[4]),
            (ROWS[2], ROWS[3], "Element", p.element, cx[0], cx[2]),
            (ROWS[2], ROWS[3], "Designed by", p.designer, cx[2], cx[3]),
            (ROWS[2], ROWS[3], "Date", p.date, cx[3], cx[4]),
            (ROWS[3], ROWS[4], "Location", p.title(), cx[0], cx[2]),
            (ROWS[3], ROWS[4], "Checked by", p.checked_by, cx[2], cx[3]),
            (ROWS[3], ROWS[4], "Design code", "BS 8110-1:1997", cx[3], cx[4]),
        ]
        for ytop, ybot, lab, val, xa, xb in cells:
            ax.plot([xa, xa], [ybot, ytop], color="black", lw=0.4) if xa not in (LEFT,) else None
            ax.text(xa + 0.004, ytop - 0.0035, lab, fontsize=4.8, va="top", color="#444444")
            if val:
                fit(ax, val, xa + 0.004, xb, (ytop + ybot) / 2 - 0.0035, 7.6, weight="bold")
        ax.plot([LEFT, RIGHT], [ROWS[1], ROWS[1]], color="black", lw=0.6)
        # column headings
        ax.text((LEFT + X0) / 2, 0.8795, "Design Ref.", ha="center", va="center", fontsize=7, style="italic")
        ax.text((X0 + X1) / 2, 0.8795, "Calculation", ha="center", va="center", fontsize=7, style="italic")
        ax.text((X1 + RIGHT) / 2, 0.8795, "Output", ha="center", va="center", fontsize=7, style="italic")
        for x in (X0 - 0.004, X1 + 0.004):
            ax.plot([x, x], [BOTTOM - 0.012, ROWS[4]], color="black", lw=0.5)
        ax.plot([LEFT, RIGHT], [0.8895 - 0.0, 0.8895], color="black", lw=0.5)

    def ensure(h):
        if st["y"] - h < BOTTOM:
            new_page()

    def sync():
        st["y"] = min(st["y"], st["ref_y"], st["out_y"])

    def line(txt, indent=0.0, bold=False, fs=7.6, ref="", out="", color="black", style="normal"):
        width = (X1 - X0 - indent - 0.01) * PW
        nchar = max(20, int(width / (0.56 * fs / 72.0)))
        rows = textwrap.wrap(txt, nchar, break_long_words=False) or [""]
        ensure(STEP * (len(rows) + 0.3))
        ax = st["ax"]
        for i, row in enumerate(rows):
            ax.text(X0 + indent, st["y"] - i * STEP, row, fontsize=fs, va="top", weight="bold" if bold else "normal",
                    color=color, style=style)
        y0 = st["y"]
        if ref:
            ry = y0 if st["ref_y"] > y0 else st["ref_y"]
            for i, rr in enumerate(textwrap.wrap(ref, 22, break_long_words=False)):
                ax.text(LEFT + 0.006, ry - i * 0.0125, rr, fontsize=5.6, va="top", color="#0b3d91")
                st["ref_y"] = ry - (i + 1) * 0.0125
        if out:
            for k, v in OUT_TOKENS.items():
                out = out.replace(k, v)
            oy = y0
            if st["out_y"] < y0:
                oy = st["out_y"]
            for i, rr in enumerate(textwrap.wrap(out, 17, break_long_words=False)):
                ax.text(X1 + 0.008, oy - i * 0.0135, rr, fontsize=7.2, va="top", weight="bold", color=RED)
                st["out_y"] = oy - (i + 1) * 0.0135
        st["y"] = y0 - len(rows) * STEP

    def gap(n=0.5):
        st["y"] -= STEP * n

    def heading(txt):
        sync()
        gap(0.4)
        ensure(STEP * 3)
        ax = st["ax"]
        ax.text(X0, st["y"], txt, fontsize=8.6, weight="bold", color=BLUE, va="top")
        ax.plot([X0, X0 + 0.0075 * len(txt) * 1.05 + 0.02], [st["y"] - STEP * 1.05] * 2, color=BLUE, lw=0.8)
        st["y"] -= STEP * 1.5

    def sketch_row(items, h):
        sync()
        ensure(h + 0.01)
        ax = st["ax"]
        ytop = st["y"]
        ax.add_patch(patches.Rectangle((LEFT + 0.003, ytop - h - 0.004), RIGHT - LEFT - 0.006, h + 0.006,
                                       fc="white", ec="none", zorder=4))
        total = sum(w for _, w in items)
        x = 0.5 - total / 2
        for fn, w in items:
            sax = ax.inset_axes([x, ytop - h, w, h])
            sax.set_zorder(10)
            fn(sax)
            x += w
        st["y"] = ytop - h - 0.01
        st["ref_y"] = st["out_y"] = 2.0

    def add_page_numbers():
        n = len(pages)
        for i, (fig, ax) in enumerate(pages, 1):
            fit(ax, f"{i} of {n}", cx_sheet[0], cx_sheet[1], (ROWS[1] + ROWS[2]) / 2 - 0.0035, 8, weight="bold")

    cx_sheet = (0.75, RIGHT)
    f2 = lambda v: f"{v:.2f}"
    n_mid, dm = r["n_mid"], s.mid_dia
    mid, sup = r["mid"], r["sup"]
    Lm = r["L"]

    new_page()
    ax = st["ax"]
    ax.text((X0 + X1) / 2, st["y"], p.title(), ha="center", va="top", fontsize=10.5, weight="bold", color=BLUE)
    ax.plot([X0 + 0.02, X1 - 0.02], [st["y"] - STEP * 1.2] * 2, color=BLUE, lw=0.9)
    st["y"] -= STEP * 2.0

    sketch_row([(lambda a: draw_plan(a, s, label=p.panel_name.upper()), 0.62)], 0.19)
    sketch_row([(lambda a: draw_along(a, s), 0.80)], 0.095)
    sketch_row([(lambda a: draw_section(a, s), 0.42), (lambda a: draw_block3d(a, s), 0.30)], 0.125)

    # ---- design basis
    heading("DESIGN BASIS")
    line(f"Concrete grade {FCU} = {s.fcu} N/mm\u00b2      Reinforcement {FY} = {s.fy} N/mm\u00b2      "
         f"Links {FYV} = {s.fyv} N/mm\u00b2")
    line(f"Concrete cover = {s.cover_mm:.0f} mm      Concrete density = {s.concrete_density:g} kN/m\u00b3")
    line(f"Slab: {s.topping_mm:.0f} mm topping on {s.rib_depth_mm:.0f} mm ribs, overall depth H = {r['h']:.0f} mm; "
         f"ribs {s.rib_width_mm:.0f} mm wide at {r['bf']:.0f} mm centres")
    line(f"Clear span {s.clear_span_mm:.0f} mm, supports {s.support_a_mm:.0f} / {s.support_b_mm:.0f} mm wide: "
         f"effective span L = {s.clear_span_mm:.0f} + {(s.support_a_mm + s.support_b_mm) / 2:.0f} = "
         f"{r['Lmm']:.0f} mm", out=f"L = {Lm:.2f} m")

    # ---- loading
    heading("LOADING")
    line("Hollow blocks", bold=True)
    sketch_row([(lambda a: draw_block_plan(a, s), 0.24), (lambda a: draw_block3d(a, s), 0.24)], 0.115)
    line(f"Size of hollow blocks: H x L x W = {s.rib_depth_mm:.0f} x {s.block_length_mm:.0f} x "
         f"{s.block_width_mm:.0f} mm")
    line(f"Weight of 1 block = {s.block_kg:g} kg")
    line(f"Weight of blocks / m\u00b2 = {s.blocks_along} x {s.blocks_across} x {s.block_kg:g} = "
         f"{r['blk_kgm2']:g} kg/m\u00b2")
    line(f"= {r['blk_kgm2']:g} kg x 10 N/kg x 1/1000 = {f2(r['blk'])} kN/m\u00b2")
    gap(0.3)
    line("Ribs", bold=True)
    sketch_row([(lambda a: draw_tsection(a, s, r), 0.36)], 0.12)
    line(f"Flange width {BF} = rib width + block width = {s.rib_width_mm:.0f} + {s.block_width_mm:.0f} = "
         f"{r['bf']:.0f} mm")
    line(f"Area of ribs = {s.rib_width_mm / 1000:g} x {s.rib_depth_mm / 1000:g} = {r['rib_area']:.4g} m\u00b2")
    line(f"{s.ribs_per_m} ribs/m = {r['rib_area']:.4g} x {s.ribs_per_m} = {r['rib_area_m']:.4g} m\u00b2")
    line(f"Self-weight of ribs = {r['rib_area_m']:.4g} m\u00b2 x {s.concrete_density:g} kN/m\u00b3 = "
         f"{f2(r['rib_sw'])} kN/m\u00b2")
    gap(0.3)
    line("Dead loads", bold=True)
    line(f"Topping self-weight = {s.topping_mm / 1000:g} x {s.concrete_density:g}  = {f2(r['top'])} kN/m\u00b2")
    for lab, v in r["parts"][1:]:
        line(f"{lab}  = {f2(v)} kN/m\u00b2")
    line(f"{GK} = {f2(r['Gk'])} kN/m\u00b2", bold=True, out=f"G_k = {f2(r['Gk'])} kN/m\u00b2")
    gap(0.3)
    line(f"Live load, {QK} = {s.live_kNm2:g} kN/m\u00b2 ({s.live_label})", ref="BS 6399-1:1996 Table 1",
         out=f"Q_k = {s.live_kNm2:g} kN/m\u00b2")
    line(f"Design load, n = {s.gamma_g:g}{GK} + {s.gamma_q:g}{QK}", ref="BS 8110-1:1997 Cl 3.2.1.2.2")
    line(f"= {s.gamma_g:g}({f2(r['Gk'])}) + {s.gamma_q:g}({s.live_kNm2:g}) = {f2(r['n'])} kN/m\u00b2",
         out=f"n = {f2(r['n'])} kN/m\u00b2")
    gap(0.3)
    line(f"Consider a {BF} of {r['bf'] / 1000:.3f} m supported on each rib")
    line(f"udl on each rib = {r['bf'] / 1000:.3f} x {f2(r['n'])} = {f2(r['udl'])} kN/m", out=f"udl = {f2(r['udl'])} kN/m")
    line(f"Load on span F = {f2(r['udl'])} x {Lm:.2f} = {f2(r['F'])} kN", out=f"F = {f2(r['F'])} kN")
    line(f"Effective depth, d = H - cover - \u03c6/2 = {r['h']:.0f} - {s.cover_mm:.0f} - {s.phi_assumed_mm:.0f}/2 = "
         f"{r['d']:.0f} mm", out=f"d = {r['d']:.0f} mm")

    # ---- moments & shear
    heading("DESIGN OF BENDING MOMENT & SHEAR")
    line(f"Moment @ B = {s.c_support:g}FL = {s.c_support:g} x {f2(r['F'])} x {Lm:.2f} = {f2(r['Msup'])} kN.m",
         ref=s.coeff_ref, out=f"M_B = {f2(r['Msup'])} kN.m")
    line(f"Moment @ C = {s.c_mid:g}FL = {s.c_mid:g} x {f2(r['F'])} x {Lm:.2f} = {f2(r['Mmid'])} kN.m",
         out=f"M_C = {f2(r['Mmid'])} kN.m")
    line(f"Shear @ A = {s.c_shear_a:g}F = {s.c_shear_a:g} x {f2(r['F'])} = {f2(r['VA'])} kN", out=f"V_A = {f2(r['VA'])} kN")
    line(f"Shear @ B = {s.c_shear_b:g}F = {s.c_shear_b:g} x {f2(r['F'])} = {f2(r['VB'])} kN", out=f"V_B = {f2(r['VB'])} kN")

    # ---- midspan
    heading("MIDSPAN T-SECTION")
    line(f"Width of flange {BF} = {r['bf'] / 1000:.3f} m;   moment applied = {f2(r['Mmid'])} kN.m",
         ref="BS 8110-1:1997 Cl 3.4.4.4")
    line(f"Moment of resistance {MR_} = 0.45{FCU}{BF}{HF}(d - 0.5{HF})")
    line(f"{MR_} = 0.45 x {s.fcu} x {r['bf']:.0f} x {r['hf']:.0f} x ({r['d']:.0f} - 0.5 x {r['hf']:.0f}) = "
         f"{f2(r['MR'])} kN.m")
    line(f"{MR_} > M applied: neutral axis lies within the flange - treat as a rectangular section.")
    line(f"b = {r['bf']:.0f} mm,  d = {r['d']:.0f} mm")
    K = mid["K"]
    line(f"K = M / {FCU}bd\u00b2 = {f2(r['Mmid'])} x 10\u2076 / ({s.fcu} x {r['bf']:.0f} x {r['d']:.0f}\u00b2) = "
         f"{K:.4f}  {'<' if K <= K_LIM else '>'} 0.156" + ("  : no compression reinforcement required" if not mid['comp']
                                                            else "  : compression reinforcement required"))
    line(f"z = d[0.5 + \u221a(0.25 - K/0.9)] \u2264 0.95d = {mid['zr_raw']:.3f}d  "
         f"{'use 0.95d' if mid['zr_raw'] > 0.95 else '= ' + format(mid['zr'], '.2f') + 'd'}")
    line(f"{ASREQ} = M / (0.95{FY}z) = {f2(r['Mmid'])} x 10\u2076 / (0.95 x {s.fy} x {mid['zr']:.2f} x {r['d']:.0f}) = "
         f"{f2(mid['As'])} mm\u00b2", out=f"As,req = {f2(mid['As'])} mm\u00b2")
    line(f"Provide {_bars(n_mid, dm)} bars ({ASPROV} = {r['As_mid_prov']} mm\u00b2)", bold=True,
         out=f"As,prov = {r['As_mid_prov']} mm\u00b2")

    # ---- support
    heading("AT SUPPORTS - RECTANGULAR SECTION")
    line(f"Moment = {f2(r['Msup'])} kN.m;  b = {BW} = {r['bw']:.0f} mm")
    K = sup["K"]
    line(f"K = M / {FCU}bd\u00b2 = {f2(r['Msup'])} x 10\u2076 / ({s.fcu} x {r['bw']:.0f} x {r['d']:.0f}\u00b2) = "
         f"{K:.4f}  {'<' if K <= K_LIM else '>'} 0.156" + ("  : no compression reinforcement required" if not sup['comp']
                                                            else "  : compression reinforcement required"))
    if not sup["comp"]:
        line(f"z = d[0.5 + \u221a(0.25 - K/0.9)] = {sup['zr']:.2f}d = {sup['z']:.2f} mm")
        line(f"{ASREQ} = M / (0.95{FY}z) = {f2(r['Msup'])} x 10\u2076 / (0.95 x {s.fy} x {sup['z']:.2f}) = "
             f"{f2(sup['As'])} mm\u00b2")
    else:
        line(f"z = d[0.5 + \u221a(0.25 - 0.156/0.9)] = {sup['zr']:.2f}d = {sup['z']:.2f} mm")
        line(f"d' = cover + \u03c6/2 = {s.cover_mm:.0f} + {s.phi_assumed_mm:.0f}/2 = {r['dp']:.0f} mm")
        line(f"{ASC} = (K - K')f_cu b d\u00b2 / (0.95{FY}(d - d')) = {f2(sup['Asc'])} mm\u00b2",
             out=f"A's = {f2(sup['Asc'])} mm\u00b2")
        line(f"{AS} = K'{FCU}bd\u00b2 / (0.95{FY}z) + {ASC} = {f2(sup['As'])} mm\u00b2")
        ok = r.get("sup_comp_ok")
        line(f"Compression steel is provided by the {_bars(n_mid, dm)} bottom bars ({r['As_mid_prov']} mm\u00b2): "
             f"{'OK' if ok else 'NOT ENOUGH'}")
    line(f"{sup['As']:.2f} mm\u00b2 \u2192 {r['bf']:.0f} mm  (one rib per {r['bf']:.0f} mm width)")
    line(f"Per metre width: 1000 x {sup['As']:.2f} / {r['bf']:.0f} = {f2(r['As_m_req'])} mm\u00b2/m",
         out=f"As,req = {f2(r['As_m_req'])} mm\u00b2/m")
    line(f"Provide Y{s.sup_dia} bars @ {r['sp']} ({ASPROV} = {r['As_m_prov']} mm\u00b2/m)", bold=True,
         out=f"As,prov = {r['As_m_prov']} mm\u00b2/m")

    # ---- shear
    heading("SHEAR REINFORCEMENT")
    line(f"v = V / ({BW}d) = {f2(r['Vmax'])} x 10\u00b3 / ({r['bw']:.0f} x {r['d']:.0f}) = {r['v']:.3f} N/mm\u00b2",
         ref="BS 8110-1:1997 Cl 3.4.5.2", out=f"v = {r['v']:.3f} N/mm\u00b2")
    basis = ("support steel per rib" if s.shear_basis == SHEAR_STEEL_BASIS[0] else "support steel per metre")
    line(f"{AS} used for {VC}: {r['As_sh']:.0f} mm\u00b2 ({basis})")
    line(f"(100{AS}/{BW}d)^(1/3) = (100 x {r['As_sh']:.0f} / ({r['bw']:.0f} x {r['d']:.0f}))^(1/3) = {r['f_rho']:.3f}")
    line(f"(400/d)^(1/4) = (400/{r['d']:.0f})^(1/4) = {r['f_d']:.3f}" +
         (f";   (f_cu/25)^(1/3) = {r['f_fcu']:.3f}" if s.fcu > 25 else ""))
    line(f"{VC} = 0.79 x {r['f_rho']:.3f} x {r['f_d']:.3f}" + (f" x {r['f_fcu']:.3f}" if s.fcu > 25 else "") +
         f" / 1.25 = {r['vc']:.2f} N/mm\u00b2", ref="BS 8110-1:1997 Table 3.8", out=f"vc = {r['vc']:.2f} N/mm\u00b2")
    if r["case"] == "none":
        line(f"v < 0.5{VC} = {0.5 * r['vc']:.2f}: shear reinforcement is not required.", bold=True)
    else:
        line(f"0.5{VC} < v < {VC} + 0.4:   {0.5 * r['vc']:.2f} < {r['v']:.3f} < {r['vc'] + 0.4:.2f}" +
             ("  : minimal links required." if r["case"] == "minimal" else "") if r["case"] == "minimal"
             else f"v > {VC} + 0.4 ({r['vc'] + 0.4:.2f}): links designed for shear.", ref="BS 8110-1:1997 Table 3.7")
        form = (f"{ASV}/{SV} = 0.4{BW} / (0.95{FYV})" if r["case"] == "minimal"
                else f"{ASV}/{SV} = {BW}(v - {VC}) / (0.95{FYV})")
        line(form + f" \u2192 try Y{s.link_dia}, {s.link_legs} legs, {ASV} = {r['Asv']} mm\u00b2")
        den = f"0.4 x {r['bw']:.0f}" if r["case"] == "minimal" else f"{r['bw']:.0f} x ({r['v']:.3f} - {r['vc']:.2f})"
        line(f"{SV} = {ASV}(0.95{FYV}) / ({den}) = {r['Asv']} x 0.95 x {s.fyv} / ({den}) = {r['sv_req']:.2f} mm")
        rule = "4 x bw" if s.link_rule == LINK_SPACING_RULES[0] else "0.75d"
        line(f"Maximum spacing ({rule}) = {r['sv_lim']:.0f} mm", ref="BS 8110-1:1997 Cl 3.4.5.10")
        line(f"Provide Y{s.link_dia} links @ {r['sv_prov']}", bold=True, out=f"Y{s.link_dia} @ {r['sv_prov']}")

    # ---- deflection
    heading("DEFLECTION CHECK")
    line(f"{BW}/b = {r['bw']:.0f}/{r['bf']:.0f} = {r['ratio']:.3f}  {'<' if r['ratio'] <= 0.3 else '>'} 0.3 "
         f"({s.support_condition.lower()} span, flanged)", ref="BS 8110-1:1997 Table 3.9 & 3.10")
    line(f"Basic span/d ratio = {r['basic']:.1f}")
    line(f"M/bd\u00b2 = {f2(r['Mmid'])} x 10\u2076 / ({r['bf']:.0f} x {r['d']:.0f}\u00b2) = {r['M_bd2']:.3f}")
    line(f"{_sb('f', 's')} = 2/3 x {_sb('A', 's,req')}/{_sb('A', 's,prov')} x {FY} = 2/3 x {f2(mid['As'])}/"
         f"{r['As_mid_prov']} x {s.fy} = {f2(r['fs'])}")
    line(f"MF = 0.55 + (477 - {_sb('f', 's')}) / (120(0.9 + M/bd\u00b2)) = 0.55 + (477 - {f2(r['fs'])}) / "
         f"(120 x (0.9 + {r['M_bd2']:.3f})) = {r['MF']:.2f}  \u2264 2.0")
    line(f"Allowable span/d ratio = {r['basic']:.1f} x {r['MF']:.2f} = {r['allow']:.2f}")
    line(f"Actual span/d ratio = {r['Lmm']:.0f}/{r['d']:.0f} = {r['actual']:.2f}")
    line(("Allowable span/d > actual span/d : OK in deflection" if r["defl_ok"]
          else "Allowable span/d < actual span/d : FAILS in deflection - increase the rib depth"), bold=True,
         out="OK" if r["defl_ok"] else "FAIL")

    # ---- construction detail
    sync()
    ensure(0.42)
    heading("CONSTRUCTION DETAIL")
    sketch_row([(lambda a: draw_section(a, s), 0.38), (lambda a: draw_block3d(a, s), 0.26)], 0.15)
    sketch_row([(lambda a: draw_detail(a, s, r, "mid"), 0.36), (lambda a: draw_detail(a, s, r, "sup"), 0.36)], 0.17)
    line(f"Provide {s.cover_mm:.0f} mm cover to all reinforcement.")
    line(f"Topping reinforcement: {s.mesh} BRC mesh.")
    gap(0.3)
    line("Equivalent slab depth", bold=True)
    line(f"Topping self-weight = {f2(r['top'])} kN/m\u00b2")
    line(f"Ribs = {f2(r['rib_sw'])} kN/m\u00b2")
    line(f"Hollow blocks = {f2(r['blk'])} kN/m\u00b2")
    line(f"Total = {f2(r['eq_load'])} kN/m\u00b2")
    line(f"Equivalent depth = {f2(r['eq_load'])} / {s.concrete_density:g} = {r['eq'] / 1000:.3f} m \u2248 "
         f"{r['eq_round']:.0f} mm", bold=True, out=f"{r['eq_round']:.0f} mm")

    # ---- summary
    heading("SUMMARY OF REINFORCEMENT")
    rows = [("Midspan (bottom, per rib)", f"{_bars(n_mid, dm)}  ({r['As_mid_prov']} mm\u00b2)"),
            ("Support (top, per metre)", f"Y{s.sup_dia}@{r['sp']}  ({r['As_m_prov']} mm\u00b2/m)"),
            ("Links", "None required" if r["case"] == "none" else f"Y{s.link_dia} @ {r['sv_prov']}"),
            ("Topping mesh", f"{s.mesh} BRC"),
            ("Overall depth", f"{r['h']:.0f} mm ({s.topping_mm:.0f} + {s.rib_depth_mm:.0f})")]
    for a, b in rows:
        line(f"{a}:  {b}", bold=True)
    for w in r["warnings"]:
        line(f"NOTE: {w}", color=RED)

    add_page_numbers()
    with PdfPages(filename) as pdf:
        for fig, _ in pages:
            pdf.savefig(fig)
            plt.close(fig)
    return filename


def figure_of(fn, w=5.5, h=3.0):
    fig, ax = plt.subplots(figsize=(w, h))
    fn(ax)
    return fig
