"""
===============================================================================
UAV WING GEOMETRY GENERATOR & CFD DATA BRIDGE
===============================================================================

SUMMARY OF SCRIPT OPERATION:
1. Builds a 3D semi-wing solid inside OpenVSP using parametric user inputs (in Meters)
   and external airfoil coordinate files (.dat).
2. Converts spatial dimensions to feet internally for OpenVSP compatibility so 
   that exported STEP files match metric dimensions in CAD software.
3. Sets flat end caps for watertight closing and exports geometry as a native 
   OpenVSP model (.vsp3) and a CAD solid (.stp).
4. Computes bounding box dimensions, Mean Aerodynamic Chord (MAC), and MAC 
   leading-edge coordinates in meters.
5. Exports exact XML Data Contract to 'wing_parameters.xml' for downstream processing.

WHAT YOU NEED TO MODIFY BEFORE RUNNING:
- File paths for root and tip airfoils (.dat)
- Output destinations for STEP, XML, and VSP3 files
- OpenVSP installation path
===============================================================================
"""

import os
import sys
import math
import xml.etree.ElementTree as ET
import xml.dom.minidom

# ==============================================================================
# CONFIGURATION & USER INPUTS (ALL DIMENSIONS IN METERS)
# ==============================================================================

# Wing Geometrical Parameters (Meters & Degrees)
ROOT_CHORD = 0.285       # Root chord in meters
TIP_CHORD = 0.174      # Tip chord in meters
SEMI_SPAN = 1.1       # Semi-span length in meters
SWEEP_ANGLE = 2.5      # Sweep angle in degrees

# Airfoil Input Files
ROOT_AIRFOIL_PATH = r"C:\Users\victo\OneDrive\Desktop\Tesis_MQ9\Perfiles\NACA4415_corte_recto.dat"  # <----------------------- ROUTE FOR ROOT AIRFOIL (.dat)
TIP_AIRFOIL_PATH  = r"C:\Users\victo\OneDrive\Desktop\Tesis_MQ9\Perfiles\NACA4415_corte_recto.dat"  # <----------------------- ROUTE FOR TIP AIRFOIL (.dat)

# File Output Paths
STEP_OUTPUT_PATH = r"C:\Users\victo\UAV_Project\ALACHIKITA\wing_mq9.stp"     # <----------------------- ROUTE FOR STEP FILE OUTPUT (.stp)
XML_OUTPUT_PATH  = r"C:\Users\victo\UAV_Project\ALACHIKITA\wing_parameters.xml"      # <----------------------- ROUTE FOR XML CONFIG FILE OUTPUT (.xml)
VSP3_OUTPUT_PATH = r"C:\Users\victo\UAV_Project\ALACHIKITA\wing_mq9.vsp3"             # <----------------------- ROUTE FOR VSP3 MODEL FILE OUTPUT (.vsp3)

# OpenVSP Installation Path
VSP_INSTALL_DIR  = r"C:\Users\victo\OneDrive\Desktop\OpenVSP-3.50.5-win64"            # <----------------------- ROUTE FOR OPENVSP INSTALLATION DIRECTORY

# Unit Conversion Factor (Meters to Feet for OpenVSP internal scale)
M2FT = 3.280839895
# ==============================================================================


def generate_wing_parameters_xml(step_export_path, xml_destination_path):
    print(f"\n[INFO] Calculating Bounding Box, MAC, and writing Data Contract XML to: {xml_destination_path}")

    # Ensure output directory exists
    xml_dir = os.path.dirname(os.path.abspath(xml_destination_path))
    if xml_dir and not os.path.exists(xml_dir):
        os.makedirs(xml_dir, exist_ok=True)

    root = ET.Element("WingParameters")

    # 1. File Metadata Node
    file_paths_node = ET.SubElement(root, "FilePaths")
    ET.SubElement(file_paths_node, "StepFilePath").text = step_export_path.replace("\\", "/")

    # 2. Bounding Box Node (Calculated in Meters)
    sweep_rad = math.radians(SWEEP_ANGLE)
    tip_le_x_offset = SEMI_SPAN * math.tan(sweep_rad)
    x_max_extent = max(ROOT_CHORD, tip_le_x_offset + TIP_CHORD)
    z_margin = ROOT_CHORD * 0.15

    bbox_node = ET.SubElement(root, "BoundingBox")
    ET.SubElement(bbox_node, "XMin").text = "0.0"
    ET.SubElement(bbox_node, "YMin").text = "0.0"
    ET.SubElement(bbox_node, "ZMin").text = str(round(-z_margin, 3))
    ET.SubElement(bbox_node, "XMax").text = str(round(x_max_extent, 3))
    ET.SubElement(bbox_node, "YMax").text = str(round(SEMI_SPAN, 3))
    ET.SubElement(bbox_node, "ZMax").text = str(round(z_margin, 3))
    ET.SubElement(bbox_node, "RootChord").text = str(ROOT_CHORD)
    ET.SubElement(bbox_node, "TipChord").text = str(TIP_CHORD)

    # 3. Aerodynamic Parameters Node (Calculated in Meters)
    taper_ratio = TIP_CHORD / ROOT_CHORD
    mac_length = (2.0 / 3.0) * ROOT_CHORD * ((1.0 + taper_ratio + taper_ratio**2) / (1.0 + taper_ratio))
    mac_y_pos = (SEMI_SPAN / 3.0) * ((1.0 + 2.0 * taper_ratio) / (1.0 + taper_ratio))
    mac_x_le = mac_y_pos * math.tan(sweep_rad)

    aero_node = ET.SubElement(root, "AerodynamicParameters")
    ET.SubElement(aero_node, "MAC").text = str(round(mac_length, 4))
    ET.SubElement(aero_node, "MACLeadingEdgeX").text = str(round(mac_x_le, 4))
    ET.SubElement(aero_node, "MACSpanwiseY").text = str(round(mac_y_pos, 4))

    # Format XML output
    raw_xml_string = ET.tostring(root, 'utf-8')
    parsed_xml = xml.dom.minidom.parseString(raw_xml_string)
    pretty_xml = parsed_xml.toprettyxml(indent="    ")

    abs_xml_path = os.path.abspath(xml_destination_path)
    with open(abs_xml_path, "w", encoding="utf-8") as file:
        file.write(pretty_xml)

    print(f"[SUCCESS] XML Data Contract successfully created at: {abs_xml_path}")
    return abs_xml_path


