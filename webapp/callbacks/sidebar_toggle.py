from __future__ import annotations

from dash import Input, Output, State


def callbacks(app):
    # Toggle callback: fires on button click
    app.clientside_callback(
        """
        function(n_clicks, is_collapsed) {
            if (n_clicks === undefined || n_clicks === null) {
                return window.dash_clientside.no_update;
            }
            var newState = !is_collapsed;
            var sidebar = document.getElementById('sidebar-container');
            var graphPanel = document.getElementById('graph-panel');
            var icon = document.querySelector('#sidebar-toggle-btn i');
            if (sidebar) sidebar.classList.toggle('sidebar-collapsed', newState);
            if (graphPanel) graphPanel.classList.toggle('sidebar-expanded', newState);
            if (icon) {
                icon.className = newState
                    ? 'bi bi-layout-sidebar-inset'
                    : 'bi bi-layout-sidebar';
            }
            return newState;
        }
        """,
        Output("sidebar-collapsed-store", "data"),
        Input("sidebar-toggle-btn", "n_clicks"),
        State("sidebar-collapsed-store", "data"),
        prevent_initial_call=True,
    )

    # Init callback: restore sidebar state on page load from the store
    app.clientside_callback(
        """
        function(is_collapsed) {
            var sidebar = document.getElementById('sidebar-container');
            var graphPanel = document.getElementById('graph-panel');
            var icon = document.querySelector('#sidebar-toggle-btn i');
            if (is_collapsed === true) {
                if (sidebar) sidebar.classList.add('sidebar-collapsed');
                if (graphPanel) graphPanel.classList.add('sidebar-expanded');
                if (icon) icon.className = 'bi bi-layout-sidebar-inset';
            } else {
                if (sidebar) sidebar.classList.remove('sidebar-collapsed');
                if (graphPanel) graphPanel.classList.remove('sidebar-expanded');
                if (icon) icon.className = 'bi bi-layout-sidebar';
            }
            return window.dash_clientside.no_update;
        }
        """,
        Output("sidebar-init", "children"),
        Input("sidebar-collapsed-store", "data"),
        prevent_initial_call=False,
    )
