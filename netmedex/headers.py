from typing import TypedDict


class Headers(TypedDict):
    use_mesh_vocabulary: str


USE_MESH_VOCABULARY = "USE-MESH-VOCABULARY"

HEADERS = Headers(use_mesh_vocabulary=USE_MESH_VOCABULARY)