# ==============================================================================
# OPENVSP GEOMETRY ENGINE
# ==============================================================================

if hasattr(os, 'add_dll_directory'):
    os.add_dll_directory(VSP_INSTALL_DIR)

try:
    print("=== UAV Wing Geometry Generator & CFD Data Bridge ===")
    import openvsp as vsp

    vsp.ClearVSPModel()
    wing_geom_id = vsp.AddGeom("WING")
    vsp.SetGeomName(wing_geom_id, "UAV_Wing_4415")
    vsp.Update()

    # Apply topology settings (single semi-wing, watertight caps)
    parameter_ids = vsp.GetGeomParmIDs(wing_geom_id)
    for param_id in parameter_ids:
        param_name = vsp.GetParmName(param_id)
        if "Sym_Planar" in param_name:
            vsp.SetParmVal(param_id, 0.0)
        if "Cap_Type" in param_name:
            vsp.SetParmVal(param_id, 1.0)
    vsp.Update()

    # Configure custom airfoil profiles
    xsec_surface_id = vsp.GetXSecSurf(wing_geom_id, 0)
    vsp.ChangeXSecShape(xsec_surface_id, 0, vsp.XS_FILE_AIRFOIL)
    vsp.ChangeXSecShape(xsec_surface_id, 1, vsp.XS_FILE_AIRFOIL)
    vsp.Update()

    root_section = vsp.GetXSec(xsec_surface_id, 0)
    tip_section  = vsp.GetXSec(xsec_surface_id, 1)
    vsp.ReadFileAirfoil(root_section, ROOT_AIRFOIL_PATH)
    vsp.ReadFileAirfoil(tip_section, TIP_AIRFOIL_PATH)

    # Assign wing dimensions (Converting Meters to Feet for OpenVSP)
    vsp.SetParmVal(vsp.GetXSecParm(tip_section, "Root_Chord"), ROOT_CHORD * M2FT)
    vsp.SetParmVal(vsp.GetXSecParm(tip_section, "Tip_Chord"), TIP_CHORD * M2FT)
    vsp.SetParmVal(vsp.GetXSecParm(tip_section, "Span"), SEMI_SPAN * M2FT)
    vsp.SetParmVal(vsp.GetXSecParm(tip_section, "Sweep"), SWEEP_ANGLE)
    vsp.Update()

    # Target path preparation
    abs_vsp3_path = os.path.abspath(VSP3_OUTPUT_PATH)
    abs_step_path = os.path.abspath(STEP_OUTPUT_PATH)

    if os.path.dirname(abs_vsp3_path):
        os.makedirs(os.path.dirname(abs_vsp3_path), exist_ok=True)
    if os.path.dirname(abs_step_path):
        os.makedirs(os.path.dirname(abs_step_path), exist_ok=True)

    formatted_vsp3_path = abs_vsp3_path.replace("\\", "/")
    formatted_step_path = abs_step_path.replace("\\", "/")

    # Export OpenVSP session file
    print(f"[INFO] Writing VSP3 session file to: {formatted_vsp3_path}")
    vsp.WriteVSPFile(formatted_vsp3_path)

    # Export CAD solid STEP file
    print(f"[INFO] Exporting CAD STEP model to: {formatted_step_path}")
    vsp.Update()
    vsp.ExportFile(formatted_step_path, vsp.SET_ALL, vsp.EXPORT_STEP)

    # Integrity verification
    print("\n=== FILE GENERATION AUDIT ===")
    if os.path.exists(abs_vsp3_path):
        print(f"  [OK] VSP3 file successfully saved ({os.path.getsize(abs_vsp3_path)} bytes)")
    else:
        print(f"  [ERROR] VSP3 file not found at: {abs_vsp3_path}")

    if os.path.exists(abs_step_path):
        print(f"  [OK] STEP file successfully saved ({os.path.getsize(abs_step_path)} bytes)")
    else:
        print(f"  [ERROR] STEP file not found at: {abs_step_path}")

    # Build XML configuration file
    generated_xml_path = generate_wing_parameters_xml(formatted_step_path, XML_OUTPUT_PATH)
    print(f"\n[INFO] 'wing_parameters.xml' generated successfully.")

except Exception as error:
    print(f"\n[CRITICAL EXECUTION ERROR]: {error}")