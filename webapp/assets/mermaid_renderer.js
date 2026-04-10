(function () {
  let loading = false;
  let initialized = false;

  function ensureMermaidReady(cb) {
    if (window.mermaid) {
      if (!initialized) {
        window.mermaid.initialize({
          startOnLoad: false,
          securityLevel: "loose",
          theme: "default",
        });
        initialized = true;
      }
      cb();
      return;
    }

    if (loading) {
      setTimeout(() => ensureMermaidReady(cb), 200);
      return;
    }

    loading = true;
    const script = document.createElement("script");
    script.src = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js";
    script.async = true;
    script.onload = function () {
      loading = false;
      ensureMermaidReady(cb);
    };
    script.onerror = function () {
      loading = false;
      // Keep fallback behavior: if Mermaid CDN fails, raw code block stays visible.
      // eslint-disable-next-line no-console
      console.warn("Failed to load Mermaid script.");
    };
    document.head.appendChild(script);
  }

  function convertCodeBlocksToMermaid(root) {
    const codeBlocks = root.querySelectorAll("pre code.language-mermaid");
    if (!codeBlocks.length) return false;

    let converted = false;
    codeBlocks.forEach((code) => {
      const pre = code.closest("pre");
      if (!pre) return;
      const graphDef = (code.textContent || "").trim();
      if (!graphDef) return;

      const wrapper = document.createElement("div");
      wrapper.className = "mermaid";
      wrapper.textContent = graphDef;
      pre.replaceWith(wrapper);
      converted = true;
    });
    return converted;
  }

  function renderMermaidIn(root) {
    if (!root || !root.querySelectorAll) return;
    const changed = convertCodeBlocksToMermaid(root);
    if (!changed) return;

    ensureMermaidReady(() => {
      if (window.mermaid && typeof window.mermaid.run === "function") {
        window.mermaid.run({ querySelector: ".mermaid" });
      } else if (window.mermaid && typeof window.mermaid.init === "function") {
        window.mermaid.init(undefined, document.querySelectorAll(".mermaid"));
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    const target = document.getElementById("chat-messages") || document.body;
    renderMermaidIn(document);

    const observer = new MutationObserver((mutations) => {
      for (const m of mutations) {
        if (m.addedNodes && m.addedNodes.length > 0) {
          renderMermaidIn(document);
          break;
        }
      }
    });
    observer.observe(target, { childList: true, subtree: true });
  });
})();
