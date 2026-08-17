/**
 * Pediatric Portal postMessage sender
 * Delegates clicks on [data-postmsg-type] elements to the shared NetMedEx iframe.
 */
(function () {
    document.addEventListener('click', function (e) {
        var el = e.target.closest('[data-postmsg-type]');
        if (!el) return;

        var iframe = document.getElementById('iframe-netmedex');
        if (!iframe || !iframe.contentWindow) return;

        var type  = el.getAttribute('data-postmsg-type');
        var text  = el.getAttribute('data-postmsg-value') || '';

        iframe.contentWindow.postMessage({ type: type, text: text }, '*');

        // Brief visual flash to confirm the click
        el.style.transition = 'background 0.1s';
        el.style.background = 'rgba(79,195,247,0.35)';
        setTimeout(function () { el.style.background = ''; }, 350);

        // If this is a chat fill, also switch to the Chat panel
        if (type === 'fillChat') {
            var chatBtn = document.getElementById('nav-chat');
            if (chatBtn) chatBtn.click();
        }
        // If node search, switch to Network panel
        if (type === 'searchNodes') {
            var netBtn = document.getElementById('nav-network');
            if (netBtn) netBtn.click();
        }
    });
})();
