# ==============================================================================
# GENERACIÓN DE MALLA PARAMÉTRICA VÍA CONTRATO XML (GUI) / MANUAL Y CAPA LÍMITE
# Integra:
# 1. Entrada de condiciones de flujo y cálculo teórico de y1 (y+=1)
# 2. Seleccionador gráfico de archivo XML mediante ventana de exploración (GUI)
# 3. Lectura de <MAC>, <SemiSpan> y nueva ruta <GeometryFilePath> del XML
# 4. Explorador GUI alternativo para seleccionar geometría .scdocx si falla XML
# 5. Ruta de salida dinámica vinculada a la ubicación del XML (o del .scdocx)
# 6. Selección de Capa Límite: Teórica vs. Modificación manual por RAM/CPU
# 7. Selección de nivel de malla (1: Más fina -> 5: Más gruesa)
# 8. Búsqueda de etiquetas estrictas en inglés (inner_boi, middle_boi, uav_surface)
# 9. Capa Límite Estructurada en 2 etapas: 2 capas de y1 constante + expansión
# 10. Generación de Malla Poly-Hexcore en PyFluent Meshing
# ==============================================================================
import os
import math
import xml.etree.ElementTree as ET
import tkinter as tk
from tkinter import filedialog
import ansys.fluent.core as pyfluent
from ansys.fluent.core import FluentVersion, Precision, FluentMode, UIMode

# ---------------------------------------------------------
# 0. FUNCIONES DE EXPLORACIÓN DE ARCHIVOS (GUI)
# ---------------------------------------------------------
def seleccionar_archivo_xml():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo de Contrato XML",
        filetypes=[("Archivos XML", "*.xml"), ("Todos los archivos", "*.*")]
    )
    root.destroy()
    return file_path

def seleccionar_archivo_geometria():
    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    file_path = filedialog.askopenfilename(
        title="Selecciona el archivo de Geometría (.scdocx)",
        filetypes=[
            ("Archivos SpaceClaim", "*.scdocx"), 
            ("Todos los archivos", "*.*")
        ]
    )
    root.destroy()
    return file_path

# ---------------------------------------------------------
# LIMPIEZA AUTOMÁTICA DE PROCESOS PREVIOS
# ---------------------------------------------------------
print("[+] Limpiando sesiones previas de Fluent y liberando RAM...")
os.system("taskkill /F /IM fluent.exe /T >nul 2>&1")
os.system("taskkill /F /IM cx2520.exe /T >nul 2>&1")
os.system("taskkill /F /IM fl_meshing.exe /T >nul 2>&1")

print("\n====================================================")
print("--> CONFIGURACIÓN INTERACTIVA DE MALLADO Y SIMULACIÓN <")
print("====================================================")

def solicitar_float(prompt, default_val):
    user_in = input(f"{prompt} [Predeterminado: {default_val}]: ").strip()
    return float(user_in) if user_in else float(default_val)

# ---------------------------------------------------------
# 1. PARÁMETROS DEL FLUIDO Y FLUJO
# ---------------------------------------------------------
print("\n--- 1. CONDICIONES DEL FLUJO ---")
u_velocity = solicitar_float("-> Velocidad del flujo (u) [m/s]", 85.0)
density    = solicitar_float("-> Densidad del fluido (rho) [kg/m³]", 0.5489)
viscosity  = solicitar_float("-> Viscosidad dinámica (mu) [kg/(m·s)]", 1.527e-5)

# ---------------------------------------------------------
# 2 Y 3. LECTURA DE CONTRATO GEOMÉTRICO (GUI) Y XML
# ---------------------------------------------------------
print("\n--- 2. CONTRATO GEOMÉTRICO Y GEOMETRÍA ---")
print("1. Seleccionar archivo XML mediante explorador de archivos")
print("2. Insertar valores a discreción y elegir geometría manualmente")
opcion_xml = input("Seleccione una opción (1/2) [Predeterminado: 1]: ").strip()

output_dir = None
mac = None
semi_span = None
archivo_geometria = None
y_plus_target = 1.0  # Default

