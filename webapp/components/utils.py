import dash
from dash import html


def generate_param_title(title, descriptions, is_right=False):
    class_name = "info-outer info-right" if is_right else "info-outer info-left"
    kwargs = {"data-tooltip": descriptions, "data-x": "0px", "data-y": "0px"}
    return html.Div(
        [
            html.H5(title),
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
