from __future__ import annotations

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
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    overflow: hidden;
  }}

  #cy {{
      width: 100vw;
      height: 100vh;
      position: absolute;
      top: 0;
      left: 0;
      z-index: 1;
  }}

  #control-panel {{
      position: absolute;
      top: 10px;
      left: 10px;
      z-index: 100;
      background-color: rgba(255, 255, 255, 0.9);
      padding: 15px;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      width: 250px;
      border: 1px solid #ddd;
  }}

  .control-group {{
      margin-bottom: 15px;
  }}

  .control-group label {{
      display: block;
      margin-bottom: 5px;
      font-weight: 600;
      color: #333;
      font-size: 14px;
  }}

  .control-group select, 
  .control-group input[type="range"] {{
      width: 100%;
      padding: 5px;
      border-radius: 4px;
      border: 1px solid #ccc;
  }}

  .value-display {{
      float: right;
      color: #666;
  }}

  #legend-container {{
      position: absolute;
      padding: 10px;
      background-color: rgba(255, 255, 255, 0.9);
      border: 1px solid #ddd;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      bottom: 20px;
      right: 20px;
      z-index: 100;
  }}

  .legend-box {{
    display: flex;
    align-items: center;
    margin-bottom: 5px;
    width: 140px;
  }}

  .legend-box svg {{
      margin-right: 10px;
  }}

  .legend-box p {{
      margin: 0;
      font-size: 12px;
      color: #333;
  }}

  /* Info Panel Styles */
  #info-panel {{
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 100;
      background-color: rgba(255, 255, 255, 0.95);
      padding: 15px;
      border-radius: 8px;
      box-shadow: 0 2px 10px rgba(0,0,0,0.1);
      width: 300px;
      max-height: 80vh;
      overflow-y: auto;
      border: 1px solid #ddd;
      display: none;
  }}
  .info-title {{
      font-size: 16px;
      font-weight: bold;
      margin-bottom: 10px;
      padding-bottom: 5px;
      border-bottom: 2px solid #eee;
      color: #333;
  }}
  .info-row {{
      margin-bottom: 8px;
      font-size: 13px;
      color: #333;
  }}
  .info-label {{
      font-weight: 600;
      color: #666;
      margin-right: 5px;
  }}
  .pmid-list {{
      margin-top: 8px;
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
  }}
  .pmid-link {{
      display: inline-block;
      padding: 2px 6px;
      background-color: #e3f2fd;
      color: #1565c0;
      text-decoration: none;
      border-radius: 4px;
      font-size: 12px;
      transition: background-color 0.2s;
  }}
  .pmid-link:hover {{
      background-color: #bbdefb;
  }}

  #logo-container {{
      position: absolute;
      top: 10px;
      left: 50%;
      transform: translateX(-50%);
      z-index: 200;
      background-color: rgba(255, 255, 255, 0.8);
      padding: 5px 15px;
      border-radius: 8px;
      box-shadow: 0 2px 5px rgba(0,0,0,0.1);
      transition: background-color 0.3s;
  }}
  #logo-container:hover {{
      background-color: rgba(255, 255, 255, 1);
  }}
  #logo-container img {{
      display: block;
      height: 40px;
  }}
</style>
<body>

<!-- Control Panel -->
<div id="control-panel">
  <div class="control-group">
    <label>Layout Algorithm</label>
    <select id="layout-select">
      <option value="cose" selected>Cose (Physics)</option>
      <option value="circle">Circle</option>
      <option value="grid">Grid</option>
      <option value="concentric">Concentric</option>
      <option value="breadthfirst">Breadthfirst (Tree)</option>
      <option value="random">Random</option>
    </select>
  </div>
  
  <div class="control-group">
    <label>Min Degree Filter: <span id="degree-val" class="value-display">0</span></label>
    <input type="range" id="degree-slider" min="0" max="20" value="0" step="1">
  </div>
  
  <div style="font-size: 11px; color: #666; margin-top: 10px; line-height: 1.4;">
    <strong>Tips:</strong><br>
    • Scroll to zoom<br>
    • Drag background to pan<br>
    • Drag nodes to move
  </div>