if opcion_xml != "2":
    print("\n[+] Abriendo ventana para seleccionar el archivo XML...")
    xml_path = seleccionar_archivo_xml()
    
    if xml_path and os.path.exists(xml_path):
        print(f"  [v] Archivo XML seleccionado: {xml_path}")
        output_dir = os.path.dirname(xml_path)
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # Lectura de MAC y SemiSpan
            node_mac = root.find(".//MAC")
            if node_mac is not None and node_mac.text:
                mac = float(node_mac.text.strip())
            
            node_span = root.find(".//SemiSpan")
            if node_span is not None and node_span.text:
                semi_span = float(node_span.text.strip())
                
            # Lectura de Geometría (Usa la nueva etiqueta GeometryFilePath)
            node_geom = root.find(".//GeometryFilePath")
            if node_geom is not None and node_geom.text:
                path_candidate = node_geom.text.strip()
                if os.path.exists(path_candidate):
                    archivo_geometria = path_candidate
                    print(f"  [v] Ruta de geometría CAD leída del XML: {archivo_geometria}")
                else:
                    print(f"  [!] La ruta especificada en el XML no existe localmente:\n      '{path_candidate}'")
                    
            # Lectura de Y+ Target recomendado en el XML (Si existe)
            node_yplus = root.find(".//TargetYPlus")
            if node_yplus is not None and node_yplus.text:
                y_plus_target = float(node_yplus.text.strip())
            
            if mac is not None:
                print(f"  [v] MAC leído: {mac} m")
            if semi_span is not None:
                print(f"  [v] SemiSpan (b/2) leído: {semi_span} m")
        except Exception as e:
            print(f"  [!] Error leyendo el archivo XML ({e}).")

# 4. EXPLORADOR ALTERNATIVO SI FALLA XML
if not archivo_geometria:
    print("\n[+] Abriendo ventana para seleccionar el archivo de geometría (.scdocx)...")
    archivo_geometria = seleccionar_archivo_geometria()
    
    if not archivo_geometria or not os.path.exists(archivo_geometria):
        default_geom = r"C:\Users\victo\UAV_Project\ALACHIKITA\Enclosure_CFD.scdocx"
        print(f"  [!] No se seleccionó un archivo válido. Usando ruta por defecto: {default_geom}")
        archivo_geometria = default_geom
    else:
        print(f"  [v] Geometría seleccionada manualmente: {archivo_geometria}")

# 5. RUTA DE SALIDA DINÁMICA
if not output_dir:
    output_dir = os.path.dirname(archivo_geometria)

if mac is None or semi_span is None:
    print("\n[i] Insertando valores geométricos a discreción:")
    mac = solicitar_float(" -> Cuerda Media Aerodinámica (MAC) [m]", 0.234)
    span_total = solicitar_float(" -> Envergadura total del ala (b) [m]", 2.2)
    semi_span = span_total / 2.0

# ---------------------------------------------------------
# 6. CÁLCULO TEÓRICO Y SELECCIÓN DE CAPA LÍMITE (y1)
# ---------------------------------------------------------
reynolds = (density * u_velocity * mac) / viscosity
cf_friction = (2.0 * math.log10(reynolds) - 0.65) ** (-2.3)
tau_wall = 0.5 * density * (u_velocity ** 2) * cf_friction
u_tau = math.sqrt(tau_wall / density)
y1_teorico = (y_plus_target * viscosity) / (density * u_tau)

print("\n--- 3. ALTURA DE LA PRIMERA CAPA DE INFLACIÓN (y1) ---")
print(f" -> Número de Reynolds (Re): {reynolds:.3e}")
print(f" -> Altura teórica calculada (y+ = {y_plus_target}): {y1_teorico:.6e} m")

print("\n¿Cómo deseas definir la primera capa de inflación?")
print(f"1. Usar valor teórico calculado (y+ = {y_plus_target})")
print("2. Modificar tamaño manualmente (ej. por restricciones de RAM/CPU)")
opcion_y1 = input("Seleccione una opción (1/2) [Predeterminado: 1]: ").strip()

if opcion_y1 == "2":
    first_layer_height = solicitar_float(" -> Ingrese la altura de la primera celda (y1) [m]", 0.00001)
    print(f"  [!] Usando primera capa personalizada: {first_layer_height:.6e} m")
