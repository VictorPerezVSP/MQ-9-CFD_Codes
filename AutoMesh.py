# ==============================================================================
# PARAMETRIC MESH GENERATION VIA XML CONTRACT (GUI) / MANUAL & BOUNDARY LAYER
# Integrates:
# 1. Flow condition input and theoretical y1 calculation (y+=1)
# 2. Graphical XML contract file picker via explorer window (GUI)
# 3. Parsing of <MAC>, <SemiSpan>, and new <GeometryFilePath> path from XML
# 4. Alternative GUI explorer for selecting .scdocx geometry if XML fails
# 5. Dynamic output path linked to the location of the XML (or .scdocx)
# 6. Boundary layer selection: Theoretical vs. Manual modification due to RAM/CPU
# 7. Mesh density level selection (1: Finest -> 5: Coarsest)
# 8. Strict English label matching (inner_boi, middle_boi, uav_surface)
# 9. Unified Structured Boundary Layer (First Height + Smooth Expansion)
# 10. Poly-Hexcore Mesh Generation in PyFluent Meshing
# ==============================================================================
import os
import math
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog
import ansys.fluent.core as pyfluent
from ansys.fluent.core import FluentVersion, Precision, FluentMode, UIMode

# ---------------------------------------------------------
# 0. FILE EXPLORER FUNCTIONS (GUI)
# ---------------------------------------------------------
def select_xml_file():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Select XML Contract File",
        filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")]
    )
    root.destroy()
    return file_path

def select_geometry_file():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Select Geometry File (.scdocx)",
        filetypes=[
            ("SpaceClaim Files", "*.scdocx"), 
            ("All Files", "*.*")
        ]
    )
    root.destroy()
    return file_path

# ---------------------------------------------------------
# AUTOMATIC CLEANUP OF PREVIOUS PROCESSES
# ---------------------------------------------------------
print("[+] Cleaning up previous Fluent sessions and freeing RAM...")
os.system("taskkill /F /IM fluent.exe /T >nul 2>&1")
os.system("taskkill /F /IM cx2520.exe /T >nul 2>&1")
os.system("taskkill /F /IM fl_meshing.exe /T >nul 2>&1")

print("\n====================================================")
print("--> INTERACTIVE MESHING & SIMULATION SETUP <--")
print("====================================================")

def prompt_float(prompt_text, default_val):
    user_in = input(f"{prompt_text} [Default: {default_val}]: ").strip()
    return float(user_in) if user_in else float(default_val)

# ---------------------------------------------------------
# 1. FLUID AND FLOW PARAMETERS
# ---------------------------------------------------------
print("\n--- 1. FLOW CONDITIONS ---")
u_velocity = prompt_float("-> Flow velocity (u) [m/s]", 85.0)
density    = prompt_float("-> Fluid density (rho) [kg/m³]", 0.5489)
viscosity  = prompt_float("-> Dynamic viscosity (mu) [kg/(m·s)]", 1.527e-5)

# ---------------------------------------------------------
# 2 & 3. GEOMETRIC CONTRACT (GUI) & XML PARSING
# ---------------------------------------------------------
print("\n--- 2. GEOMETRIC CONTRACT AND GEOMETRY ---")
print("1. Select XML file using file explorer")
print("2. Input values manually and select geometry file")
xml_option = input("Select an option (1/2) [Default: 1]: ").strip()

output_dir = None
mac = None
semi_span = None
geometry_file = None
target_y_plus = 1.0  # Default

