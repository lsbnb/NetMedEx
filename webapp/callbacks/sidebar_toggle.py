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

    # Search Options collapse — toggle on click, restore from store on page load
    app.clientside_callback(
        """
        function(n_clicks, stored) {
            var open;
            if (!n_clicks) {
                open = (stored !== null && stored !== undefined) ? stored : true;
            } else {
                open = !stored;
            }
            var chevron = document.getElementById('search-options-chevron');
            if (chevron) chevron.style.transform = open ? '' : 'rotate(-90deg)';
            if (!n_clicks) {
                return [open, window.dash_clientside.no_update];
            }
            return [open, open];
        }
        """,
        Output("search-options-collapse", "is_open"),
        Output("search-options-open-store", "data"),
        Input("search-options-toggle-btn", "n_clicks"),
        State("search-options-open-store", "data"),
        prevent_initial_call=False,
    )

    # Display Filters collapse (Graph tab) — toggle on click, restore from store on page load
    app.clientside_callback(
        """
        function(n_clicks, stored) {
            var open;
            if (!n_clicks) {
                open = (stored !== null && stored !== undefined) ? stored : false;
            } else {
                open = !stored;
            }
            var chevron = document.getElementById('display-filters-chevron');
            if (chevron) chevron.style.transform = open ? '' : 'rotate(-90deg)';
            if (!n_clicks) {
                return [open, window.dash_clientside.no_update];
            }
            return [open, open];
        }
        """,
        Output("display-filters-collapse", "is_open"),
        Output("display-filters-open-store", "data"),
        Input("display-filters-toggle-btn", "n_clicks"),
        State("display-filters-open-store", "data"),
        prevent_initial_call=False,
    )

    # Advanced Network Options collapse — toggle on click, restore from store on page load
    app.clientside_callback(
        """
        function(n_clicks, stored) {
            var open;
            if (!n_clicks) {
                open = (stored !== null && stored !== undefined) ? stored : false;
            } else {
                open = !stored;
            }
            var chevron = document.getElementById('network-options-chevron');
            if (chevron) chevron.style.transform = open ? '' : 'rotate(-90deg)';
            if (!n_clicks) {
                return [open, window.dash_clientside.no_update];
            }
            return [open, open];
        }
        """,
        Output("network-options-collapse", "is_open"),
        Output("network-options-open-store", "data"),
        Input("network-options-toggle-btn", "n_clicks"),
        State("network-options-open-store", "data"),
        prevent_initial_call=False,
    )
