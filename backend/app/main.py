"""FastAPI application factory."""

from fastapi import FastAPI


def create_app() -> FastAPI:
    """Build the API application. Routes arrive with the slices that own them."""
    return FastAPI(title="FinbudAI")