else:
    first_layer_height = y1_teorico
    print(f"  [v] Usando primera capa teórica: {first_layer_height:.6e} m")

# ---------------------------------------------------------
# 7. SELECCIÓN DE DENSIDAD DE MALLA (NIVELES 1 AL 5)
# ---------------------------------------------------------
print("\n--- 4. SELECCIÓN DE DENSIDAD DE MALLA (1 a 5) ---")
print("1: Malla M1 (Muy Fina)")
print("2: Malla M2 (Fina)")
print("3: Malla M3 (Media)")
print("4: Malla M4 (Medio-Gruesa)")
print("5: Malla M5 (Gruesa)")
opcion_malla = input("Seleccione el nivel de densidad (1-5) [Predeterminado: 5]: ").strip()

niveles_malla = {
    "1": {"nombre": "M1_VeryFine",  "factor": 0.40},
    "2": {"nombre": "M2_Fine",      "factor": 0.55},
    "3": {"nombre": "M3_Medium",    "factor": 0.70},
    "4": {"nombre": "M4_CoarseFine","factor": 0.85},
    "5": {"nombre": "M5_Coarse",    "factor": 1.00}
}

if opcion_malla not in niveles_malla:
    opcion_malla = "5"

config_nivel = niveles_malla[opcion_malla]
factor_malla = config_nivel["factor"]
nombre_nivel = config_nivel["nombre"]

output_dir_nivel = os.path.join(output_dir, opcion_malla)
os.makedirs(output_dir_nivel, exist_ok=True)
mesh_output_path = os.path.join(output_dir_nivel, f"Malla_UAV_{nombre_nivel}.msh.h5")

# ---------------------------------------------------------
# 8 y 9. PARAMETRIZACIÓN, ETIQUETAS EN INGLÉS Y BL EN 2 ETAPAS
# ---------------------------------------------------------
# Dimensiones parametrizadas basadas en MAC
size_face_wing  = 0.0061 * mac * factor_malla         
size_boi_fine   = 0.0061 * mac * factor_malla         
size_boi_medium = 0.0122 * mac * factor_malla         
mesh_min_size   = 0.00004 * mac * factor_malla        
mesh_max_size   = 0.545 * semi_span 

# Capa límite en 2 etapas
total_inflation_layers = 45
initial_constant_layers = 2
outer_inflation_layers = total_inflation_layers - initial_constant_layers
inflation_growth_rate = 1.09

boi_fine_growth_rate = 1.00
boi_medium_growth_rate = 1.05
global_growth_rate = 1.08

# ETIQUETAS ESTRICTAS EN INGLÉS (Alineadas con el nuevo XML)
LABEL_UAV = ["*uav_surface*"]
LABEL_BOI_FINE = ["*inner_boi*"]
LABEL_BOI_MEDIUM = ["*middle_boi*"]

print("\n----------------------------------------------------")
print("RESUMEN DE PARÁMETROS FINAL:")
print(f" -> Ruta base de exportación: {output_dir}")
print(f" -> Geometría seleccionada: {archivo_geometria}")
print(f" -> Nivel de Malla: Nivel {opcion_malla} ({nombre_nivel}) | Factor: {factor_malla:.2f}")
print(f" -> MAC: {mac:.4f} m | Semi-envergadura (b/2): {semi_span:.4f} m")
print(f" -> Primera capa (y1): {first_layer_height:.6e} m")
print(f" -> Capas de inflación: {initial_constant_layers} uniformes + {outer_inflation_layers} exponenciales")
print(f" -> Archivo de salida: {mesh_output_path}")
print("----------------------------------------------------\n")

# ---------------------------------------------------------
# 10. EJECUCIÓN DE FLUENT MESHING (Poly-Hexcore)
# ---------------------------------------------------------
print("[+] Lanzando Ansys Fluent en modo Meshing (6 Núcleos)...")
meshing_session = pyfluent.launch_fluent(
    product_version=FluentVersion.v252,
    mode=FluentMode.MESHING,
    precision=Precision.DOUBLE,
    processor_count=6,
    ui_mode=UIMode.NO_GUI_OR_GRAPHICS
)

