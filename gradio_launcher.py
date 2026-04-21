"""
Simple launcher for the Gradio interface.
Run this script to start the web UI for the arXiv Paper Curator RAG system.
"""

import sys
from pathlib import Path

# Add src to Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from src.gradio_app import main

if __name__ == "__main__":
    main()
