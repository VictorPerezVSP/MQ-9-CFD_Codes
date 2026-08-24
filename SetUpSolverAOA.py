# ==============================================================================
# PARAMETRIC MASTER SCRIPT - MQ-9 REAPER AoA SWEEP
# Integrates velocity correction, aerodynamic vectors, API robustness,
# individualized convergence control, and filtered Cp export.
# ==============================================================================
import os
import math
import xml.etree.ElementTree as ET
import ansys.fluent.core as pyfluent

# ---------------------------------------------------------
# 0. PATH CONFIGURATION AND PHYSICAL CONSTANTS (ISA 25k ft)
# ---------------------------------------------------------
MESH_FILE = r"U:\Dissertation_MAC2025\SimB2AOA\N4415\Malla_Hibrida_UAV_441512m_WakeOptimized.msh.h5"
XML_PATH = r"U:\Dissertation_MAC2025\SimB2AOA\N4415\configuracion_geometria_fluent.xml"
OUTPUT_DIR = r"U:\Dissertation_MAC2025\SimB2AOA\N4415\NA4415sim"

V_INF = 85.0                 # Free-stream velocity in m/s (ISA 25k ft)
ITERATIONS_PER_AOA = 1500    # Iterations per Angle of Attack
AOA_LIST = [-2.0, 0.0, 2.0, 4.0, 6.0, 8.0, 10.0]  # List of Angles of Attack

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Atmospheric and Physical Parameters
operating_pressure = 37600.52   # Pa
temperature_25k = 238.65        # K (-34.5 °C)
R = 287.05                      # J/(kg·K)
air_viscosity = 1.527e-5        # kg/(m·s)
air_density = operating_pressure / (R * temperature_25k)  # ~0.5489 kg/m³
mac_chord = 1.313               # m
reynolds = (air_density * V_INF * mac_chord) / air_viscosity
tu_intensity = 0.0008165        # 0.08165%
tvr_viscosity_ratio = 2e-7 * reynolds  # ~0.8023

print("====================================================")
print("--> ADVANCED MQ-9 PARAMETRIC SWEEP <")
print("====================================================")

