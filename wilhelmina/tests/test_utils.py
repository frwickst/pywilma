"""Tests for utils."""

from wilhelmina.utils import html_to_markdown


def test_html_to_markdown() -> None:
    """Test conversion of HTML to Markdown."""
    # Test basic conversion
    html = "<p>This is a paragraph</p>"
    assert html_to_markdown(html) == "This is a paragraph"

    # Test with links
    html = "<p>Check out <a href='https://example.com'>this link</a></p>"
    assert html_to_markdown(html) == "Check out [this link](<https://example.com>)"

    # Test with formatting
    html = "<p><strong>Bold</strong> and <em>italic</em> text</p>"
    assert html_to_markdown(html) == "**Bold** and _italic_ text"

    # Test with lists
    html = "<ul><li>Item 1</li><li>Item 2</li></ul>"
    expected = "* Item 1\n  * Item 2"
    assert html_to_markdown(html) == expected

    # Test with empty string
    assert html_to_markdown("") == ""
