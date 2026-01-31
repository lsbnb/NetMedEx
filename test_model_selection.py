"""
Quick test to verify model selection implementation.
This checks the UI components and callbacks are correctly defined.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

def test_ui_components():
    """Test that new UI components are defined correctly"""
    from webapp.components.advanced_settings import llm_config
    
    # Check that llm_config has children
    assert llm_config.children is not None, "llm_config should have children"
    
    # Find the openai-config div and check for model selector
    openai_config_found = False
    model_selector_found = False
    custom_input_found = False
    
    def search_components(component):
        nonlocal openai_config_found, model_selector_found, custom_input_found
        
        if hasattr(component, 'id'):
            if component.id == 'openai-config':
                openai_config_found = True
            elif component.id == 'openai-model-selector':
                model_selector_found = True
                # Check options
                assert len(component.options) == 7, f"Expected 7 options, got {len(component.options)}"
                assert component.value == "gpt-4o-mini", f"Expected default 'gpt-4o-mini', got {component.value}"
            elif component.id == 'openai-custom-model-div':
                custom_input_found = True
        
        if hasattr(component, 'children'):
            if isinstance(component.children, list):
                for child in component.children:
                    search_components(child)
            elif component.children is not None:
                search_components(component.children)
    
    search_components(llm_config)
    
    assert openai_config_found, "openai-config div not found"
    assert model_selector_found, "openai-model-selector dropdown not found"
    assert custom_input_found, "openai-custom-model-div not found"
    
    print("✅ UI components test passed!")
    return True


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
    has_config_callback = False
    
    for output_id in callback_list:
        if 'openai-custom-model-div.style' in str(output_id):
            has_custom_toggle = True
        if 'llm-config-status.children' in str(output_id):
            has_config_callback = True
    
    assert has_custom_toggle, "Custom model toggle callback not found"
    assert has_config_callback, "LLM configuration callback not found"
    
    print("✅ Callback signatures test passed!")
    return True


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Model Selection Implementation - Component Tests")
    print("="*60 + "\n")
    
    try:
        test_ui_components()
        test_callback_signatures()
        
        print("\n" + "="*60)
        print("All tests passed! ✅")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
