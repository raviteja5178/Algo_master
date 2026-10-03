"""
pytest configuration — ensures the project root is on sys.path so all
packages are importable without installation.
"""
import sys
import os

# Add the sensex-auto-trader directory to the path
sys.path.insert(0, os.path.dirname(__file__))
