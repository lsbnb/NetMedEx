HTML_TEMPLATE = """<!DOCTYPE html>
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

  body {{
    background-color: #eeeeee;
  }}

  #cy {{
      width: 98%;
      height: 98%;
      position: absolute;
  }}

  #legend-container {{
      position: absolute;
      padding: 5px;
      background-color: #eeeeee;
      border: 1px solid #585858;
      bottom: 50px;
      right: 50px;
      z-index: 100;
  }}

  .legend-box {{
    display: grid;
    grid-template-columns: 1fr 2fr;
    align-items: center;
    justify-items: center;
    width: 130px;
  }}

  .legend-box p {{
      margin: 0;
      font-size: 12px;
  }}
</style>
<body>
<div id="cy"></div>
<div id="legend-container">
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-1{{fill:#fd8d3c;}}</style></defs><rect class="cls-1" x="22.5" y="22.5" width="75" height="75" transform="translate(60 -24.85) rotate(45)"/></svg>
    <p>Species</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-2{{fill:#67a9cf;}}</style></defs><circle class="cls-2" cx="60" cy="60" r="45"/></svg>
    <p>Chemical</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-3{{fill:#74c476;}}</style></defs><polygon class="cls-3" points="60 20 13.81 100 106.19 100 60 20"/></svg>
    <p>Gene</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-4{{fill:#8c96c6;}}</style></defs><rect class="cls-4" x="17.5" y="17.5" width="85" height="85" rx="23.84"/></svg>
    <p>Disease</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-5{{fill:#bdbdbd;}}</style></defs><polygon class="cls-5" points="60.17 102.5 109.08 17.5 60.17 39.19 10.93 17.5 60.17 102.5"/></svg>
    <p>CellLine</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-6{{fill:#fccde5;}}</style></defs><polygon class="cls-6" points="104.5 110 37.83 110 15.5 10 82.17 10 104.5 110"/></svg>
    <p>DNAMutation</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-7{{fill:#fa9fb5;}}</style></defs><polygon class="cls-7" points="85 16.7 35 16.7 10 60 35 103.3 85 103.3 110 60 85 16.7"/></svg>
    <p>ProteinMutation</p>
  </div>
  <div class="legend-box">
    <svg width="25px" height="25px" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-8{{fill:#ffffb3;}}</style></defs><polygon class="cls-8" points="79.13 13.81 40.87 13.81 13.81 40.87 13.81 79.13 40.87 106.19 79.13 106.19 106.19 79.13 106.19 40.87 79.13 13.81"/></svg>
    <p>SNP</p>
  </div>
</div>
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
