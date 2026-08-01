"""HTML-escaping helper shared across every page module (kept dependency-free
so it can sit below shell/compare/static_export/etc. in the import graph)."""

import html


def _esc(s):
    return html.escape(str(s))
