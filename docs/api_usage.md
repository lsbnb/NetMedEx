# Python API Usage

NetMedEx supports Python **3.11** and above. This page demonstrates how to use the library programmatically. The `PubTatorAPI` class retrieves articles from PubTator3, and `PubTatorGraphBuilder` constructs the co-occurrence network.

## Retrieve Articles

```python
from netmedex.pubtator import PubTatorAPI

collection = PubTatorAPI(
    query='"covid-19" AND "PON1"',
    sort="score",
    max_articles=100,
).run()
```

## Save and Load Collections

```python
import json

# Save to JSON
with open("collection.json", "w") as f:
    json.dump(collection.to_json(), f)

# Load from JSON
from netmedex.pubtator_data import PubTatorCollection
with open("collection.json") as f:
    loaded = PubTatorCollection.from_json(json.load(f))

# Or load from a PubTator file
from netmedex.pubtator_parser import PubTatorIO
loaded = PubTatorIO.parse("collection.pubtator")
```

## Build and Export a Network

```python
from netmedex.graph import PubTatorGraphBuilder, save_graph

builder = PubTatorGraphBuilder(node_type="all")
builder.add_collection(loaded)
graph = builder.build(weighting_method="freq", edge_weight_cutoff=1)

save_graph(graph, "network.html", output_filetype="html")
```

The notebook `notebooks/netmedex_usage.ipynb` contains a complete demonstration of these steps.
