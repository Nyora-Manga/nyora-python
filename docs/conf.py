"""Sphinx configuration for the Nyora Python documentation.

Builds the HTML docs served at https://nyora.xyz/docs/python/. The ``src``
directory is inserted on ``sys.path`` so :mod:`autodoc` can import the real
``nyora`` and ``nyora_tui`` packages and document them from source.
"""

from __future__ import annotations

import os
import sys

# Make the importable packages (``nyora`` / ``nyora_tui``) available to autodoc.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.abspath(os.path.join(_HERE, "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# -- Project information ------------------------------------------------------

project = "Nyora Python"
author = "Md Hasan Raza"
copyright = "2026, Md Hasan Raza"  # noqa: A001
release = "2.1.4"
version = "2.1.4"

# -- General configuration ----------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx_copybutton",
]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- MyST (Markdown) ----------------------------------------------------------

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "linkify",
    "substitution",
    "tasklist",
]
myst_heading_anchors = 3

# -- Autodoc ------------------------------------------------------------------

autodoc_default_options = {
    "members": True,
    "show-inheritance": True,
    "undoc-members": False,
}
autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_typehints_description_target = "documented"
autoclass_content = "both"

# -- Napoleon (Google-style docstrings) ---------------------------------------

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_rtype = True
napoleon_use_param = True
# Render docstring ``Attributes:`` sections as inline ``:ivar:`` fields rather
# than separate ``py:attribute`` directives. This avoids duplicate object
# descriptions for dataclass fields (documented once by autodoc, once by the
# docstring) while keeping the attribute documentation visible.
napoleon_use_ivar = True

# -- sphinx-autodoc-typehints -------------------------------------------------

always_document_param_types = True
typehints_fully_qualified = False

# -- Intersphinx --------------------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- HTML output --------------------------------------------------------------

html_theme = "furo"
html_title = "Nyora Python"
html_baseurl = "https://nyora.xyz/docs/python/"
html_static_path = ["_static"]
html_css_files = ["brand.css"]

# Furo light/dark theme variables, defaulting to the dark Nyora brand palette.
html_theme_options = {
    "light_css_variables": {
        "font-stack": "'Mori', ui-sans-serif, system-ui, sans-serif",
        "font-stack--monospace": "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace",
        "color-brand-primary": "#0ae448",
        "color-brand-content": "#00bae2",
        "color-background-primary": "#fffce1",
        "color-background-secondary": "#f4f1d8",
        "color-foreground-primary": "#0e100f",
        "color-foreground-secondary": "#3a3c36",
        "color-sidebar-background": "#f4f1d8",
        "color-sidebar-brand-text": "#0e100f",
    },
    "dark_css_variables": {
        "font-stack": "'Mori', ui-sans-serif, system-ui, sans-serif",
        "font-stack--monospace": "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, monospace",
        "color-brand-primary": "#0ae448",
        "color-brand-content": "#9d95ff",
        "color-background-primary": "#0e100f",
        "color-background-secondary": "#14171560",
        "color-background-hover": "#1a1d1b",
        "color-foreground-primary": "#fffce1",
        "color-foreground-secondary": "rgba(255, 252, 225, 0.66)",
        "color-foreground-muted": "rgba(255, 252, 225, 0.66)",
        "color-foreground-border": "rgba(255, 252, 225, 0.1)",
        "color-background-border": "rgba(255, 252, 225, 0.1)",
        "color-sidebar-background": "#0e100f",
        "color-sidebar-brand-text": "#fffce1",
        "color-sidebar-link-text--top-level": "#fffce1",
    },
}

# Copy the LLM-friendly index into the built docs root.
html_extra_path = ["llms.txt"]
