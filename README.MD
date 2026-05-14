Task Definition: Project PaperGen
Overview
The objective is to design and implement an automated pipeline for generating academic research papers. This system must bridge the gap between raw experimental data and publication-ready documents (IEEE, Springer, Elsevier standards).

Infrastructure & Resource Allocation
Controller (Local): A Python-based orchestration layer running on the development environment (laptop/workstation). This handles logic, API coordination, and file management.

High-Performance Compute (Remote Server): Access to an NVIDIA A30 GPU located on a remote server. This resource is dedicated to:

Running domain-specific LLMs (e.g., Llama-3, Mistral) for technical validation.

Processing heavy inference tasks that require data privacy (preventing sensitive lab data from leaving the controlled environment).

Performing factual consistency and plagiarism checks.

Cloud Intelligence (APIs): Integration with Claude and Gemini for linguistic synthesis, abstract generation, and high-level structural drafting.

Core Requirements
Automated Ingestion: Systematically collect and preprocess diverse data types: lab notes (text), experimental results (CSV/JSON), and reference materials (PDF).

Hybrid Modeling: Orchestrate a flow that routes "creative/linguistic" tasks to Cloud APIs and "technical/private" tasks to the remote A30 GPU.

Academic Integrity: Implement modules for rigorous citation management, plagiarism detection, and technical accuracy verification.

Standardized Output: Final generation must be compatible with LaTeX templates for major academic publishers.

Scalability: The architecture must be modular, allowing for future expansion into different research domains or multilingual support.

Development Standards
Strict Modularity: Every component (Ingestion, Writing, Validation, Formatting) must be isolated.

Documentation: Every directory within the project must contain a README.md defining its specific role in the pipeline.

Remote Synergy: The project must handle the communication between the local controller and the remote A30 server efficiently.