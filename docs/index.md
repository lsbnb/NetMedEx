# About NetMedEx

![NetMedEx](./assets/NetMedEx.png)

NetMedEx is a Python-based tool designed to extract BioConcept entities (e.g., genes, diseases, chemicals, and species) from Pubtator files generated by [Pubtator3](https://www.ncbi.nlm.nih.gov/research/pubtator3/). It calculates the frequency of BioConcept pairs (e.g., gene-gene, gene-chemical, chemical-disease) based on co-mentions in publications and generates a co-mention interaction network. These networks can be viewed in a browser or imported into [Cytoscape](https://cytoscape.org/) for advanced visualization and analysis.


## Getting Started

NetMedEx offers three ways for users to interact with the tool:

1. [Web Application (via Docker)](installation.md#web-application-via-docker)
2. [Web Application (Local)](installation.md#web-application-local)
3. [Command-Line Interface (CLI)](installation.md#command-line-interface-cli)