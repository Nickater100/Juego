import os

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

def asset_path(*parts: str) -> str:
    return os.path.join(PROJECT_ROOT, "assets", *parts)
