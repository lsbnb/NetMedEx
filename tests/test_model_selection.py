"""
Quick test to verify model selection implementation.
This checks the UI components and callbacks are correctly defined.
"""

import sys
import os

# Add parent directory to path
# Add project root to path (parent of current directory's parent)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_ui_components():
    """Test that provider-specific UI components are defined correctly"""
    import dash
    from unittest.mock import patch

    # Mock get_asset_url since it's called at import time
    with patch("dash.get_asset_url", return_value="assets/icon_config.svg"):
        from webapp.components.advanced_settings import llm_config

    # Check that llm_config has children
    assert llm_config.children is not None, "llm_config should have children"

    # Find provider-specific config sections and key controls
    openai_config_found = False
    google_config_found = False
    google_params_found = False
    local_config_found = False
    model_selector_found = False
    custom_input_found = False
    verify_btn_found = False
    provider_has_google_option = False

    def search_components(component):
        nonlocal openai_config_found
        nonlocal google_config_found
        nonlocal google_params_found
        nonlocal local_config_found
        nonlocal model_selector_found
        nonlocal custom_input_found
        nonlocal verify_btn_found
        nonlocal provider_has_google_option

        if hasattr(component, "id"):
            if component.id == "openai-config":
                openai_config_found = True
            elif component.id == "google-config":
                google_config_found = True
            elif component.id == "google-params-config":
                google_params_found = True
            elif component.id == "local-llm-config":
                local_config_found = True
            elif component.id == "openai-model-selector":
                model_selector_found = True
                # Check options
                assert len(component.options) == 7, (
                    f"Expected 7 options, got {len(component.options)}"
                )
                assert component.value == "gpt-4o-mini", (
                    f"Expected default 'gpt-4o-mini', got {component.value}"
                )
            elif component.id == "openai-custom-model-div":
                custom_input_found = True
            elif component.id == "verify-llm-connection-btn":
                verify_btn_found = True
            elif component.id == "llm-provider-selector":
                option_values = [opt["value"] for opt in component.options]
                provider_has_google_option = "google" in option_values

        if hasattr(component, "children"):
            if isinstance(component.children, list):
                for child in component.children:
                    search_components(child)
            elif component.children is not None:
                search_components(component.children)

    search_components(llm_config)

    assert openai_config_found, "openai-config div not found"
    assert google_config_found, "google-config div not found"
    assert google_params_found, "google-params-config div not found"
    assert local_config_found, "local-llm-config div not found"
    assert model_selector_found, "openai-model-selector dropdown not found"
    assert custom_input_found, "openai-custom-model-div not found"
    assert verify_btn_found, "verify-llm-connection-btn not found"
    assert provider_has_google_option, "Google provider option not found"

    print("✅ UI components test passed!")


def test_callback_signatures():
    """Test that callbacks have correct signatures"""
    from webapp import app as webapp_app
    from webapp.callbacks import llm_callbacks

    # Create a test app
    import dash

    app = dash.Dash(__name__)

    # Register callbacks
    llm_callbacks.callbacks(app)

    # Check that callbacks are registered
    callback_list = app.callback_map

    # Look for our new callbacks
    has_custom_toggle = False
    has_verify_callback = False

    for output_id in callback_list:
        if "openai-custom-model-div.style" in str(output_id):
            has_custom_toggle = True
        if "llm-config-status.children" in str(output_id):
            has_verify_callback = True

    assert has_custom_toggle, "Custom model toggle callback not found"
    assert has_verify_callback, "LLM verify callback not found"

    print("✅ Callback signatures test passed!")


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Model Selection Implementation - Component Tests")
    print("=" * 60 + "\n")

    try:
        test_ui_components()
        test_callback_signatures()

        print("\n" + "=" * 60)
        print("All tests passed! ✅")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
