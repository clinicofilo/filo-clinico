"""
Entry point per il deployment Vercel Serverless / Service.
Espone l'istanza FastAPI `app`.
"""
from server import app

__all__ = ["app"]
