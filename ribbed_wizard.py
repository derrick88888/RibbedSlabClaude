"""
Command-line wizard for the ribbed slab design.
Run:  python ribbed_wizard.py      (press Enter to accept the value in brackets)
"""
import os
import ribbed_slab as rs

HERE = os.path.dirname(os.path.abspath(__file__))


def ask(label, default, cast=str, options=None):
    shown = f" [{default}]" if default != "" else ""
    while True:
        raw = input(f"{label}{shown}: ").strip()
        if raw == "":
            return default
        if options is not None:
            if raw in [str(o) for o in options]:
                return cast(raw)
            print("  choose one of:", ", ".join(str(o) for o in options))
            continue
        try:
            return cast(raw)
        except ValueError:
            print("  invalid value")


def main():
    print("\n=== RIBBED SLAB DESIGN WIZARD (BS 8110-1:1997) ===\n")
    p = rs.ProjectInfo(logo_path=os.path.join(HERE, "logo.png"))
    s = rs.RibbedSlab()
    print("-- Project --")
    p.project_title = ask("Project", p.project_title)
    p.job_no = ask("Job No.", p.job_no)
    p.designer = ask("Designed by", p.designer)
    p.checked_by = ask("Checked by", p.checked_by)
    p.element = ask("Element", p.element)
    p.panel_name = ask("Panel", p.panel_name)
    p.grids = ask("Between grids", p.grids)
    print("\n-- Geometry (mm) --")
    s.clear_span_mm = ask("Clear span", s.clear_span_mm, float)
    s.support_a_mm = ask("Support A width", s.support_a_mm, float)
    s.support_b_mm = ask("Support B width", s.support_b_mm, float)
    s.panel_width_m = ask("Panel width across ribs (m)", s.panel_width_m, float)
    s.has_adjacent = ask("Adjacent panel in sketch? (1/0)", 1, int) == 1
    if s.has_adjacent:
        s.adj_width_m = ask("Adjacent panel width (m)", s.adj_width_m, float)
        s.adj_depth_m = ask("Adjacent panel length (m)", s.adj_depth_m, float)
    s.topping_mm = ask("Topping thickness", s.topping_mm, float)
    s.rib_depth_mm = ask("Rib depth below topping", s.rib_depth_mm, float)
    s.rib_width_mm = ask("Rib width", s.rib_width_mm, float)
    s.block_width_mm = ask("Block width (across ribs)", s.block_width_mm, float)
    s.block_length_mm = ask("Block length (along ribs)", s.block_length_mm, float)
    s.ribs_per_m = ask("Ribs per metre", s.ribs_per_m, int)
    s.blocks_along = ask("Blocks along 1 m", s.blocks_along, int)
    s.blocks_across = ask("Blocks across 1 m", s.blocks_across, int)
    s.block_kg = ask("Weight of one block (kg)", s.block_kg, float)
    print("\n-- Loading (kN/m2) --")
    s.partition_label = ask("Other dead load description", s.partition_label)
    s.partition_kNm2 = ask("Other dead load", s.partition_kNm2, float)
    s.finishes_kNm2 = ask("Finishes", s.finishes_kNm2, float)
    s.live_kNm2 = ask("Live load", s.live_kNm2, float)
    s.live_label = ask("Live load description", s.live_label)
    print("\n-- Materials and reinforcement --")
    s.fcu = ask("Concrete grade fcu", s.fcu, int, rs.CONCRETE_GRADES)
    s.fy = ask("Main steel fy", s.fy, int, rs.STEEL_GRADES)
    s.fyv = ask("Link steel fyv", s.fyv, int, rs.LINK_STEEL_GRADES)
    s.cover_mm = ask("Cover (mm)", s.cover_mm, float)
    s.phi_assumed_mm = ask("Bar dia assumed for d (mm)", s.phi_assumed_mm, float)
    s.mid_dia = ask("Midspan bar diameter", s.mid_dia, int, rs.BAR_DIAS)
    s.sup_dia = ask("Support bar diameter", s.sup_dia, int, rs.BAR_DIAS)
    s.link_dia = ask("Link diameter", s.link_dia, int, rs.LINK_DIAS)
    s.mesh = ask("Topping mesh", s.mesh, str, rs.MESH_OPTIONS)
    s.support_condition = ask("Span condition (deflection)", s.support_condition, str,
                              list(rs.SUPPORT_CONDITIONS))
    try:
        r = rs.analyse(s)
    except ValueError as e:
        print("\nDESIGN PROBLEM:", e)
        return
    print("\n=== RESULTS ===")
    print(f"d = {r['d']:.0f} mm   Gk = {r['Gk']:.2f}   n = {r['n']:.2f} kN/m2   F = {r['F']:.2f} kN")
    print(f"Moment B = {r['Msup']:.2f}  C = {r['Mmid']:.2f} kN.m    Shear = {r['Vmax']:.2f} kN")
    print(f"Midspan : {r['n_mid']}Y{s.mid_dia}  ({r['As_mid_prov']} mm2, req {r['mid']['As']:.2f})")
    print(f"Support : Y{s.sup_dia}@{r['sp']}  ({r['As_m_prov']} mm2/m, req {r['As_m_req']:.2f})")
    print("Links   :", "none required" if r["case"] == "none" else f"Y{s.link_dia}@{r['sv_prov']}")
    print(f"Deflection span/d: allowable {r['allow']:.2f} vs actual {r['actual']:.2f} "
          f"-> {'OK' if r['defl_ok'] else 'FAIL'}")
    for w in r["warnings"]:
        print("NOTE:", w)
    out = os.path.join(HERE, p.pdf_filename())
    rs.generate_pdf(s, p, r, out)
    print("\nPDF written to", out)


if __name__ == "__main__":
    main()
