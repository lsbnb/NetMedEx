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
  const safeTitle = (pmid) => {
    if (!pmid_title) return "—"
    return pmid_title[pmid] || pmid_title[String(pmid)] || pmid_title[Number(pmid)] || "—"
  }

  pmids.forEach((pmid, index) => {
    const title = safeTitle(pmid)

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
            props: { children: title }
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
  show_edge_info: function (selected_edges, tap_edge, pmid_title, pmid_citations) {
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

      const edge_table = create_pmid_table(tap_edge.pmids, pmid_title, pmid_citations)
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
  show_node_info: function (selected_nodes, tap_node, pmid_title, pmid_citations) {
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
          identifier = "NCBI Taxonomy: " + identifier
        } else if (node_type === "Gene") {
          href = NCBI_GENE + identifier
          // Prepend "NCBI Gene:"
          identifier = "NCBI Gene: " + identifier
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

      const node_table = create_pmid_table(tap_node.pmids, pmid_title, pmid_citations)
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
  },
  sync_llm_toggles: function (provider, openai_api_key, google_api_key, google_model, local_url, local_model, openrouter_api_key, openrouter_model) {
    if (provider === "openai") {
      if (openai_api_key && openai_api_key.trim().startsWith("sk-")) {
        return [true, "semantic"];
      }
    } else if (provider === "google") {
      if (google_api_key && google_api_key.trim() !== "" && google_model && google_model.trim() !== "") {
        return [true, "semantic"];
      }
    } else if (provider === "openrouter") {
      if (openrouter_api_key && openrouter_api_key.trim() !== "" && openrouter_model && openrouter_model.trim() !== "") {
        return [true, "semantic"];
      }
    } else if (provider === "local") {
      if (local_url && local_url.trim() !== "" && local_model && local_model.trim() !== "") {
        return [true, "semantic"];
      }
    }
    return [false, "co-occurrence"];
  },
  apply_graph_visual_filters: function (threshold, searchQuery, visibleNodeTypes, elements, current_stylesheet) {
    const CHUNK_SIZE = 200;
    const isDynamic = (rule) => {
      if (!rule) return false;
      if (rule._netmedex_dynamic === true) return true;
      const selector = rule.selector || "";
      const style = rule.style || {};
      // Signature of our dynamic rules (search highlight, confidence filter, etc.)
      if (selector.includes('[id="')) return true;
      if (style.opacity === 0.1 || style.opacity === 0.2 || style.opacity === 0.95 || style.opacity === 0.05) return true;
      if (style["border-color"] === "#ff6b00") return true;
      return false;
    };

    const stripDynamicRules = (rules) => (Array.isArray(rules) ? rules : []).filter(
      (rule) => !isDynamic(rule)
    );

    let base_rules = [];
    if (Array.isArray(current_stylesheet) && current_stylesheet.length > 0) {
      base_rules = stripDynamicRules(current_stylesheet);
      window.__netmedex_base_stylesheet = base_rules;
    } else if (Array.isArray(window.__netmedex_base_stylesheet)) {
      base_rules = [...window.__netmedex_base_stylesheet];
    } else {
      return window.dash_clientside.no_update;
    }

    const new_stylesheet = [...base_rules];
    const graphElements = Array.isArray(elements) ? elements : [];
    const nodeElements = [];
    const edgeElements = [];
    for (const el of graphElements) {
      if (!el || !el.data) continue;
      if (el.data.source && el.data.target) edgeElements.push(el);
      else nodeElements.push(el);
    }
    const hasCommunityNodes = nodeElements.some(
      (node) => Boolean(node && node.data && node.data.is_community)
    );
    const wasCommunityMode = Boolean(window.__netmedex_prev_has_community);
    const justExitedCommunityMode = wasCommunityMode && !hasCommunityNodes;
    window.__netmedex_prev_has_community = hasCommunityNodes;

    const addRule = (selector, style) => {
      if (!selector) return;
      new_stylesheet.push({ selector, style, _netmedex_dynamic: true });
    };
    const addChunkedIdRules = (ids, elementType, style) => {
      if (!ids || ids.length === 0) return;
      for (let i = 0; i < ids.length; i += CHUNK_SIZE) {
        const chunk = ids.slice(i, i + CHUNK_SIZE);
        const selector = chunk.map((id) => `${elementType}[id="${id}"]`).join(", ");
        addRule(selector, style);
      }
    };

    // Always reset opacity before applying interactive highlights.
    addRule("node", { opacity: 1, "text-opacity": 1 });
    addRule("edge", { opacity: 1 });

    if (hasCommunityNodes) {
      addRule("edge", {
        "curve-style": "bezier",
        "line-opacity": 0.9
      });
      addRule(":parent", {
        "z-compound-depth": "bottom"
      });
      return new_stylesheet.map(rule => {
        const { _netmedex_dynamic, ...cleanRule } = rule;
        return cleanRule;
      });
    }

    // 1) Confidence threshold: hide only low-confidence semantic edges.
    const numericThreshold = Number(threshold) || 0;
    const hideEdgeIds = new Set();
    if (numericThreshold > 0 && !hasCommunityNodes && !justExitedCommunityMode) {
      for (const edge of edgeElements) {
        const data = edge.data || {};
        if (data.edge_type !== "semantic") continue;
        const conf = data.relation_confidence;
        if (typeof conf === "number" && conf < numericThreshold && data.id) {
          hideEdgeIds.add(data.id);
        }
      }
    }

    // 2) Node type filter
    const normalizedTypeFilter = new Set((visibleNodeTypes || []).map((t) => String(t).toLowerCase()));
    const ALL_KNOWN_NODE_TYPES = new Set([
      "gene", "disease", "chemical", "species", "cellline",
      "dnamutation", "proteinmutation", "snp", "community",
    ]);
    const hideNodeIds = new Set();
    const isShowAllNodeTypes = normalizedTypeFilter.size === ALL_KNOWN_NODE_TYPES.size;
    if (normalizedTypeFilter.size > 0 && !isShowAllNodeTypes && !hasCommunityNodes) {
      for (const node of nodeElements) {
        const data = node.data || {};
        const nodeId = data.id;
        if (!nodeId) continue;
        const nodeType = String(data.node_type || "").toLowerCase();
        if (!normalizedTypeFilter.has(nodeType)) {
          hideNodeIds.add(nodeId);
        }
      }
      for (const edge of edgeElements) {
        const data = edge.data || {};
        if (!data.id) continue;
        if (hideNodeIds.has(data.source) || hideNodeIds.has(data.target)) {
          hideEdgeIds.add(data.id);
        }
      }
    }

    // 3a) Isolate-node hiding: when confidence threshold is active, hide nodes
    //     whose every edge has been filtered out (no visible edges remain).
    if (numericThreshold > 0 && !hasCommunityNodes && !justExitedCommunityMode) {
      // Build a map: nodeId -> list of edge ids connected to it
      const nodeEdgeCount = new Map();
      const nodeVisibleEdgeCount = new Map();
      for (const node of nodeElements) {
        const id = node.data && node.data.id;
        if (id) {
          nodeEdgeCount.set(id, 0);
          nodeVisibleEdgeCount.set(id, 0);
        }
      }
      for (const edge of edgeElements) {
        const data = edge.data || {};
        const src = data.source;
        const tgt = data.target;
        if (!src || !tgt) continue;
        // Count total edges for each endpoint
        if (nodeEdgeCount.has(src)) nodeEdgeCount.set(src, nodeEdgeCount.get(src) + 1);
        if (nodeEdgeCount.has(tgt)) nodeEdgeCount.set(tgt, nodeEdgeCount.get(tgt) + 1);
        // Count visible (non-hidden) edges for each endpoint
        if (!hideEdgeIds.has(data.id)) {
          if (nodeVisibleEdgeCount.has(src)) nodeVisibleEdgeCount.set(src, nodeVisibleEdgeCount.get(src) + 1);
          if (nodeVisibleEdgeCount.has(tgt)) nodeVisibleEdgeCount.set(tgt, nodeVisibleEdgeCount.get(tgt) + 1);
        }
      }
      for (const [nodeId, visibleCount] of nodeVisibleEdgeCount) {
        // Only hide nodes that originally had edges but now have none visible
        if (visibleCount === 0 && nodeEdgeCount.get(nodeId) > 0 && !hideNodeIds.has(nodeId)) {
          hideNodeIds.add(nodeId);
        }
      }
    }

    addChunkedIdRules(Array.from(hideNodeIds), "node", { display: "none" });
    addChunkedIdRules(Array.from(hideEdgeIds), "edge", { display: "none" });

    // 3) Search highlight
    const normalizeText = (txt) => String(txt || "").toLowerCase().replace(/[^a-z0-9]/g, "");
    const SYNONYM_MAP = {
      metformin: ["glucophage", "dimethylbiguanide"],
      t2dm: ["type2diabetes", "type2diabetesmellitus", "diabetesmellitustype2"],
      diabetes: ["diabetesmellitus", "dm"],
      covid19: ["sarscov2", "coronavirusdisease2019", "covid"],
      egfr: ["erb1", "epidermalgrowthfactorreceptor"],
      tp53: ["p53", "tumorproteinp53"],
    };
    const buildQueryCandidates = (query) => {
      const q = normalizeText(query);
      if (!q) return [];
      const out = new Set([q]);
      const aliases = SYNONYM_MAP[q] || [];
      for (const alias of aliases) out.add(normalizeText(alias));
      for (const [base, list] of Object.entries(SYNONYM_MAP)) {
        if (list.map(normalizeText).includes(q)) out.add(base);
      }
      return Array.from(out).filter(Boolean);
    };

    const rawTerms = String(searchQuery || "").split(",").map((t) => t.trim()).filter(Boolean);
    const anchorNodeIds = new Set();
    for (const term of rawTerms) {
      const candidates = buildQueryCandidates(term);
      if (candidates.length === 0) continue;
      for (const node of nodeElements) {
        const data = node.data || {};
        const nodeId = data.id;
        if (!nodeId || hideNodeIds.has(nodeId)) continue;
        const labelNorm = normalizeText(data.label || "");
        const idNorm = normalizeText(data.standardized_id || "");
        if (candidates.some((q) => labelNorm.includes(q) || idNorm.includes(q))) {
          anchorNodeIds.add(nodeId);
        }
      }
    }

    if (anchorNodeIds.size > 0) {
      const neighborNodeIds = new Set(anchorNodeIds);
      const focusEdgeIds = new Set();
      for (const edge of edgeElements) {
        const data = edge.data || {};
        const edgeId = data.id;
        if (!edgeId || hideEdgeIds.has(edgeId)) continue;
        if (anchorNodeIds.has(data.source) || anchorNodeIds.has(data.target)) {
          focusEdgeIds.add(edgeId);
          if (!hideNodeIds.has(data.source)) neighborNodeIds.add(data.source);
          if (!hideNodeIds.has(data.target)) neighborNodeIds.add(data.target);
        }
      }

      addRule("node", { opacity: 0.2, "text-opacity": 0.2 });
      addRule("edge", { opacity: 0.1 });
      addChunkedIdRules(Array.from(neighborNodeIds), "node", { opacity: 1, "text-opacity": 1 });
      addChunkedIdRules(Array.from(anchorNodeIds), "node", {
        "border-width": 3,
        "border-color": "#ff6b00",
        "border-opacity": 1,
      });
      addChunkedIdRules(Array.from(focusEdgeIds), "edge", { opacity: 0.95 });
    }

    return new_stylesheet.map(rule => {
      const { _netmedex_dynamic, ...cleanRule } = rule;
      return cleanRule;
    });
  },
  filter_edges_by_confidence: function (threshold, elements, current_stylesheet) {
    return window.dash_clientside.clientside.apply_graph_visual_filters(
      threshold,
      "",
      [],
      elements,
      current_stylesheet
    );
  }
};

// --- GLOBAL PURE-JS INTERACTION HANDLERS ---
// This handles the copy feature using event delegation on the document.
// This is 100% stable regardless of Dash re-renders or component replacement.
document.addEventListener("click", function (e) {
  const btn = e.target.closest(".js-copy-btn");
  if (!btn) return;

  const copyId = btn.getAttribute("data-copy-id");
  const textEl = document.getElementById("copy-text-" + copyId);
  if (!textEl) return;

  const textToCopy = textEl.textContent;

  // Copy to clipboard
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(textToCopy);
  } else {
    const textArea = document.createElement("textarea");
    textArea.value = textToCopy;
    textArea.style.position = "fixed";
    textArea.style.left = "-9999px";
    textArea.style.top = "-9999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    document.execCommand("copy");
    textArea.remove();
  }

  // Visual Feedback (Toggle class)
  btn.classList.remove("bi-files", "text-secondary");
  btn.classList.add("bi-check2", "text-success");

  setTimeout(function () {
    // Revert back if the button is still in the DOM
    if (btn && btn.classList.contains("bi-check2")) {
      btn.classList.remove("bi-check2", "text-success");
      btn.classList.add("bi-files", "text-secondary");
    }
  }, 2000);
});

// Chat Send Button Processing Feedback
document.addEventListener("click", function (e) {
  const btn = e.target.closest(".suggested-question-btn, #chat-send-btn, #modal-chat-send-btn");
  if (!btn) return;
  btn.classList.add("processing");

  const thinkingHTML = '<span class="chat-thinking-dots"><span></span><span></span><span></span></span>';
  if (btn.id === "chat-send-btn" || btn.classList.contains("suggested-question-btn")) {
    const status = document.getElementById("chat-processing-status");
    if (status) status.innerHTML = thinkingHTML;
  }
  if (btn.id === "modal-chat-send-btn" || btn.classList.contains("suggested-question-btn")) {
    const modalStatus = document.getElementById("modal-chat-processing-status");
    if (modalStatus) modalStatus.innerHTML = thinkingHTML;
  }
});

// Global initialization and cleanup
(function () {
  /**
   * Chat component enhancements
   */
  function setupChatAutoScroll() {
    const chatContainer = document.getElementById('chat-messages');
    if (!chatContainer || chatContainer._scrollInitialized) return;
    chatContainer._scrollInitialized = true;

    // Scroll to bottom initially
    chatContainer.scrollTop = chatContainer.scrollHeight;

    // Create an observer to scroll when new messages are added
    const observer = new MutationObserver(() => {
      const anchors = chatContainer.querySelectorAll('.chat-message-user-anchor');
      if (anchors.length > 0) {
        const latestAnchor = anchors[anchors.length - 1];
        latestAnchor.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      } else {
        chatContainer.scrollTop = chatContainer.scrollHeight;
      }

      const status = document.getElementById('chat-processing-status');
      const modalStatus = document.getElementById('modal-chat-processing-status');
      if (status) status.textContent = '';
      if (modalStatus) modalStatus.textContent = '';
      const sendBtn = document.getElementById('chat-send-btn');
      const modalSendBtn = document.getElementById('modal-chat-send-btn');
      if (sendBtn) sendBtn.classList.remove('processing');
      if (modalSendBtn) modalSendBtn.classList.remove('processing');
    });

    observer.observe(chatContainer, { childList: true });
  }

  /**
   * Draggable Legend
   */
  function makeLegendDraggable() {
    const legend = document.getElementById('legend-container');
    if (!legend || legend._dragInitialised) return;
    legend._dragInitialised = true;

    let dragging = false;
    let offsetX = 0;
    let offsetY = 0;

    legend.addEventListener('mousedown', function (e) {
      dragging = true;
      legend.style.cursor = 'grabbing';

      const rect = legend.getBoundingClientRect();
      const parentRect = legend.offsetParent
        ? legend.offsetParent.getBoundingClientRect()
        : { top: 0, left: 0 };

      legend.style.bottom = 'auto';
      legend.style.right = 'auto';
      legend.style.top = (rect.top - parentRect.top) + 'px';
      legend.style.left = (rect.left - parentRect.left) + 'px';

      offsetX = e.clientX - rect.left;
      offsetY = e.clientY - rect.top;

      e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      const parentRect = legend.offsetParent
        ? legend.offsetParent.getBoundingClientRect()
        : { top: 0, left: 0 };

      legend.style.left = (e.clientX - parentRect.left - offsetX) + 'px';
      legend.style.top = (e.clientY - parentRect.top - offsetY) + 'px';
    });

    document.addEventListener('mouseup', function () {
      if (!dragging) return;
      dragging = false;
      legend.style.cursor = 'grab';
    });
  }

  /**
   * ChatGPT-like input behavior:
   * - Enter => send
   * - Shift+Enter => newline
   * - Disable send button for blank input
   * - Keep input focused after sending
   */
  function setupChatInputBehavior() {
    const pairs = [
      { inputId: 'chat-input-box', buttonId: 'chat-send-btn' },
      { inputId: 'modal-chat-input', buttonId: 'modal-chat-send-btn' },
    ];

    pairs.forEach(({ inputId, buttonId }) => {
      const input = document.getElementById(inputId);
      const button = document.getElementById(buttonId);
      if (!input || !button) return;
      if (input._chatBehaviorBound) {
        // Keep button state synced even on re-render.
        if (input.disabled) {
          button.disabled = true;
        } else {
          button.disabled = input.value.trim().length === 0;
        }
        return;
      }
      input._chatBehaviorBound = true;

      const syncButtonState = () => {
        if (input.disabled) {
          button.disabled = true;
          return;
        }
        button.disabled = input.value.trim().length === 0;
      };

      const autoResize = () => {
        input.style.height = 'auto';
        const maxHeight = 220;
        const next = Math.min(input.scrollHeight, maxHeight);
        input.style.height = `${Math.max(next, 52)}px`;
        input.style.overflowY = input.scrollHeight > maxHeight ? 'auto' : 'hidden';
      };

      autoResize();
      syncButtonState();

      input.addEventListener('input', () => {
        autoResize();
        syncButtonState();
      });

      input.addEventListener('keydown', (e) => {
        if (e.isComposing) return;
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          autoResize();
          syncButtonState();
          if (!button.disabled) {
            button.click();
            setTimeout(() => input.focus(), 50);
          }
        }
      });

      button.addEventListener('click', () => {
        setTimeout(autoResize, 0);
        setTimeout(() => input.focus(), 50);
      });
    });
  }

  /**
   * Handle outside clicks to close advanced settings
   */
  function handleAdvancedSettingsOutsideClick(event) {
    const aBtn = document.getElementById('advanced-settings-btn');
    const aCollapse = document.getElementById('advanced-settings-collapse');

    // Check if the panel is currently displayed
    if (aBtn && aCollapse && aCollapse.style.display !== 'none') {
      // ⚠️ FIX: Ignore clicks on portal elements (like dropdown menus)
      // Standard Dash/React-Select menus and other overlays are often appended to body
      const isPortalClick = event.target.closest('.Select-menu-outer') ||
        event.target.closest('.VirtualizedSelect__menu') ||
        event.target.closest('.rc-slider-tooltip') ||
        event.target.closest('.Select-option') ||
        event.target.closest('.VirtualizedSelectOption');

      if (isPortalClick) return;

      // If click is outside both button and panel
      if (!aCollapse.contains(event.target) && !aBtn.contains(event.target)) {
        // Find close button or click main button to toggle
        const closeBtn = document.getElementById('close-advanced-settings-btn');
        if (closeBtn) {
          closeBtn.click();
        } else {
          aBtn.click();
        }
      }
    }
  }

  function init() {
    setupChatAutoScroll();
    setupChatInputBehavior();
    makeLegendDraggable();
  }

  // Bind outside click listener once
  if (!window._netmedex_outside_click_bound) {
    document.addEventListener('click', handleAdvancedSettingsOutsideClick);
    window._netmedex_outside_click_bound = true;
  }

  // Initial call
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Throttled observer for dynamic elements
  let timeout = null;
  const bodyObserver = new MutationObserver(() => {
    if (timeout) return;
    timeout = setTimeout(() => {
      init();
      timeout = null;
    }, 500); // Only check twice per second max
  });
  bodyObserver.observe(document.body, { childList: true, subtree: true });
})();
