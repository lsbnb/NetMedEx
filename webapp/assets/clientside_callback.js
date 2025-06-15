window.dash_clientside = window.dash_clientside || {}

function create_pmid_table(pmids, pmid_title) {
  const pubtator_href = "https://www.ncbi.nlm.nih.gov/research/pubtator3/publication/"
  const pmid_table = {
    type: "Table",
    namespace: "dash_html_components",
    props: {
      className: "table table-bordered table-striped table-sm",
      children: [
        {
          type: "Thead",
          namespace: "dash_html_components",
          props: {
            children: [
              {
                type: "Tr",
                namespace: "dash_html_components",
                props: {
                  children: [
                    {
                      type: "Th",
                      namespace: "dash_html_components",
                      props: { children: "No." }
                    },
                    {
                      type: "Th",
                      namespace: "dash_html_components",
                      props: { children: "PMID" }
                    },
                    {
                      type: "Th",
                      namespace: "dash_html_components",
                      props: { children: "Title" }
                    }
                  ]
                }
              }
            ]
          }
        },
        {
          type: "Tbody",
          namespace: "dash_html_components",
          props: { children: [] }
        }
      ]
    }
  }

  const table_entry = pmid_table.props.children[1].props.children
  pmids.forEach((pmid, index) => {
    const title = pmid_title[pmid]

    table_entry.push({
      type: "Tr",
      namespace: "dash_html_components",
      props: {
        children: [
          {
            type: "Td",
            namespace: "dash_html_components",
            props: { children: `${index + 1}` }
          },
          {
            type: "Td",
            namespace: "dash_html_components",
            props: {
              children: {
                type: "A",
                namespace: "dash_html_components",
                props: {
                  href: pubtator_href + pmid,
                  target: "_blank",
                  children: pmid,
                }
              }
            }
          },
          {
            type: "Td",
            namespace: "dash_html_components",
            props: { children: `${title}` }
          }
        ]
      }
    })
  })

  return pmid_table
}

window.dash_clientside.clientside = {
  info_scroll: function (trigger) {
    const infoElements = document.querySelectorAll("[data-tooltip]")
    const rootElement = document.querySelector(":root")

    infoElements.forEach((infoElement) => {
      infoElement.addEventListener("mouseover", () => {
        const position = infoElement.getBoundingClientRect()
        if (infoElement.classList.contains("info-right")) {
          rootElement.style.setProperty("--tooltip-x", `${position.right}px`)
        } else {
          rootElement.style.setProperty("--tooltip-x", `${position.left}px`)
        }
        rootElement.style.setProperty("--tooltip-y", `${position.bottom}px`)
      })
    })

    return null
  },
  show_edge_info: function (selected_edges, tap_edge, pmid_title) {
    function check_if_selected(tap_edge) {
      for (let i = 0; i < selected_edges.length; i++) {
        if (selected_edges[i].id === tap_edge.id) {
          return true
        }
      }
      return false
    }

    function get_z_index(display) {
      return display === "none" ? -100 : 100
    }

    let elements = []
    let display = "none"

    const nodeContainer = document.getElementById("node-info-container")
    if (nodeContainer) {
      nodeContainer.style.display = "none"
      nodeContainer.style.zIndex = -100
    }

    if (tap_edge !== undefined) {
      if (!check_if_selected(tap_edge)) {
        return [{ "display": display, "zIndex": get_z_index(display) }, elements]
      }

      const [node_1, node_2] = tap_edge.label.split(" (interacts with) ")
      let edge_type
      if (tap_edge.edge_type === "node") {
        edge_type = "Node"
      } else if (tap_edge.edge_type === "community") {
        edge_type = "Community"
      }
      elements.push({ props: { children: `${edge_type} 1: ${node_1}` }, type: "P", namespace: "dash_html_components" })
      elements.push({ props: { children: `${edge_type} 2: ${node_2}` }, type: "P", namespace: "dash_html_components" })
      const edge_table = create_pmid_table(tap_edge.pmids, pmid_title)
      display = "block"
      elements.push(edge_table)
    }


    return [
      {
        display: display,
        zIndex: get_z_index(display),
      },
      elements,
    ]
  },
  show_node_info: function (selected_nodes, tap_node, pmid_title) {
    function check_if_selected(tap_node) {
      for (let i = 0; i < selected_nodes.length; i++) {
        if (selected_nodes[i].id === tap_node.id) {
          return true
        }
      }
      return false
    }

    function get_z_index(display) {
      return display === "none" ? -100 : 100
    }

    let elements = []
    let display = "none"

    const edgeContainer = document.getElementById("edge-info-container")
    if (edgeContainer) {
      edgeContainer.style.display = "none"
      edgeContainer.style.zIndex = -100
    }

    if (tap_node !== undefined) {
      if (!check_if_selected(tap_node)) {
        return [{ "display": display, "zIndex": get_z_index(display) }, elements]
      }

      elements.push({ props: { children: `Name: ${tap_node.label.trim()}` }, type: "P", namespace: "dash_html_components" })

      let identifier = tap_node.standardized_id
      const node_type = tap_node.node_type
      let href = null

      const NCBI_TAXONOMY = "https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id="
      const NCBI_GENE = "https://www.ncbi.nlm.nih.gov/gene/"
      const NCBI_MESH = "https://meshb.nlm.nih.gov/record/ui?ui="

      if (identifier !== "-" && identifier !== "") {
        if (node_type === "Species") {
          href = NCBI_TAXONOMY + identifier
          // Prepend "NCBI Taxonomy:"
          identifer = "NCBI Taxonomy: " + identifier
        } else if (node_type === "Gene") {
          href = NCBI_GENE + identifier
          // Prepend "NCBI Gene:"
          identifer = "NCBI Gene: " + identifier
        } else if (node_type === "Chemical" || node_type === "Disease") {
          if (identifier.startsWith("MESH:")) {
            href = NCBI_MESH + identifier.replace("MESH:", "")
          }
        }
      }

      if (href) {
        elements.push({
          type: "P",
          namespace: "dash_html_components",
          props: {
            children: ["Identifier: ", {
              type: "A",
              namespace: "dash_html_components",
              props: { href: href, target: "_blank", children: identifier }
            }]
          }
        })
      } else {
        elements.push({ props: { children: `Identifier: ${identifier}` }, type: "P", namespace: "dash_html_components" })
      }

      const node_table = create_pmid_table(tap_node.pmids, pmid_title)
      display = "block"
      elements.push(node_table)
    }

    return [
      {
        display: display,
        zIndex: get_z_index(display),
      },
      elements,
    ]
  }
}