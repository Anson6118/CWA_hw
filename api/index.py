import os
import sys

# Add the parent directory to sys.path so we can import server.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import app  # noqa: E402  (Vercel looks for the `app` WSGI instance)
