import sys
import os

# Project root → src on path so `concierge` package resolves
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
