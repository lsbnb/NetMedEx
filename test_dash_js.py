from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        errors = []
        page.on("pageerror", lambda err: errors.append(f"JS Exception: {err}"))
        page.on("console", lambda msg: errors.append(f"Console {msg.type}: {msg.text}") if msg.type in ['error', 'warning'] else None)
        
        print("Navigating to http://127.0.0.1:8050")
        try:
            page.goto("http://127.0.0.1:8050", wait_until="networkidle", timeout=10000)
            print("Loaded. Waiting 2 seconds for callbacks...")
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Error navigating: {e}")
            
        print("--- Browser Errors & Warnings ---")
        for err in errors:
            print(err)
            
        browser.close()

run()