meshing_session.journal.start(file_name=os.path.join(output_dir_nivel, f"uav_mq9_{nombre_nivel}.py"))
watertight = meshing_session.watertight()

# STEP 1: IMPORTAR GEOMETRÍA
print(f"[+] Cargando geometría: {os.path.basename(archivo_geometria)}...")
watertight.import_geometry.arguments.set_state({
    "ImportType": "Single File",
    "FileName": archivo_geometria,
    "LengthUnit": "m"
})
watertight.import_geometry()

# STEP 2: CONTROLES DE TAMAÑO LOCAL PARAMETRIZADOS (Nombres en inglés)
print("[+] Aplicando controles de tamaño local...")

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

# STEP 3: CREAR MALLA SUPERFICIAL
print("[+] Generando malla superficial...")
surf_controls = watertight.create_surface_mesh.arguments.cfd_surface_mesh_controls
surf_controls.min_size.set_state(float(mesh_min_size))
surf_controls.max_size.set_state(float(mesh_max_size))
surf_controls.growth_rate.set_state(float(global_growth_rate))
surf_controls.size_functions.set_state("Curvature and Proximity")
surf_controls.scope_proximity_to.set_state("edges-and-faces")

watertight.create_surface_mesh()

# STEP 4: DESCRIBIR GEOMETRÍA Y SHARE TOPOLOGY
print("[+] Compartiendo topología y definiendo región de fluido...")
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

# STEP 5: ACTUALIZAR FRONTERAS (Alineadas con XML)
print("[+] Asignando tipos de frontera...")
watertight.update_boundaries.arguments.set_state({
    "BoundaryLabelList": [
        "inlet", "outlet", "*close_wall*", "far_wall", "bottom", "top", "*uav_surface*"
    ],
    "BoundaryLabelTypeList": [
        "velocity-inlet", "pressure-outlet", "symmetry", "symmetry", "symmetry", "symmetry", "wall"
    ]
})
watertight.update_boundaries()

# STEP 6: ACTUALIZAR REGIONES
print("[+] Procesando dominios volumétricos...")
watertight.update_regions()

# STEP 7: CAPA LÍMITE ESTRUCTURADA EN 2 ETAPAS
print(f"[+] Configurando Capa Límite ({initial_constant_layers} capas uniformes + {outer_inflation_layers} capas exponenciales)...")

watertight.add_boundary_layer.arguments.set_state({
    "AddChild": "yes",
    "BLControlName": "bl_constant_first_layers",
    "OffsetMethodType": "first-layer-height",
    "FirstHeight": first_layer_height,
    "NumberOfLayers": initial_constant_layers,
    "Rate": 1.00,
    "BlLabelList": LABEL_UAV
})
watertight.add_boundary_layer.add_child_and_update()

watertight.add_boundary_layer.arguments.set_state({
    "AddChild": "yes",
    "BLControlName": "bl_outer_growth_layers",
    "OffsetMethodType": "first-layer-height",
    "FirstHeight": first_layer_height,
    "NumberOfLayers": outer_inflation_layers,
    "Rate": inflation_growth_rate,
    "BlLabelList": LABEL_UAV
})
watertight.add_boundary_layer.add_child_and_update()

# STEP 8: CREAR MALLA VOLUMÉTRICA Poly-Hexcore
print("[+] Generando volumen Poly-Hexcore...")
vol_mesh_args = watertight.create_volume_mesh.arguments
vol_mesh_args.volume_fill.set_state("poly-hexcore")
vol_mesh_args.volume_fill_controls.hex_max_cell_length.set_state(float(mesh_max_size))

watertight.create_volume_mesh()

# STEP 9: EXPORTACIÓN
print(f"[+] Guardando malla en: {mesh_output_path}")
meshing_session.tui.file.write_mesh(mesh_output_path)

meshing_session.journal.stop()
meshing_session.exit()

print("\n====================================================")
print(f"[***] MALLADO NIVEL {opcion_malla} ({nombre_nivel}) COMPLETADO Y EXPORTADO [***]")
print("====================================================")