/**
 * Pediatric Portal → NetMedEx postMessage receiver
 * Listens for messages from the Pediatric wrapper (port 8051) and injects
 * text into the Chat input or Node search input accordingly.
 *
 * Message shapes:
 *   { type: "fillChat",    text: "..." }  → fills #chat-input-box (textarea)
 *   { type: "searchNodes", text: "..." }  → fills #graph-node-search (input)
 */
(function () {
    function setReactValue(el, value) {
        // Must use the native setter to bypass React's synthetic event system
        var proto = el.tagName === 'TEXTAREA'
            ? window.HTMLTextAreaElement.prototype
            : window.HTMLInputElement.prototype;
        var setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
        setter.call(el, value);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
    }

    window.addEventListener('message', function (event) {
        var data = event.data;
        if (!data || typeof data !== 'object' || !data.type) return;

        if (data.type === 'fillChat' && data.text) {
            // Small delay to ensure the chat panel is mounted
            setTimeout(function () {
                var el = document.getElementById('chat-input-box');
                if (!el) return;
                setReactValue(el, data.text);
                el.focus();
                el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 120);
        }

        if (data.type === 'searchNodes' && data.text) {
            setTimeout(function () {
                var el = document.getElementById('graph-node-search');
                if (!el) return;
                setReactValue(el, data.text);
                el.focus();
                el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 120);
        }
    });
})();
