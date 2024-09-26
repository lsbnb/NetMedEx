import networkx as nx
import json

CYTOSCAPE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cytoscape Network</title>
</head>
<style>
  * {{
    padding: 0;
    margin: 0;
    box-sizing: border-box;
  }}

  #cy {{
      width: 98%;
      height: 98%;
      position: absolute;
  }}
</style>
<body>
<div id="cy"></div> 
</body>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.1/cytoscape.min.js"></script>
<script>
  let cy = cytoscape({{
    container: document.getElementById("cy"),
    elements: {cytoscape_js},
    layout: {{"name": "{layout}"}},
    style: [
    {{
      selector: "node",
      style: {{
        "text-valign": "center",
        "label": "data(label)",
        "shape": "data(shape)",
        "color": "data(label_color)",
        "background-color" : "data(color)",
      }},
    }},
    {{
      selector: ":parent",
      style: {{
        "background-opacity": 0.3,
      }},
    }},
    {{
      selector: "edge",
      style: {{
        "width": "data(weight)",
      }},
    }},
    {{
      selector: ".top-center",
      style: {{
        "text-valign": "top",
        "text-halign": "center",
        "font-size": "20px",
      }},
    }}
  ]
  }})
</script>
</html>
"""


def save_as_html(G: nx.Graph, savepath: str, layout="preset"):
    with open(savepath, "w") as f:
        cytoscape_js = create_cytoscape_js(G)
        f.write(CYTOSCAPE_TEMPLATE.format(cytoscape_js=cytoscape_js, layout=layout))


def create_cytoscape_js(G: nx.Graph):
    elements = []
    for node in G.nodes(data=True):
        elements.append(create_cytoscape_node(node))

    for edge in G.edges(data=True):
        elements.append(create_cytoscape_edge(edge, G))

    return json.dumps(elements)


def create_cytoscape_node(node):
    node_id, node_attr = node

    node_info = {
        "data": {
            "id": node_attr["_id"],
            "parent": node_attr.get("parent", None),
            "color": node_attr["color"],
            "label_color": node_attr["label_color"],
            "label": node_attr["name"],
            "shape": node_attr["shape"].lower(),
        },
        "position": {
            "x": round(node_attr["pos"][0], 3),
            "y": round(node_attr["pos"][1], 3),
        }
    }

    # Community nodes
    if node_attr["_id"].startswith("c"):
        node_info["classes"] = "top-center"

    return node_info


def create_cytoscape_edge(edge, G):
    node_id_1, node_id_2, edge_attr = edge

    edge_info = {
        "data": {
            "id": edge_attr["_id"],
            "source": G.nodes[node_id_1]["_id"],
            "target": G.nodes[node_id_2]["_id"],
            "label": f"{G.nodes[node_id_1]['name']} (interacts with) {G.nodes[node_id_2]['name']}",
            "weight": round(float(edge_attr["scaled_edge_weight"]), 1),
        }
    }
    return edge_info
