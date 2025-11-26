"""Placeholder AST builder.

Currently the parser directly emits Node objects; this module exists so the
project structure is complete and can hold future AST-building logic.
"""
from __future__ import annotations

def build_ast_from_tokens(tokens):
    """Future: convert tokens to a richer AST. For now this is a passthrough."""
    return tokens