if xml_option != "2":
    print("\n[+] Opening file picker to select XML file...")
    xml_path = select_xml_file()
    
    if xml_path and os.path.exists(xml_path):
        print(f"  [v] XML file selected: {xml_path}")
        output_dir = os.path.dirname(xml_path)
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Parsing MAC and SemiSpan
            node_mac = root.find(".//MAC")
            if node_mac is not None and node_mac.text:
                mac = float(node_mac.text.strip())
            
            node_span = root.find(".//SemiSpan")
            if node_span is not None and node_span.text:
                semi_span = float(node_span.text.strip())
                
            # Parsing Geometry path
            node_geom = root.find(".//GeometryFilePath")
            if node_geom is not None and node_geom.text:
                path_candidate = node_geom.text.strip()
                if os.path.exists(path_candidate):
                    geometry_file = path_candidate
                    print(f"  [v] CAD geometry path read from XML: {geometry_file}")
                else:
                    print(f"  [!] The path specified in XML does not exist locally:\n      '{path_candidate}'")
                    
            # Parsing Recommended Target Y+ from XML (if present)
            node_yplus = root.find(".//TargetYPlus")
            if node_yplus is not None and node_yplus.text:
                target_y_plus = float(node_yplus.text.strip())
            
            if mac is not None:
                print(f"  [v] Parsed MAC: {mac} m")
            if semi_span is not None:
                print(f"  [v] Parsed SemiSpan (b/2): {semi_span} m")
        except Exception as e:
            print(f"  [!] Error reading XML file ({e}).")

# 4. FALLBACK FILE EXPLORER IF XML FAILS
if not geometry_file:
    print("\n[+] Opening file picker to select geometry file (.scdocx)...")
    geometry_file = select_geometry_file()
    
    if not geometry_file or not os.path.exists(geometry_file):
        default_geom = r"C:\Users\victo\UAV_Project\ALACHIKITA\Enclosure_CFD.scdocx"
        print(f"  [!] No valid file selected. Using default path: {default_geom}")
        geometry_file = default_geom
    else:
        print(f"  [v] Geometry selected manually: {geometry_file}")

# 5. DYNAMIC OUTPUT DIRECTORY
if not output_dir:
    output_dir = os.path.dirname(geometry_file)

if mac is None or semi_span is None:
    print("\n[i] Inserting custom geometric values:")
    mac = prompt_float(" -> Mean Aerodynamic Chord (MAC) [m]", 0.234)
    total_span = prompt_float(" -> Total wing span (b) [m]", 2.2)
    semi_span = total_span / 2.0

# ---------------------------------------------------------
# 6. THEORETICAL CALCULATION & BOUNDARY LAYER SELECTION (y1)
# ---------------------------------------------------------
reynolds = (density * u_velocity * mac) / viscosity
cf_friction = (2.0 * math.log10(reynolds) - 0.65) ** (-2.3)
tau_wall = 0.5 * density * (u_velocity ** 2) * cf_friction
u_tau = math.sqrt(tau_wall / density)
theoretical_y1 = (target_y_plus * viscosity) / (density * u_tau)

print("\n--- 3. FIRST INFLATION LAYER HEIGHT (y1) ---")
print(f" -> Reynolds Number (Re): {reynolds:.3e}")
print(f" -> Theoretical first layer height (y+ = {target_y_plus}): {theoretical_y1:.6e} m")

print("\nHow would you like to define the first inflation layer?")
print(f"1. Use calculated theoretical value (y+ = {target_y_plus})")
print("2. Modify height manually (e.g., due to RAM/CPU constraints)")
y1_option = input("Select an option (1/2) [Default: 1]: ").strip()

if y1_option == "2":
    first_layer_height = prompt_float(" -> Enter first layer height (y1) [m]", 0.00001)
    print(f"  [!] Using custom first layer height: {first_layer_height:.6e} m")
else:
    first_layer_height = theoretical_y1
    print(f"  [v] Using theoretical first layer height: {first_layer_height:.6e} m")

# ---------------------------------------------------------
# 7. MESH DENSITY SELECTION (LEVELS 1 TO 5)
# ---------------------------------------------------------
print("\n--- 4. MESH DENSITY SELECTION (1 to 5) ---")
print("1: Mesh M1 (Very Fine)")
print("2: Mesh M2 (Fine)")
print("3: Mesh M3 (Medium)")
print("4: Mesh M4 (Coarse-Fine)")
print("5: Mesh M5 (Coarse)")
mesh_option = input("Select density level (1-5) [Default: 5]: ").strip()

