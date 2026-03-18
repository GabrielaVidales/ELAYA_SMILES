# 🌌 ELAYA-SMILES  
### Molecular Intelligence from Text to Structure

<p align="center">
  <img src="pictures/Logo_Elaya.jpg" width="180" alt="ELAYA Logo"/>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/badge/RDKit-Chemoinformatics-green?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/OpenBabel-Conversion-orange?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/ANI-Neural_Potentials-purple?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Status-Active-success?style=for-the-badge"/>
</p>

<p align="center">
  <b>Transform SMILES into accurate 3D molecular structures with AI-enhanced conformational exploration.</b>
</p>

---

## ✨ Overview

**ELAYA-SMILES** is a computational framework designed to convert **SMILES strings** into realistic **3D molecular geometries**, enabling downstream applications in:

- 🧬 Molecular Dynamics  
- ⚛️ Quantum Chemistry  
- 🧪 Drug Discovery  
- 🤖 Machine Learning on molecular properties  

It integrates classical cheminformatics with modern **AI-based potentials** to efficiently explore conformational space.

---

## 🧠 Key Features

🔹 **SMILES → 3D Conversion**  
Generate reliable 3D conformations from text-based molecular representations.

🔹 **Advanced Conformer Search (GLOMOS)**  
Genetic algorithm for exploring low-energy conformational landscapes.

🔹 **AI-Powered Optimization (ANI)**  
Near quantum-level accuracy for organic molecules at a fraction of the computational cost.

🔹 **Multiple Backends**
- RDKit (ETKDGv3)
- OpenBabel
- Graph-based approximations (NetworkX)

🔹 **Reproducibility**
- Deterministic workflows using fixed random seeds

---

## ⚙️ Methodology

### 🧪 1. Molecular Parsing
- SMILES → Molecular graph  
- Hydrogen completion  

### 🔺 2. Initial 3D Embedding
- **ETKDGv3** (distance geometry + torsional knowledge)

### 🔄 3. Conformational Exploration
- Genetic algorithm (GLOMOS)
- Sampling diverse conformers

### ⚛️ 4. Energy Minimization
- Classical force fields:
  - UFF  
  - MMFF94  

### 🤖 5. AI Refinement
- ANI neural network potentials  
- Fast approximation of quantum energies  

---

## 🧬 Scientific Background

### 🔹 Conformers
Molecules exist as ensembles of interconverting 3D structures due to rotation around single bonds.

### 🔹 Force Fields
Approximate molecular energy using parameterized functions (bonded + non-bonded interactions).

### 🔹 ANI Potentials
Neural networks trained on quantum data to predict molecular energies efficiently.

---

## 👩‍🔬 Desarrollo

Este sistema ha sido desarrollado por **Gabriela Vidales** como parte de un esfuerzo por integrar herramientas de código abierto con flujos de trabajo reproducibles para la representación y análisis molecular tridimensional.

Se agradece especialmente el apoyo del Dr. Filiberto Ortiz Chi y el Dr. Luis Ortiz por su valiosa orientación durante el desarrollo de esta herramienta.
