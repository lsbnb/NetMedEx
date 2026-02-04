try:
    print("Importing graph_update...")
    from webapp.callbacks import graph_update

    print("graph_update imported.")

    print("Importing chat_callbacks...")
    from webapp.callbacks import chat_callbacks

    print("chat_callbacks imported.")

    print("Importing node_rag...")
    from netmedex import node_rag

    print("node_rag imported.")

    print("Importing graph_rag...")
    from netmedex import graph_rag

    print("graph_rag imported.")

    print("All imports successful.")
except Exception as e:
    print(f"IMPORT ERROR: {e}")
    import traceback

    traceback.print_exc()
