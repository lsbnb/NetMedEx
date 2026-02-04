from webapp.app import app


def verify_callbacks():
    print("Verifying callbacks...")
    # Trigger callback collection
    # Note: app.py calls collect_callbacks(app) inside main(), but app object is global.
    # We need to manually call collect_callbacks to populate the map because importing app.py doesn't run main().
    from webapp.callbacks import collect_callbacks

    collect_callbacks(app)

    found_toggle = False
    found_switch = False

    for callback_id, callback in app.callback_map.items():
        inputs = callback["inputs"]
        outputs = callback["output"]

        # Check for toggle_panels
        # Input: sidebar-panel-toggle.active_tab
        has_sidebar_input = any(
            inp["id"] == "sidebar-panel-toggle" and inp["property"] == "active_tab"
            for inp in inputs
        )

        if has_sidebar_input:
            # Check outputs
            # It might be a list of outputs
            outs = outputs if isinstance(outputs, list) else [outputs]
            out_ids = []
            for o in outs:
                if hasattr(o, "component_id"):
                    out_ids.append(f"{o.component_id}.{o.component_property}")
                elif isinstance(o, dict):
                    out_ids.append(f"{o['id']}.{o['property']}")
                else:
                    out_ids.append(str(o))

            if "search-panel.style" in out_ids and "chat-panel-container.style" in out_ids:
                print(f"FOUND: toggle_panels callback. ID: {callback_id}")
                print(f"  Inputs: {inputs}")
                print(f"  Outputs: {out_ids}")
                found_toggle = True

        # Check for switch_to_graph_panel
        # Input: cy-graph-container.style
        has_container_input = any(
            inp["id"] == "cy-graph-container" and inp["property"] == "style" for inp in inputs
        )

        if has_container_input:
            outs = outputs if isinstance(outputs, list) else [outputs]
            # Check if o is dict or object
            out_ids = []
            for o in outs:
                if hasattr(o, "component_id"):
                    out_ids.append(f"{o.component_id}.{o.component_property}")
                elif isinstance(o, dict):
                    out_ids.append(f"{o['id']}.{o['property']}")
                else:
                    out_ids.append(str(o))

            if "sidebar-panel-toggle.active_tab" in out_ids:
                print(f"FOUND: switch_to_graph_panel callback. ID: {callback_id}")
                print(f"  Inputs: {inputs}")
                print(f"  Outputs: {out_ids}")
                found_switch = True

    if not found_toggle:
        print("ERROR: toggle_panels callback NOT FOUND!")
    if not found_switch:
        print("ERROR: switch_to_graph_panel callback NOT FOUND!")


if __name__ == "__main__":
    verify_callbacks()
