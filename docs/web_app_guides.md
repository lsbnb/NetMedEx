## Web Application

This is the typical interface when you open the app in your browser.

![NetMedEx Interface](./assets/netmedex_interface.jpeg)

*Note: The interface may differ slightly between versions.*


The interface consists of a sidebar (background: <span style="display:inline-block; width:10px; height:10px; background-color:#518c9c;"></span>) and a region for network display (background: <span style="display:inline-block; width:10px; height:10px; background-color:#eeeeee;"></span>).

## Usage

### Search Articles and Generate Networks (Default) 
1. Select `PubTator3 API` in Source.  
2. Select your [Search Type](reference.md#search-type-web-app).  
3. Enter the corresponding inputs in the box below.  
4. Adjust parameters in the sidebar and the config (<img src="assets/icon_config.svg" alt="config_icon" width="10px"/>) as needed (see [Reference](reference.md)).  
5. Press `Submit`.  

>Step 3 note: If your search type is `Text Search`, use double quotes for keywords containing spaces and logical operators (e.g., AND/OR) to combine keywords. For example, "COVID 19" AND "PON1".

Once the program finishes generating the network, it will be displayed on the right-hand side:

![NetMedEx Network](assets/netmedex_network.png)

*Note: The default layout may display nodes overlapping with others. You can manually drag the nodes to arrange them as desired.*

In the top-right corner, there are buttons to download the network and adjust settings:

* `PubTator`: Download the PubTator file for reuse (see [Generate Networks from PubTator Files](#generate-networks-from-pubtator-files)).  
* `HTML`: Export the network in HTML format.
* `XGMML`: Export the network in a Cytoscape-compatible format (see [Network Output Format](reference.md#network-output-format)).
* &#8943; : Graph settings for adjusting graph layout, edge weight cutoff, minimum node degree, etc (see [Network Visualization Tools](reference.md#network-visualization-tools)). 

>Tip: Adjusting `edge weight cutoff` is particularly useful if you think the current network is overcrowded or too sparse.


#### Interactive Network

The nodes in the network can be dragged around. Additionally, when you click on an edge, its information is displayed in the box at the bottom.

![NetMedEx Edge Info](assets/netmedex_edge-info.png)

The evidence for the co-occurrence of two biological concepts that constitute the edge will be displayed as a table. This table is available as a CSV file.

If the `Community` parameter is enabled, the edges between nodes in different communities will be collapsed into a single community edge, which may include a long list of articles. To identify the evidence for nodes in separate communities, please disable the `Community` parameter and generate the network again.

### Generate Networks from PubTator Files

The downloaded PubTator files can be reused to generate networks without performing article searches. To generate networks from PubTator files:

1. Select `PubTator File` in Source.  
2. Upload the PubTator file.  
2. Adjust the parameters as needed (see [Reference](reference.md)).  
3. Press `Submit`.  