"""Shared pydantic schemas for juscraper public APIs (refs #93)."""
from .cjsg import OutputCJSGBase, SearchBase

__all__ = ["SearchBase", "OutputCJSGBase"]
