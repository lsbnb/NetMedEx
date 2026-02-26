try:
    import netmedex
    from netmedex import pubtator

    print("NetMedEx package imported successfully.")
    print("NetMedEx.pubtator module imported successfully.")
except ImportError as e:
    print(f"Import failed: {e}")
    exit(1)
except Exception as e:
    print(f"Error: {e}")
    exit(1)