mesh_levels = {
    "1": {"name": "M1_VeryFine",   "factor": 0.40},
    "2": {"name": "M2_Fine",       "factor": 0.55},
    "3": {"name": "M3_Medium",     "factor": 0.70},
    "4": {"name": "M4_CoarseFine", "factor": 0.85},
    "5": {"name": "M5_Coarse",     "factor": 1.00}
}

if mesh_option not in mesh_levels:
    mesh_option = "5"

level_config = mesh_levels[mesh_option]
mesh_factor = level_config["factor"]
level_name = level_config["name"]

level_output_dir = os.path.join(output_dir, mesh_option)
os.makedirs(level_output_dir, exist_ok=True)
mesh_output_path = os.path.join(level_output_dir, f"Malla_UAV_{level_name}.msh.h5")

# ---------------------------------------------------------
# 8 & 9. PARAMETRIZATION & UNIFIED BOUNDARY LAYER
# ---------------------------------------------------------
# Parametric dimensions based on MAC
size_face_wing  = 0.0061 * mac * mesh_factor         
size_boi_fine   = 0.0061 * mac * mesh_factor         
size_boi_medium = 0.0122 * mac * mesh_factor         
mesh_min_size   = 0.00004 * mac * mesh_factor        
mesh_max_size   = 0.545 * semi_span 

# Unified Boundary Layer settings
total_inflation_layers = 45
inflation_growth_rate = 1.09

boi_fine_growth_rate = 1.00
boi_medium_growth_rate = 1.05
global_growth_rate = 1.08

# Strict English Labels
LABEL_UAV = ["*uav_surface*"]
LABEL_BOI_FINE = ["*inner_boi*"]
LABEL_BOI_MEDIUM = ["*middle_boi*"]

print("\n----------------------------------------------------")
print("FINAL PARAMETER SUMMARY:")
print(f" -> Base export path: {output_dir}")
print(f" -> Selected geometry: {geometry_file}")
print(f" -> Mesh Level: Level {mesh_option} ({level_name}) | Factor: {mesh_factor:.2f}")
print(f" -> MAC: {mac:.4f} m | Semi-span (b/2): {semi_span:.4f} m")
print(f" -> First layer height (y1): {first_layer_height:.6e} m")
print(f" -> Inflation layers: {total_inflation_layers} total (Growth Rate: {inflation_growth_rate})")
print(f" -> Output mesh file: {mesh_output_path}")
print("----------------------------------------------------\n")

# ---------------------------------------------------------
# 10. FLUENT MESHING EXECUTION (Poly-Hexcore)
# ---------------------------------------------------------
print("[+] Launching Ansys Fluent in Meshing mode (6 cores)...")
meshing_session = pyfluent.launch_fluent(
    product_version=FluentVersion.v252,
    mode=FluentMode.MESHING,
    precision=Precision.DOUBLE,
    processor_count=6,
    ui_mode=UIMode.NO_GUI_OR_GRAPHICS
)

meshing_session.journal.start(file_name=os.path.join(level_output_dir, f"uav_mq9_{level_name}.py"))
watertight = meshing_session.watertight()

# STEP 1: IMPORT GEOMETRY
print(f"[+] Loading geometry: {os.path.basename(geometry_file)}...")
watertight.import_geometry.arguments.set_state({
    "ImportType": "Single File",
    "FileName": geometry_file,
    "LengthUnit": "m"
})
watertight.import_geometry()

# STEP 2: PARAMETRIC LOCAL SIZING CONTROLS
print("[+] Applying local sizing controls...")

watertight.add_local_sizing.arguments.set_state({
    "AddChild": "yes",
    "BOIControlName": "uav_surface_refinement",
    "BOIExecution": "Face Size",
    "BOIFaceLabelList": LABEL_UAV,
    "BOISize": size_face_wing
})
watertight.add_local_sizing.add_child_and_update()

