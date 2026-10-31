"""Model replies with LaTeX are parsed without losing them (spec 010)."""

from app.llm.client import parse_json_reply


def test_invalid_escapes_keep_their_backslash() -> None:
    raw = r'{"text": "La raíz: \(\sqrt{49} \cdot 2\)"}'

    assert parse_json_reply(raw) == {"text": r"La raíz: \(\sqrt{49} \cdot 2\)"}


def test_latex_commands_that_look_like_escapes_are_restored_in_math() -> None:
    raw = r'{"text": "\(\frac{1}{3} \times 2 \neq x \rightarrow \beta\)"}'

    assert (
        parse_json_reply(raw)["text"]
        == r"\(\frac{1}{3} \times 2 \neq x \rightarrow \beta\)"
    )


def test_display_math_is_restored_too() -> None:
    raw = r'{"text": "Despeja:\n\[x = \frac{12}{3}\]"}'

    assert parse_json_reply(raw)["text"] == "Despeja:\n" + r"\[x = \frac{12}{3}\]"


def test_text_outside_math_keeps_line_breaks_tabs_and_dollars() -> None:
    raw = r'{"text": "Cuesta 12 $.\nTotal:\t20 $", "cited": ["F1"]}'

    assert parse_json_reply(raw) == {
        "text": "Cuesta 12 $.\nTotal:\t20 $",
        "cited": ["F1"],
    }


def test_well_escaped_latex_is_unchanged() -> None:
    raw = r'{"text": "\\(\\frac{x}{2}\\)"}'

    assert parse_json_reply(raw)["text"] == r"\(\frac{x}{2}\)"


def test_nested_strings_are_restored() -> None:
    raw = r'{"options": [{"text": "\(\frac{1}{2}\)"}]}'

    assert parse_json_reply(raw) == {"options": [{"text": r"\(\frac{1}{2}\)"}]}


def test_unusable_replies_are_empty() -> None:
    assert parse_json_reply("not json") == {}
    assert parse_json_reply("[1, 2]") == {}


def test_form_feed_and_backspace_are_restored_everywhere() -> None:
    # Never real text; a model that drops the delimiters still keeps \frac and \beta.
    raw = r'{"text": "Es \frac{7}{2} y \beta.\nFin"}'

    assert parse_json_reply(raw)["text"] == "Es " + r"\frac{7}{2} y \beta." + "\nFin"
