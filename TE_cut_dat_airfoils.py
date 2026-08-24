"""
==============================================================================
AIRFOIL TRAILING EDGE CUTTER & RENORMALIZER
==============================================================================
This script reads an airfoil coordinate file in Selig/UIUC format (.dat),
applies a straight vertical cut at a designated chord position (defaulting 
to 99% chord, x_cut = 0.99 for a 1% truncation), and optionally renormalizes 
the modified profile so the chord length spans exactly from x = 0 to x = 1. 
Finally, it exports the new coordinates to a .dat file and plots a comparison 
between the original and modified airfoils.
==============================================================================
"""

import os
import numpy as np
import matplotlib.pyplot as plt

def read_dat(filepath):
    """Reads an airfoil .dat file (Selig/UIUC format)."""
    coords = []
    name = "Airfoil"
    with open(filepath, 'r') as f:
        lines = f.readlines()
        name = lines[0].strip()
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) == 2:
                try:
                    coords.append([float(parts[0]), float(parts[1])])
                except ValueError:
                    continue
    return name, np.array(coords)

def save_dat(filepath, name, coords):
    """Saves modified coordinates to a new .dat file."""
    with open(filepath, 'w') as f:
        f.write(f"{name} - Flat Trailing Edge (1% Cut)\n")
        for x, y in coords:
            f.write(f"  {x:10.6f}  {y:10.6f}\n")

def cut_trailing_edge(coords, x_cut=0.99, renormalize=True):
    """Performs a straight cut at the trailing edge (default 1% cut at x = 0.99)."""
    idx_le = np.argmin(coords[:, 0])
    
    upper_surface = coords[:idx_le + 1]
    lower_surface = coords[idx_le:]
    
    # Exact interpolation at x_cut
    idx_upper_sort = np.argsort(upper_surface[:, 0])
    y_upper_cut = np.interp(x_cut, upper_surface[idx_upper_sort, 0], upper_surface[idx_upper_sort, 1])
    
    idx_lower_sort = np.argsort(lower_surface[:, 0])
    y_lower_cut = np.interp(x_cut, lower_surface[idx_lower_sort, 0], lower_surface[idx_lower_sort, 1])
    
    # Filter and insert cut points
    upper_filtered = upper_surface[upper_surface[:, 0] <= x_cut]
    lower_filtered = lower_surface[lower_surface[:, 0] <= x_cut]
    
    new_upper_surface = np.vstack(([x_cut, y_upper_cut], upper_filtered))
    new_lower_surface = np.vstack((lower_filtered, [x_cut, y_lower_cut]))
    
    new_coords = np.vstack((new_upper_surface, new_lower_surface[1:]))
    
    # Renormalize chord length from 0 to 1
    if renormalize:
        x_min = np.min(new_coords[:, 0])
        new_coords[:, 0] = (new_coords[:, 0] - x_min) / (x_cut - x_min)
        
    return new_coords

# ==========================================
# DIRECT EXECUTION
# ==========================================
if __name__ == "__main__":
    # Direct path specification
    input_file = r"C:\Users\victo\OneDrive\Desktop\Tesis_MQ9\Perfiles\NACA4415.dat"
    
    # Generate output path in the same folder
    base_path, ext = os.path.splitext(input_file)
    output_file = f"{base_path}_straight_cut_1pct{ext}"

    # Verify that file exists
    if not os.path.exists(input_file):
        print(f"ERROR: File not found at path:\n{input_file}")
    else:
        # Process (1% cut at x_cut = 0.99)
        name, original_coords = read_dat(input_file)
        modified_coords = cut_trailing_edge(original_coords, x_cut=0.99, renormalize=True)
        
        # Save
        save_dat(output_file, name, modified_coords)
        
        print("Airfoil processed successfully.")
        print(f"Input file: {input_file}")
        print(f"File saved at: {output_file}")

        # Plot comparison
        plt.figure(figsize=(10, 4))
        plt.plot(original_coords[:, 0], original_coords[:, 1], 'r--', label='Original NACA4415', alpha=0.5)
        plt.plot(modified_coords[:, 0], modified_coords[:, 1], 'b-', label='Modified NACA4415 (1% Straight Cut)', linewidth=1.8)
        plt.axis('equal')
        plt.title(f"Airfoil: {name}")
        plt.xlabel("X / c")
        plt.ylabel("Y / c")
        plt.legend()
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.show()