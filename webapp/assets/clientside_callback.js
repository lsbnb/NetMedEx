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

      const node_1 = tap_edge.source_name || "Unknown"
      const node_2 = tap_edge.target_name || "Unknown"
      const relation = tap_edge.relation_display || "interacts with"

      let edge_type
      if (tap_edge.edge_type === "node") {
        edge_type = "Node"
      } else if (tap_edge.edge_type === "community") {
        edge_type = "Community"
      }
      elements.push({ props: { children: `${edge_type} 1: ${node_1}` }, type: "P", namespace: "dash_html_components" })
      elements.push({ props: { children: `${edge_type} 2: ${node_2}` }, type: "P", namespace: "dash_html_components" })
      elements.push({ props: { children: `Relation: ${relation}` }, type: "P", namespace: "dash_html_components" })

      // Display semantic relationship information if available
      if (tap_edge.relations && Object.keys(tap_edge.relations).length > 0) {
        elements.push({
          props: {
            children: "Semantic Relationships:",
            style: { fontWeight: "bold", marginTop: "10px" }
          },
          type: "P",
          namespace: "dash_html_components"
        })

        // Iterate through PMIDs and their relations
        Object.entries(tap_edge.relations).forEach(([pmid, relation_types]) => {
          const relationArray = Array.from(relation_types)
          relationArray.forEach(relationType => {
            // Get confidence and evidence for this relation
            const confidence = tap_edge.confidences?.[pmid]?.[relationType] || "N/A"
            const evidence = tap_edge.evidences?.[pmid]?.[relationType] || "No evidence available"

            // Create a card for each relationship
            elements.push({
              type: "Div",
              namespace: "dash_html_components",
              props: {
                style: {
                  backgroundColor: "#f8f9fa",
                  padding: "10px",
                  marginTop: "8px",
                  borderRadius: "4px",
                  borderLeft: "3px solid #007bff"
                },
                children: [
                  {
                    props: {
                      children: `Relation: ${relationType}`,
                      style: { fontWeight: "bold", color: "#007bff" }
                    },
                    type: "P",
                    namespace: "dash_html_components"
                  },
                  {
                    props: {
                      children: `Confidence: ${typeof confidence === 'number' ? confidence.toFixed(2) : confidence}`,
                      style: { fontSize: "0.9em", marginTop: "4px" }
                    },
                    type: "P",
                    namespace: "dash_html_components"
                  },
                  {
                    props: {
                      children: `Evidence: "${evidence}"`,
                      style: {
                        fontSize: "0.85em",
                        fontStyle: "italic",
                        marginTop: "4px",
                        color: "#495057"
                      }
                    },
                    type: "P",
                    namespace: "dash_html_components"
                  },
                  {
                    props: {
                      children: `PMID: ${pmid}`,
                      style: { fontSize: "0.8em", marginTop: "4px", color: "#6c757d" }
                    },
                    type: "P",
                    namespace: "dash_html_components"
                  }
                ]
              }
            })
          })
        })
      }

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

/**
 * Chat component enhancements
 */
function setupChatAutoScroll() {
  const chatContainer = document.getElementById('chat-messages');
  if (!chatContainer) return;

  // Scroll to bottom initially
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Create an observer to scroll when new messages are added
  const observer = new MutationObserver(() => {
    chatContainer.scrollTo({
      top: chatContainer.scrollHeight,
      behavior: 'smooth'
    });
  });

  observer.observe(chatContainer, { childList: true });
}

// Re-run setup when the chat panel might have been rendered/updated
document.addEventListener('DOMContentLoaded', () => {
  setupChatAutoScroll();

  // Also watch for the container being added/shown
  const bodyObserver = new MutationObserver((mutationsList) => {
    if (document.getElementById('chat-messages')) {
      setupChatAutoScroll();
    }
  });
  bodyObserver.observe(document.body, { childList: true, subtree: true });
});