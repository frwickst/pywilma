"""Utility functions for Wilma client."""

import html2text

# Configure html2text
_html_converter = html2text.HTML2Text()
_html_converter.ignore_links = False
_html_converter.body_width = 0  # No wrapping
_html_converter.unicode_snob = True
_html_converter.protect_links = True
_html_converter.images_to_alt = True


def html_to_markdown(html: str) -> str:
    """Convert HTML to Markdown.

    Args:
        html: HTML content

    Returns:
        Markdown content
    """
    return _html_converter.handle(html).strip()