# ---------------------------------------------------------
# 1. MQ-9 REAPER GEOMETRIC PARAMETERS
# ---------------------------------------------------------
def get_xml_geometry(file_path):
    params = {"c_root": 1.7, "c_tip": 0.825, "b": 20.0}
    if os.path.exists(file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            for elem in root.iter():
                tag = elem.tag.lower()
                text = elem.text.strip() if elem.text else ""
                try:
                    val = float(text)
                    if "c_root" in tag or "croot" in tag or "chord_root" in tag: params["c_root"] = val
                    elif "c_tip" in tag or "ctip" in tag or "chord_tip" in tag: params["c_tip"] = val
                    elif tag == "b" or "span" in tag or "envergadura" in tag: params["b"] = val
                except ValueError:
                    continue
        except Exception: pass
    
    if params["b"] < 12.0: params["b"] = 20.0
    semi_span = params["b"] / 2.0
    semi_area = (semi_span * (params["c_root"] + params["c_tip"])) / 2.0
    return semi_area, semi_span, params["c_root"]

ref_area, semi_span, c_root = get_xml_geometry(XML_PATH)

# ---------------------------------------------------------
# 2. LAUNCH FLUENT AND IMPORT MESH
# ---------------------------------------------------------
print("\n[+] Launching Ansys Fluent Solver (4 cores)...")
solver = pyfluent.launch_fluent(precision="double", processor_count=4, ui_mode="gui")
print(f"[+] Loading mesh: {MESH_FILE}")
solver.settings.file.read_mesh(file_name=MESH_FILE)

# ---------------------------------------------------------
# 3. PHYSICAL AND NUMERICAL SETUP
# ---------------------------------------------------------
print("\n[+] Configuring Models and Materials...")
solver.settings.setup.general.operating_conditions.operating_pressure = operating_pressure
solver.settings.setup.models.energy.enabled = False
solver.settings.setup.models.viscous.model = "k-omega"
solver.settings.setup.models.viscous.k_omega_model = "sst"

solver.settings.setup.materials.fluid["air"] = {
    "density": {"option": "constant", "value": air_density},
    "viscosity": {"option": "constant", "value": air_viscosity}
}

print("[+] Setting Boundary Conditions...")
solver.settings.setup.boundary_conditions.set_zone_type(
    zone_list=["inlet", "top", "bottom", "far_wall"], new_type="velocity-inlet"
)
solver.settings.setup.boundary_conditions.set_zone_type(
    zone_list=["outlet"], new_type="pressure-outlet"
)
solver.settings.setup.boundary_conditions.set_zone_type(
    zone_list=["close_wall", "close_wall.1", "close_wall.2"], new_type="symmetry"
)
solver.settings.setup.boundary_conditions.set_zone_type(
    zone_list=["uav_surface"], new_type="wall"
)

# Initial turbulence configuration at outlet
p_outlet = solver.settings.setup.boundary_conditions.pressure_outlet["outlet"]
p_outlet.momentum.gauge_pressure.value = 0.0
p_outlet.turbulence = {
    "turbulence_specification": "Intensity and Viscosity Ratio",
    "turbulent_intensity": tu_intensity,
    "turbulent_viscosity_ratio": tvr_viscosity_ratio,
}

print("[+] Configuring Solver and Convergence Criteria...")
solver.settings.solution.methods.p_v_coupling.flow_scheme = "SIMPLE"
try:
    solver.settings.solution.methods.warped_face_gradient_correction.enable = True
    solver.settings.solution.methods.warped_face_gradient_correction.mode = "fast"
except Exception: pass

# Custom residual convergence criteria
residual_criteria = {
    "continuity": 1e-5,   # Continuity tolerance
    "x-velocity": 1e-4,   # X-velocity tolerance
    "y-velocity": 1e-4,   # Y-velocity tolerance
    "z-velocity": 1e-4,   # Z-velocity tolerance
    "k": 1e-5,            # Turbulence kinetic energy
    "omega": 1e-5         # Specific dissipation rate
}

print("  [-] Applying residual criteria:")
for eq, criterion in residual_criteria.items():
    try: 
        solver.settings.solution.monitor.residual.equations[eq].absolute_criteria = criterion
        print(f"      [v] Residual criterion for '{eq}' set to {criterion}")
    except Exception: 
        print(f"      [x] Could not set residual criterion for '{eq}'")

print("[+] Assigning Reference Values...")
solver.settings.setup.reference_values.area = ref_area
solver.settings.setup.reference_values.length = mac_chord
solver.settings.setup.reference_values.velocity = V_INF
solver.settings.setup.reference_values.density = air_density
solver.settings.setup.reference_values.viscosity = air_viscosity

# ---------------------------------------------------------
# 4. AERODYNAMIC REPORTS
# ---------------------------------------------------------
print("[+] Registering Aerodynamic Monitors...")
solver.settings.solution.report_definitions.drag.create(name="drag_uav")
solver.settings.solution.report_definitions.drag["drag_uav"].zones = ["uav_surface"]

solver.settings.solution.report_definitions.lift.create(name="lift_uav")
solver.settings.solution.report_definitions.lift["lift_uav"].zones = ["uav_surface"]

solver.settings.solution.report_definitions.drag.create(name="cd_pressure")
solver.settings.solution.report_definitions.drag["cd_pressure"].zones = ["uav_surface"]
try: solver.settings.solution.report_definitions.drag["cd_pressure"].drag_option = "pressure-drag"
except Exception: pass

solver.settings.solution.report_definitions.drag.create(name="cd_viscous")
solver.settings.solution.report_definitions.drag["cd_viscous"].zones = ["uav_surface"]
try: solver.settings.solution.report_definitions.drag["cd_viscous"].drag_option = "viscous-drag"
except Exception: pass

solver.settings.solution.report_definitions.moment.create(name="cm_pitch")
solver.settings.solution.report_definitions.moment["cm_pitch"].zones = ["uav_surface"]
try:
    solver.settings.solution.report_definitions.moment["cm_pitch"].mom_axis = [0, 1, 0]
    solver.settings.solution.report_definitions.moment["cm_pitch"].mom_center = [0.52225, 0.0, 0.0]
except AttributeError:
    solver.settings.solution.report_definitions.moment["cm_pitch"].axis = [0, 1, 0]
    solver.settings.solution.report_definitions.moment["cm_pitch"].center = [0.52225, 0.0, 0.0]

try:
    solver.settings.solution.monitor.report_files.create(name="monitores_out")
    r_file = solver.settings.solution.monitor.report_files["monitores_out"]
    r_file.file_name = os.path.join(OUTPUT_DIR, "Monitores_Aerodinamicos.out")
    r_file.report_defs = ["drag_uav", "lift_uav", "cd_pressure", "cd_viscous", "cm_pitch"]
    r_file.print = True
except Exception: pass

def execute_scheme_tui(tui_command):
    cmd_eval = f'(ti-menu-load-string "{tui_command}")'
    try: solver.scheme.eval(cmd_eval)
    except AttributeError: solver.scheme_eval.scheme_eval(cmd_eval)

# ---------------------------------------------------------
# 5. AoA PARAMETRIC SWEEP
# ---------------------------------------------------------
print("\n============================================================")
print("STARTING AoA PARAMETRIC SWEEP")
print("============================================================\n")

surfaces_created = False
inlet_zones = ["inlet", "top", "bottom", "far_wall"]

for i, aoa in enumerate(AOA_LIST, 1):
    print(f"\n[>>>] [{i}/{len(AOA_LIST)}] Setting up and Simulating AoA = {aoa:.1f}°")

    # A. Kinematics: Wind vector rotation
    aoa_rad = math.radians(aoa)
    dir_x = math.cos(aoa_rad)
    dir_z = math.sin(aoa_rad)

    for zone in inlet_zones:
        v_inlet = solver.settings.setup.boundary_conditions.velocity_inlet[zone]
        v_inlet.momentum.velocity_specification_method = "Magnitude and Direction"
        v_inlet.momentum.velocity_magnitude.value = V_INF
        v_inlet.momentum.flow_direction = [dir_x, 0.0, dir_z]
        v_inlet.turbulence = {
            "turbulence_specification": "Intensity and Viscosity Ratio",
            "turbulent_intensity": tu_intensity,
            "turbulent_viscosity_ratio": tvr_viscosity_ratio,
        }

    # B. Aerodynamics: Report force vector rotation
    solver.settings.solution.report_definitions.drag["drag_uav"].force_vector = [dir_x, 0.0, dir_z]
    solver.settings.solution.report_definitions.drag["cd_pressure"].force_vector = [dir_x, 0.0, dir_z]
    solver.settings.solution.report_definitions.drag["cd_viscous"].force_vector = [dir_x, 0.0, dir_z]
    solver.settings.solution.report_definitions.lift["lift_uav"].force_vector = [-dir_z, 0.0, dir_x]

    # C. Initialization
    print("  [-] Initializing solution (Hybrid Initialization)...")
    try:
        solver.settings.solution.initialization.hybrid_initialize()
    except Exception:
        solver.tui.solve.initialize.hybrid_initialize()

    # D. Post-processing surfaces creation
    if not surfaces_created:
        print("  [+] Creating monitoring surfaces (Cp and Wake)...")
        yb_fractions = [0.20, 0.50, 0.75, 0.90]
        for frac in yb_fractions:
            y_val = frac * semi_span
            line_name = f"cp_line_yb_{int(frac*100)}"
            execute_scheme_tui(f'surface/iso-surface y-coordinate {line_name} (uav_surface) () {y_val} ()')

        xc_fractions = [1.10, 1.50]
        for frac in xc_fractions:
            x_val = frac * c_root
            surf_name = f"wake_plane_xc_{int(frac*100)}"
            execute_scheme_tui(f'surface/iso-surface x-coordinate {surf_name} () () {x_val} ()')
            
        surfaces_created = True

    # E. Run iterations
    print(f"  [-] Running {ITERATIONS_PER_AOA} iterations...")
    solver.tui.solve.iterate(ITERATIONS_PER_AOA)

    # F. Export and Save per AoA
    str_aoa = f"{'+' if aoa >= 0 else ''}{aoa:.1f}".replace('.', 'p')
    csv_file = os.path.join(OUTPUT_DIR, f"Perfiles_Cp_AoA_{str_aoa}.csv").replace("\\", "/")

    print(f"  [-] Exporting Cp data to {csv_file}...")
    try:
        # PyFluent TUI export with explicit parameters
        solver.tui.file.export.ascii(
            csv_file, 
            "cp_line_yb_20", "cp_line_yb_50", "cp_line_yb_75", "cp_line_yb_90", "()", 
            "no",                    # Write Binary Files? -> no
            "pressure-coefficient",  # Exact selection of Pressure Coefficient
            "()",                    # End of fields selection
            "no"                     # Write Cell Center Data? -> no
        )
        print(f"  [+] Cp profiles exported successfully.")
    except Exception as err:
        print(f"  [!] Error exporting Cp CSV: {err}")

    # Save Case and Data
    case_path = os.path.join(OUTPUT_DIR, f"MQ9_AoA_{str_aoa}.cas.h5")
    data_path = os.path.join(OUTPUT_DIR, f"MQ9_AoA_{str_aoa}.dat.h5")
    solver.settings.file.write_case(file_name=case_path)
    solver.settings.file.write_data(file_name=data_path)
    print(f"  [+] Case and Data saved successfully.\n")

print("[***] PARAMETRIC SWEEP COMPLETED SUCCESSFULLY [***]")
solver.exit()