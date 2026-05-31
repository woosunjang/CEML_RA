"""
Teaching Agent — Notebook Builder

Converts structured section data into Jupyter Notebook (.ipynb) JSON format.
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

NBFORMAT_VERSION = 4
NBFORMAT_MINOR = 5


def _markdown_cell(source: str) -> dict:
    """Create a Jupyter markdown cell."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def _code_cell(source: str) -> dict:
    """Create a Jupyter code cell."""
    return {
        "cell_type": "code",
        "metadata": {},
        "source": source.splitlines(keepends=True),
        "execution_count": None,
        "outputs": [],
    }


def parse_notebook_response(raw: str) -> list[dict]:
    """Parse LLM output with [MARKDOWN], [CODE], [EXERCISE] markers into cells.

    Returns a list of cell dicts in nbformat v4 format.
    """
    cells = []

    # Split by section markers
    pattern = r'\[(MARKDOWN|CODE|EXERCISE)\]\s*\n'
    parts = re.split(pattern, raw)

    # parts will be: [preamble, type1, content1, type2, content2, ...]
    # If there's preamble text before first marker, treat as markdown
    if parts[0].strip():
        cells.append(_markdown_cell(parts[0].strip()))

    i = 1
    while i < len(parts) - 1:
        section_type = parts[i].strip().upper()
        content = parts[i + 1].strip()
        i += 2

        if not content:
            continue

        if section_type == "MARKDOWN":
            cells.append(_markdown_cell(content))
        elif section_type == "CODE":
            cells.append(_code_cell(content))
        elif section_type == "EXERCISE":
            # Exercise: add as code cell with TODO header
            if not content.startswith("# TODO"):
                content = "# TODO: 실습 과제\n" + content
            cells.append(_code_cell(content))

    # Fallback: if no markers found, treat entire response as markdown
    if not cells and raw.strip():
        cells.append(_markdown_cell(raw.strip()))

    return cells


def build_notebook(title: str, cells: list[dict]) -> dict:
    """Build a complete Jupyter notebook dict from cells.

    Args:
        title: Notebook title (used in metadata).
        cells: List of cell dicts (from parse_notebook_response).

    Returns:
        Complete nbformat v4 compatible notebook dict.
    """
    return {
        "nbformat": NBFORMAT_VERSION,
        "nbformat_minor": NBFORMAT_MINOR,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.12.0",
            },
            "title": title,
        },
        "cells": cells,
    }


def notebook_to_json(notebook: dict) -> str:
    """Serialize notebook dict to JSON string."""
    return json.dumps(notebook, ensure_ascii=False, indent=1)


def build_notebook_from_response(title: str, raw_response: str) -> dict:
    """End-to-end: parse LLM response and build notebook.

    Args:
        title: Notebook title.
        raw_response: Raw LLM output with section markers.

    Returns:
        Complete notebook dict.
    """
    cells = parse_notebook_response(raw_response)
    return build_notebook(title, cells)