watertight.add_local_sizing.arguments.set_state({
    "AddChild": "yes",
    "BOIControlName": "boi_interior_fine",
    "BOIExecution": "Body of Influence",    
    "BOIFaceLabelList": LABEL_BOI_FINE,   
    "BOISize": size_boi_fine,
    "BOIGrowthRate": boi_fine_growth_rate
})
watertight.add_local_sizing.add_child_and_update()

watertight.add_local_sizing.arguments.set_state({
    "AddChild": "yes",
    "BOIControlName": "boi_intermedio_medium",
    "BOIExecution": "Body of Influence",    
    "BOIFaceLabelList": LABEL_BOI_MEDIUM, 
    "BOISize": size_boi_medium,
    "BOIGrowthRate": boi_medium_growth_rate
})
watertight.add_local_sizing.add_child_and_update()

# STEP 3: CREATE SURFACE MESH
print("[+] Generating surface mesh...")
surf_controls = watertight.create_surface_mesh.arguments.cfd_surface_mesh_controls
surf_controls.min_size.set_state(float(mesh_min_size))
surf_controls.max_size.set_state(float(mesh_max_size))
surf_controls.growth_rate.set_state(float(global_growth_rate))
surf_controls.size_functions.set_state("Curvature and Proximity")
surf_controls.scope_proximity_to.set_state("edges-and-faces")

watertight.create_surface_mesh()

# STEP 4: DESCRIBE GEOMETRY AND SHARE TOPOLOGY
print("[+] Sharing topology and defining fluid region...")
watertight.describe_geometry.update_child_tasks(setup_type_changed=False)
watertight.describe_geometry.setup_type.set_state("Fluid regions flow around solid bodies")
watertight.describe_geometry.update_child_tasks(setup_type_changed=True)

watertight.describe_geometry.arguments.set_state({
    "SetupType": "Fluid regions flow around solid bodies",
    "CappingRequired": "No",          
    "WallToInternal": "Yes",     
    "InvokeShareTopology": "Yes" 
})
watertight.describe_geometry()
watertight.apply_share_topology()

# STEP 5: UPDATE BOUNDARIES
print("[+] Assigning boundary types...")
watertight.update_boundaries.arguments.set_state({
    "BoundaryLabelList": [
        "inlet", "outlet", "*close_wall*", "far_wall", "bottom", "top", "*uav_surface*"
    ],
    "BoundaryLabelTypeList": [
        "velocity-inlet", "pressure-outlet", "symmetry", "symmetry", "symmetry", "symmetry", "wall"
    ]
})
watertight.update_boundaries()

# STEP 6: UPDATE REGIONS
print("[+] Processing volumetric domains...")
watertight.update_regions()

# STEP 7: UNIFIED STRUCTURED BOUNDARY LAYER
print(f"[+] Setting up Boundary Layer ({total_inflation_layers} total layers)...")
watertight.add_boundary_layer.arguments.set_state({
    "AddChild": "yes",
    "BLControlName": "inflation_uav",
    "OffsetMethodType": "first-layer-height",
    "FirstHeight": first_layer_height,
    "NumberOfLayers": total_inflation_layers,
    "Rate": inflation_growth_rate,
    "BlLabelList": LABEL_UAV
})
watertight.add_boundary_layer.add_child_and_update()

# STEP 8: CREATE POLY-HEXCORE VOLUME MESH
print("[+] Generating Poly-Hexcore volume mesh...")
vol_mesh_args = watertight.create_volume_mesh.arguments
vol_mesh_args.volume_fill.set_state("poly-hexcore")
vol_mesh_args.volume_fill_controls.hex_max_cell_length.set_state(float(mesh_max_size))

watertight.create_volume_mesh()

# STEP 9: EXPORT
print(f"[+] Saving mesh to: {mesh_output_path}")
meshing_session.tui.file.write_mesh(mesh_output_path)

meshing_session.journal.stop()
meshing_session.exit()

print("\n====================================================")
print(f"[***] MESH LEVEL {mesh_option} ({level_name}) COMPLETED AND EXPORTED [***]")
print("====================================================")