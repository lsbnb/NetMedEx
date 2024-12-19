## Command-Line Interface (CLI)

To generate a network, run `netmedex search` first to retrieve relevant articles and then run `netmedex network` to generate the network.

#### Search PubMed Articles

Use the CLI to search articles containing specific biological concepts via the [PubTator3 API](https://www.ncbi.nlm.nih.gov/research/pubtator3/api):

```bash
# Query with keywords and sort articles by relevance (default: recency)
netmedex search -q '"N-dimethylnitrosamine" AND "Metformin"' [-o OUTPUT_FILEPATH] --sort score

# Query with article PMIDs
netmedex search -p 34895069,35883435,34205807 [-o OUTPUT_FILEPATH]

# Query with article PMIDs (from file)
netmedex search -f examples/pmids.txt [-o OUTPUT_FILEPATH]

# Query with PubTator3 Entity ID and limit the number of articles to 100
netmedex search -q '"@DISEASE_COVID_19" AND "@GENE_PON1"' [-o OUTPUT_FILEPATH] --max_articles 100
```

*Note: Use double quotes for keywords containing spaces and logical operators (e.g., AND/OR) to combine keywords.*

Available commands are detailed in [Search Command](#search-command).

#### Generate Co-Mention Networks

The PubTator file outputs from `netmedex search` is used to generate the network.

```bash
# Use default parameters and set edge weight cutoff to 1
netmedex network -i examples/pmids_output.pubtator -o pmids_output.html -w 1

# Keep MeSH terms and discard non-MeSH terms
netmedex network -i examples/pmids_output.pubtator -o pmids_output.html -w 1 --node_type mesh

# Keep confident relations between entities
netmedex network -i examples/pmids_output.pubtator -o pmids_output.html -w 1 --node_type relation

# Save the result in XGMML format for Cytoscape
netmedex network -i examples/pmids_output.pubtator -o pmids_output.xgmml -w 1 -f xgmml

# Use normalized pointwise mutual information (NPMI) to weight edges
netmedex network -i examples/pmids_output.pubtator -o pmids_output.html -w 5 --weighting_method npmi
```

Available commands are detailed in [Network Command](#network-command).

#### View the Network

- **HTML Output**: Open in a browser to view the network.
- **XGMML Output**: Import into Cytoscape for further analysis.

## Available Commands

### General

```bash
usage: netmedex [-h] {search,network,run} ...

positional arguments:
  {search,network,run}
    search              Search PubMed articles and obtain annotations
    network             Build a network from annotations
    run                 Run NetMedEx app

options:
  -h, --help            Show this help message and exit
```

### Search Command

```bash
usage: netmedex search [-h] [-q QUERY] [-o OUTPUT] [-p PMIDS] [-f PMID_FILE] [-s {score,date}] [--max_articles MAX_ARTICLES] [--full_text]
                       [--use_mesh] [--debug]

options:
  -h, --help            Show this help message and exit
  -q QUERY, --query QUERY
                        Query string
  -o OUTPUT, --output OUTPUT
                        Output path (default: [CURRENT_DIR].pubtator)
  -p PMIDS, --pmids PMIDS
                        PMIDs for the articles (comma-separated)
  -f PMID_FILE, --pmid_file PMID_FILE
                        Filepath to load PMIDs (one per line)
  -s {score,date}, --sort {score,date}
                        Sort articles in descending order (default: date)
  --max_articles MAX_ARTICLES
                        Maximum articles to request (default: 1000)
  --full_text           Collect full-text annotations if available
  --use_mesh            Use MeSH vocabulary instead of common text
  --debug               Print debug information
```

### Network Command

```bash
usage: netmedex network [-h] [-i INPUT] [-o OUTPUT] [-w CUT_WEIGHT] [-f {xgmml,html,json}] [--node_type {all,mesh,relation}]
                        [--weighting_method {freq,npmi}] [--pmid_weight PMID_WEIGHT] [--debug] [--community] [--max_edges MAX_EDGES]

options:
  -h, --help            Show this help message and exit
  -i INPUT, --input INPUT
                        Path to the pubtator file
  -o OUTPUT, --output OUTPUT
                        Output path (default: [INPUT_DIR].[FORMAT_EXT])
  -w CUT_WEIGHT, --cut_weight CUT_WEIGHT
                        Discard edges with weight smaller than the specified value (default: 2)
  -f {xgmml,html,json}, --format {xgmml,html,json}
                        Output format (default: html)
  --node_type {all,mesh,relation}
                        Keep specific types of nodes (default: all)
  --weighting_method {freq,npmi}
                        Weighting method for network edges (default: freq)
  --pmid_weight PMID_WEIGHT
                        CSV file for the article weights (default: 1)
  --debug               Print debug information
  --community           Divide nodes into communities using the Louvain method
  --max_edges MAX_EDGES
                        Maximum number of edges (default: 0, no limit)
```

More detailed explanation of each command is available in [Reference](reference.md).