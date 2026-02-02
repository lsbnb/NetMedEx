from __future__ import annotations

import dash
from dash import html


def generate_param_title(title, descriptions, is_right=False, id=None):
    class_name = "info-outer info-right" if is_right else "info-outer info-left"
    kwargs = {"data-tooltip": descriptions, "data-x": "0px", "data-y": "0px"}

    # Handle optional ID for H5
    h5_props = {"children": title}
    if id:
        h5_props["id"] = id

    return html.Div(
        [
            html.H5(**h5_props),
            html.Span(
                [
                    html.Img(src=dash.get_asset_url("icon_info.svg"), className="info-img"),
                ],
                className=class_name,
                **kwargs,
            ),
        ],
        className="param-title",
    )


def icon_download():
    return html.Img(
        src=dash.get_asset_url("icon_download.svg"),
        width=20,
        height=20,
        style={"margin-right": "5px"},
    )


def icon_search():
    return html.Img(
        src=dash.get_asset_url("icon_search.svg"),
        width=20,
        height=20,
        style={"margin-right": "5px"},
    )


def icon_graph():
    return html.Img(
        src=dash.get_asset_url("icon_graph.svg"),
        width=20,
        height=20,
        style={"margin-right": "5px"},
    )


def icon_chat():
    return html.Img(
        src=dash.get_asset_url("icon_chat.svg"),
        width=20,
        height=20,
        style={"margin-right": "5px"},
    )