</div>

<!-- Logo -->
<div id="logo-container">
  <a href="https://github.com/lsbnb" target="_blank" title="Visit GitHub Repository">
    <img src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAATIAAAA9CAYAAAAu5+WkAAAACXBIWXMAAAsTAAALEwEAmpwYAAAGq2lUWHRYTUw6Y29tLmFkb2JlLnhtcAAAAAAAPD94cGFja2V0IGJlZ2luPSLvu78iIGlkPSJXNU0wTXBDZWhpSHpyZVN6TlRjemtjOWQiPz4gPHg6eG1wbWV0YSB4bWxuczp4PSJhZG9iZTpuczptZXRhLyIgeDp4bXB0az0iQWRvYmUgWE1QIENvcmUgNy4yLWMwMDAgNzkuNTY2ZWJjNSwgMjAyMi8wNS8wOS0wNzoyMjoyOSAgICAgICAgIj4gPHJkZjpSREYgeG1sbnM6cmRmPSJodHRwOi8vd3d3LnczLm9yZy8xOTk5LzAyLzIyLXJkZi1zeW50YXgtbnMjIj4gPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bWxuczpzdEV2dD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlRXZlbnQjIiB4bWxuczp4bXA9Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC8iIHhtbG5zOmRjPSJodHRwOi8vcHVybC5vcmcvZGMvZWxlbWVudHMvMS4xLyIgeG1sbnM6cGhvdG9zaG9wPSJodHRwOi8vbnMuYWRvYmUuY29tL3Bob3Rvc2hvcC8xLjAvIiB4bXBNTTpPcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6YzUxNjg3NzUtODMxNi1jYTRmLThmMzEtODU0ZmI2NDRjODIyIiB4bXBNTTpEb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6OWM4ZGQzYmEtMjZhOC1kMzQ4LWI2MTQtNmRkZGQ1NzgxMmJiIiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOjkyZDc1ZDBkLTYxOTAtMjM0OC1hN2VmLTU4YmZjMzQ4ZDE2YyIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQaG90b3Nob3AgMjUuMyAoV2luZG93cykiIHhtcDpDcmVhdGVEYXRlPSIyMDI0LTEwLTMxVDA4OjQ3OjQ4KzA4OjAwIiB4bXA6TW9kaWZ5RGF0ZT0iMjAyNC0xMC0zMVQwODo1Njo1NSswODowMCIgeG1wOk1ldGFkYXRhRGF0ZT0iMjAyNC0xMC0zMVQwODo1Njo1NSswODowMCIgZGM6Zm9ybWF0PSJpbWFnZS9wbmciIHBob3Rvc2hvcDpDb2xvck1vZGU9IjMiPiA8eG1wTU06RGVyaXZlZEZyb20gc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDo5ZmFkZjljNi00OWU1LWNjNGItYTRiMC01NjkzNjFmNTU0YjMiIHN0UmVmOmRvY3VtZW50SUQ9InhtcC5kaWQ6YzUxNjg3NzUtODMxNi1jYTRmLThmMzEtODU0ZmI2NDRjODIyIi8+IDx4bXBNTTpIaXN0b3J5PiA8cmRmOlNlcT4gPHJkZjpsaSBzdEV2dDphY3Rpb249InNhdmVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjhmOGI3NWQxLTc5OWQtZjc0Ni1iYjkwLTVmOWMwNWFiMDMzNSIgc3RFdnQ6d2hlbj0iMjAyNC0xMC0zMVQwODo1Njo1NSswODowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIDIzLjQgKFdpbmRvd3MpIiBzdEV2dDpjaGFuZ2VkPSIvIi8+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJzYXZlZCIgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDo5MmQ3NWQwZC02MTkwLTIzNDgtYTdlZi01OGJmYzM0OGQxNmMiIHN0RXZ0OndoZW49IjIwMjQtMTAtMzFUMDg6NTY6NTUrMDg6MDAiIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCAyMy40IChXaW5kb3dzKSIgc3RFdnQ6Y2hhbmdlZD0iLyIvPiA8L3JkZjpTZXE+IDwveG1wTU06SGlzdG9yeT4gPC9yZGY6RGVzY3JpcHRpb24+IDwvcmRmOlJERj4gPC94OnhtcG1ldGE+IDw/eHBhY2tldCBlbmQ9InIiPz71PBGvAAApPElEQVR42u2dBXwU59PHJ6e5JEgICW6l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" alt="NetMedEx">
  </a>
