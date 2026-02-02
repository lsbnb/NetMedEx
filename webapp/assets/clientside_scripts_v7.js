window.dash_clientside = window.dash_clientside || {};

window.dash_clientside.clientside = {
  info_scroll: function (trigger) {
    try {
      var infoElements = document.querySelectorAll("[data-tooltip]");
      var rootElement = document.querySelector(":root");

      if (infoElements.length > 0) {
        console.log("Found " + infoElements.length + " tooltips.");
        infoElements.forEach(function (infoElement) {
          infoElement.addEventListener("mouseover", function () {
            var position = infoElement.getBoundingClientRect();
            if (infoElement.classList.contains("info-right")) {
              rootElement.style.setProperty("--tooltip-x", position.right + "px");
            } else {
              rootElement.style.setProperty("--tooltip-x", position.left + "px");
            }
            rootElement.style.setProperty("--tooltip-y", position.bottom + "px");
          });
        });
      } else {
        console.log("No tooltips found.");
      }
    } catch (e) {
      console.error("Error in info_scroll:", e);
    }
    return null;
  },

  show_edge_info: function (selected_edges, tap_edge, pmid_title) {
    // Dummy implementation for debug
    return [{ "display": "none", "zIndex": -100 }, []];
  },

  show_node_info: function (selected_nodes, tap_node, pmid_title) {
    // Dummy implementation for debug
    return [{ "display": "none", "zIndex": -100 }, []];
  }
};