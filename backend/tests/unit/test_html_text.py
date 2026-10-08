"""Turning Greenhouse's entity-escaped HTML into safe plain text (document 13, section 5.1)."""

from jobs_radar.adapters.sources.html_text import html_to_text

ESCAPED = (
    "&lt;div&gt;&lt;h2&gt;About the role&lt;/h2&gt;&lt;p&gt;Design &amp;amp; evaluate &lt;em&gt;LLM&lt;/em&gt; features.&lt;/p&gt;"
    "&lt;ul&gt;&lt;li&gt;Remote in EU&lt;/li&gt;&lt;li&gt;12-month contract&lt;/li&gt;&lt;/ul&gt;&lt;/div&gt;"
)


def test_entities_are_decoded_and_structure_becomes_lines() -> None:
    text = html_to_text(ESCAPED)
    assert "Design & evaluate LLM features." in text
    assert "About the role" in text.splitlines()[0]
    assert "- Remote in EU" in text.splitlines()
    assert "- 12-month contract" in text.splitlines()
    assert "<" not in text and "&amp;" not in text


def test_scripts_styles_and_event_handlers_are_removed() -> None:
    html = '&lt;p onclick="steal()"&gt;Hello&lt;/p&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;style&gt;p{color:red}&lt;/style&gt;'
    text = html_to_text(html)
    assert text == "Hello"
    assert "alert" not in text and "steal" not in text and "color" not in text


def test_tracking_pixels_and_images_disappear() -> None:
    html = '&lt;p&gt;Text&lt;/p&gt;&lt;img style="display:none" src="https://tracker.example.test/p?id=1"&gt;'
    text = html_to_text(html)
    assert text == "Text"
    assert "tracker" not in text


def test_iframes_and_forms_are_removed() -> None:
    html = '&lt;iframe src="https://evil.example.test"&gt;&lt;/iframe&gt;&lt;form&gt;&lt;input name=x&gt;&lt;/form&gt;&lt;p&gt;Keep&lt;/p&gt;'
    assert html_to_text(html) == "Keep"


def test_non_breaking_spaces_and_runs_of_space_are_normalised() -> None:
    assert html_to_text("&lt;p&gt;Apply&amp;nbsp;now   please&lt;/p&gt;") == "Apply now please"


def test_inline_tags_do_not_split_words() -> None:
    assert (
        html_to_text("&lt;p&gt;Senior &lt;strong&gt;AI&lt;/strong&gt;Engineer&lt;/p&gt;")
        == "Senior AIEngineer"
    )


def test_empty_and_missing_content_give_an_empty_string() -> None:
    assert html_to_text("") == ""
    assert html_to_text(None) == ""


def test_plain_text_without_markup_is_kept() -> None:
    assert html_to_text("Just some text.") == "Just some text."


def test_blank_lines_are_collapsed() -> None:
    text = html_to_text(
        "&lt;p&gt;One&lt;/p&gt;&lt;p&gt;&lt;/p&gt;&lt;p&gt;&lt;/p&gt;&lt;p&gt;Two&lt;/p&gt;"
    )
    assert text == "One\n\nTwo"