</div>

<div id="cy"></div>

<!-- Info Panel -->
<div id="info-panel">
  <div id="info-content"></div>
</div>

<div id="legend-container">
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-1{{fill:#fd8d3c;}}</style></defs><rect class="cls-1" x="22.5" y="22.5" width="75" height="75" transform="translate(60 -24.85) rotate(45)"/></svg>
    <p>Species</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-2{{fill:#67a9cf;}}</style></defs><circle class="cls-2" cx="60" cy="60" r="45"/></svg>
    <p>Chemical</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-3{{fill:#74c476;}}</style></defs><polygon class="cls-3" points="60 20 13.81 100 106.19 100 60 20"/></svg>
    <p>Gene</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-4{{fill:#8c96c6;}}</style></defs><rect class="cls-4" x="17.5" y="17.5" width="85" height="85" rx="23.84"/></svg>
    <p>Disease</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-5{{fill:#bdbdbd;}}</style></defs><polygon class="cls-5" points="60.17 102.5 109.08 17.5 60.17 39.19 10.93 17.5 60.17 102.5"/></svg>
    <p>CellLine</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-6{{fill:#fccde5;}}</style></defs><polygon class="cls-6" points="104.5 110 37.83 110 15.5 10 82.17 10 104.5 110"/></svg>
    <p>DNAMutation</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-7{{fill:#fa9fb5;}}</style></defs><polygon class="cls-7" points="85 16.7 35 16.7 10 60 35 103.3 85 103.3 110 60 85 16.7"/></svg>
    <p>ProteinMutation</p>
  </div>
  <div class="legend-box">
    <svg width="20" height="20" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120"><defs><style>.cls-8{{fill:#ffffb3;}}</style></defs><polygon class="cls-8" points="79.13 13.81 40.87 13.81 13.81 40.87 13.81 79.13 40.87 106.19 79.13 106.19 106.19 40.87 79.13 13.81"/></svg>
    <p>SNP</p>
  </div>
</div>
</body>
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.30.2/cytoscape.min.js"></script>
<script>
  let cy = cytoscape({{
    container: document.getElementById("cy"),
    elements: {cytoscape_js},
    layout: {{"name": "{layout}", animate: false}},
    style: [
    {{
      selector: "node",
      style: {{
        "width": "data(node_size)",
        "height": "data(node_size)",
        "text-valign": "center",
        "label": "data(label)",
        "shape": "data(shape)",
        "color": "data(label_color)",
        "background-color" : "data(color)",
        "font-size": "12px",
        "font-weight": "500",
        "text-outline-width": 2,
        "text-outline-color": "#fff",
        "text-outline-opacity": 0.8
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
        "curve-style": "bezier",
        "label": "data(label)",
        "font-size": "11px",
        "font-weight": "bold",
        "text-background-color": "#ffffff",
        "text-background-opacity": 0.9,
        "text-background-padding": "3px",
        "color": "#000000",
        "text-wrap": "wrap",
        "text-max-width": "100px",
        "text-rotation": "autorotate",
      }},
    }},
    {{
      selector: "edge[is_directional]",
      style: {{
        "target-arrow-shape": "triangle",
        "target-arrow-color": "#666",
        "arrow-scale": 1.2,
      }},
    }},
    {{
      selector: ".top-center",
      style: {{
        "text-valign": "top",
        "text-halign": "center",
        "font-size": "20px",
      }},
    }},
    {{
        selector: '.filtered',
        style: {{
            'display': 'none'
        }}
    }}
  ]
  }});
  
  // Update Layout
  document.getElementById('layout-select').addEventListener('change', function(e) {{
      const layoutName = e.target.value;
      cy.layout({{name: layoutName, animate: true, fit: true}}).run();
  }});

  // Filter by Degree
  const degreeSlider = document.getElementById('degree-slider');
  const degreeVal = document.getElementById('degree-val');
  
  // Find max degree in graph to set slider max
  // Wait for initial render
  cy.ready(function() {{
      let maxDegree = 0;
      cy.nodes().forEach(node => {{
          // Skip community nodes if any
          if (node.data('type') === 'community') return;
          
          const d = node.data('degree') || 0;
          if (d > maxDegree) maxDegree = d;
      }});
      // Cap at reasonable value if too high
      if (maxDegree > 50) maxDegree = 50;
      if (maxDegree < 5) maxDegree = 5;
      
      degreeSlider.max = maxDegree;
  }});
  
  degreeSlider.addEventListener('input', function(e) {{
      const threshold = parseInt(e.target.value);
      degreeVal.textContent = threshold;
      
      cy.batch(() => {{
          cy.nodes().forEach(node => {{
              // Always show community nodes
              if (node.data('type') === 'community') return;
              
              const d = node.data('degree') || 0;
              if (d < threshold) {{
                  node.addClass('filtered');
              }} else {{
                  node.removeClass('filtered');
              }}
          }});
      }});
      }});

  // Info Panel Interactivity
  const infoPanel = document.getElementById('info-panel');
  const infoContent = document.getElementById('info-content');

  function showPanel() {{
      infoPanel.style.display = 'block';
  }}

  function hidePanel() {{
      infoPanel.style.display = 'none';
  }}

  cy.on('tap', 'node', function(evt){{
      const node = evt.target;
      const data = node.data();
      
      // Skip community nodes for detailed info if generic
      if (data.type === 'community') return;

      let html = `<div class="info-title">${{data.label}}</div>`;
      html += `<div class="info-row"><span class="info-label">Type:</span> ${{data.node_type || data.type}}</div>`;
      html += `<div class="info-row"><span class="info-label">Degree:</span> ${{data.degree}}</div>`;
      if (data.standardized_id) {{
          html += `<div class="info-row"><span class="info-label">ID:</span> ${{data.standardized_id}}</div>`;
      }}
      
      infoContent.innerHTML = html;
      showPanel();
  }});

  cy.on('tap', 'edge', function(evt){{
      const edge = evt.target;
      const data = edge.data();
      
      let html = `<div class="info-title">Relationship Details</div>`;
      
      // Handle Source/Target Names (Using data attributes which might include swapped names for display)
      const sourceName = data.source_name || data.source;
      const targetName = data.target_name || data.target;
      
      html += `<div class="info-row"><span class="info-label">Source:</span> ${{sourceName}}</div>`;
      html += `<div class="info-row"><span class="info-label">Target:</span> ${{targetName}}</div>`;
      html += `<div class="info-row"><span class="info-label">Relation:</span> ${{data.relation_display || data.label}}</div>`;
      
      if (data.relation_confidence) {{
          html += `<div class="info-row"><span class="info-label">Confidence:</span> ${{data.relation_confidence}}</div>`;
      }}
      
      if (data.pmids && data.pmids.length > 0) {{
          html += `<div class="info-row"><span class="info-label">Evidence (${{data.pmids.length}} articles):</span></div>`;
          html += `<div class="pmid-list">`;
          data.pmids.forEach(pmid => {{
              html += `<a href="https://pubmed.ncbi.nlm.nih.gov/${{pmid}}/" target="_blank" class="pmid-link" title="Open in PubMed">${{pmid}}</a>`;
          }});
          html += `</div>`;
      }} else {{
          html += `<div class="info-row">No specific articles linked.</div>`;
      }}
      
      infoContent.innerHTML = html;
      showPanel();
  }});

  // Hide panel when clicking on background
  cy.on('tap', function(evt){{
      if(evt.target === cy){{
          hidePanel();
      }}
  }});
</script>
</html>
"""
