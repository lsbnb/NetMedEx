# Reference for Parameters in NetMedEx

### Source (web app only)

* `PubTator3 API`: Search articles and generate networks from biological annotations in the collected articles

* `PubTator File`: Generate networks from the annotation file (PubTator File), available via the `PubTator` button (see [Search Articles and Generate Networks](web_app_guides.md#search-articles-and-generate-networks-default)).


### Search Type

CLI: `netmedex search`

* `Text Search` (`-q`, `--query`): Use keywords to retrieve relevant articles 
    - Examples:
        - "COVID 19" AND "PON1"
        - "liver cancer" AND "sorafenib"  
    - Note: Use double quotes to match whole words and AND/OR to combine keywords.

* `PMID` (`-p`, `--pmids`): Retrieve articles by PubMed Identifier (PMID)
    - Examples: 26578185,26952367
    - Note: Separate PMIDs by commas.

* `PMID File` (`-f`, `--pmid_file`): Retrieve articles by a text file of PMIDs
    - Note: One PMID per line 

### Sort

CLI: `netmedex search`

* `Relevance` (`--sort score`): Sort articles in descending order by relevance score (see how search results are prioritized in the <a href="https://academic.oup.com/nar/article/52/W1/W540/7640526" target="_blank">PubTator3 Paper</a>)

* `Recency` (`--sort date`): Sort articles in descending order by publication date 

This parameter affects the retrieved articles if the total number exceeds [Max Articles](#max-articles).

### PubTator3 Parameters

CLI: `netmedex search`

* `Use MeSH Vocabulary` (`--mesh`): If enabled, standardize the text in the original content using MeSH vocabulary. If disabled, the text is lowercased and standardized using plural stemming.

* `Full Text` (`--full_text`): If enabled, retrieve full-text annotations if available. If disabled, collect annotations from abstracts only.
    - For articles where only abstracts are available, annotations will be collected from the abstracts. As a result, the network may be generated from a mix of full-text articles and abstracts if this parameter is enabled.

### Max Articles

CLI: `netmedex search`

* `Max Articles` (`--max_articles`): Specify the maximum number of articles to retrieve.
    - This parameter applies to `Text Search` only. If search results exceed `MAX_ARTICLES`, only the top `MAX_ARTICLES` will be retrieved after sorting.

### Node Filter (Node Type)

CLI: `netmedex network`

* `All` (`--node_type all`): Retain all annotations (biological concepts with or without standardized MeSH terms).

* `MeSH` (`--node_type mesh`): Retain annotations with standardized MeSH terms only.

* `BioREx Relation` (`--node_type relation`): Retain only the annotations with high-confidence relationships as predicted by the <a href="https://www.sciencedirect.com/science/article/pii/S1532046423002083?via%3Dihub" target="_blank">BioREx model</a> used in PubTator3. This results in a network that is not co-mention-based.

### Weighting Method

CLI: `netmedex network`

* `Frequency` (`--weighting_method freq`): Calculate edge weights using co-occurrence counts.

* `NPMI` (`--weighting_method npmi`): Calculate edge weights using normalized pointwise mutual information (NPMI).
    - Edges will be assigned high weights if the concepts co-occur frequently. For exmaple, biological concepts that co-occur in only a few articles can still have a high edge weight if they almost always co-occur whenever each concept appears in an article.
    - The calculated NPMI ranges from `-1` to `1`. The weight is set to `0` for negative values. 
    - This option is still experimental and requires further optimization.    

### Edge Weight Cutoff

CLI: `netmedex network`

* `Edge Weight Cutoff` (`--cut_weight INT`): Set the minimum edge weight to filter the graph.
    - Raw edge weights (calculated using `Frequency` or `NPMI`) are scaled linearly between `0` and `20`. 
    - If set to `0`, all edges are included.

See also [Max Edges](#max-edges), which directly limits the number of edges.


### Max Edges

* `Max Edges` (`--max_edges INT`): Set the maximum number of edges in the graph.
    - After sorting edges by weight, only the top `MAX_EDGES` are retained. Isolated nodes are removed.
    - If set to `0`, all edges are included.


### Network Parameters

* `Community` (`--community`): Group nodes into communities by the <a href="https://iopscience.iop.org/article/10.1088/1742-5468/2008/10/P10008" target="_blank">Louvain algorithm</a>.
    - In essence, the Louvain algorithm groups nodes into communities that maximize intra-community links and minimize inter-community links.
    - This option is useful for visualizing dense networks.
    - Edges between nodes in separate communities are collapsed into a single community edge.
    - If enabled, the generated network currently cannot be exported in `XGMML` format.

* `--pmid_weight PMID_WEIGHT_FILE` (CLI only): Path to the CSV file for the article weights.

Example CSV file (`pmid_weight.csv`):
```
26578185,1
26952367,2
```


### Network Output Format

* `HTML` (`--format html`): Export the network in HTML format.

* `XGMML` (`--format xgmml`):  Export the network in a Cytoscape-compatible format.
    - This generated file can be opened in <a href="https://cytoscape.org/" target="_blank">Cytoscape</a> for further analysis.

* `--format json` (CLI only): Export the network info in JSON format.


### Network Visualization Tools (web app only)

* `Graph Layout`: Adjust the graph layout.

* `Edge Weight Cutoff`: Dynamically adjust edge weight cutoff without resubmitting inputs. (See [Edge Weight Cutoff](#edge-weight-cutoff))

* `Minimum Node Degree`: Set the minimum node degree to filter the graph. 
    - This option is useful for identifying hubs and their connections. 
