<p align="center">
  <img src="pictures/Logo_Elaya.jpg" width="240">
</p>

<h1 align="center">
ELAYA SMILES 
  (Energy-minimized Linear-to-structure Atom Yielding Algorithm)
</h1>

<p align="center">
<b>Molecular Conversion and 3D Structural Analysis Platform</b>
</p>

<p align="center">
<a href="https://elaya-smiles.onrender.com/">
🌐 Try the Web App
</a>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![RDKit](https://img.shields.io/badge/RDKit-Compatible-green)
![OpenBabel](https://img.shields.io/badge/OpenBabel-Supported-orange)
![Visualization](https://img.shields.io/badge/Py3Dmol-Enabled-red)
![Status](https://img.shields.io/badge/Status-Active-success)

</p>

---

## What is ELAYA SMILES?

**ELAYA SMILES is a web-based platform designed for the conversion of linear molecular representations (SMILES) into optimized three-dimensional structures, enabling visualization and structural analysis within a unified environment.**

---

## 🌐 Purpose and Relevance

SMILES (Simplified Molecular Input Line Entry System) provides a compact and efficient way to represent molecular structures as text. However, many computational chemistry applications—such as molecular simulations, docking, and property prediction—require accurate 3D geometries.

**ELAYA SMILES facilitates this transformation** by integrating multiple cheminformatics tools to generate reliable 3D conformations, supporting both research and educational workflows in molecular modeling.

---

## 🚀 Core Features

- Conversion of SMILES strings into 3D molecular structures using:
  - RDKit (ETKDGv3)
  - OpenBabel
  - NetworkX (topological approximation)
- Interactive 3D molecular visualization
- Export of generated structures in `.xyz` format
- User-friendly web interface for rapid molecular exploration

---

## ⚗️ Scientific Highlights

- **Multi-method SMILES → 3D conversion**  
  Combines established cheminformatics approaches for flexible structure generation.

- **Distance geometry with torsional knowledge (ETKDGv3)**  
  Produces realistic conformations using experimental and knowledge-based constraints.

- **Force field-based optimization**  
  Geometry refinement using classical methods such as UFF and MMFF94.

- **Graph-based structural approximation**  
  NetworkX provides topology-based layouts useful for visualization, though not physically accurate.

---

## 🧬 Scientific Background

### 🔹 Conformational Flexibility
Molecules exist as ensembles of interconverting conformers due to rotation around single bonds. Identifying low-energy conformations is essential for understanding molecular behavior.

### 🔹 Molecular Geometry
Accurate 3D structures are critical for:
- Molecular dynamics simulations  
- Structure-based drug design  
- Quantum-chemical calculations  

---

## 🧰 Technologies

- **Backend:** Flask, Flask-CORS  
- **Cheminformatics:** RDKit, OpenBabel  
- **Visualization:** Py3Dmol  
- **Frontend:** HTML5, CSS3, JavaScript  

---

## 👩‍🔬 Development

Developed by **Gabriela Yasmin Vidales Ayala** as part of an initiative to bridge cheminformatics tools with accessible, reproducible workflows for molecular modeling.

Special thanks to **Dr. Filiberto Ortiz Chi** and **Dr. Luis Ortiz** for their scientific guidance and support.
