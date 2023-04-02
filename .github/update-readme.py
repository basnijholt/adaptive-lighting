"""Are you tired of manually updating Markdown files with code output?.

Fear not! With this script, you can easily insert code block output into
the designated content section of your Markdown file.

Here's how it works: you simply add your code block
between <!-- START_CODE --> and <!-- END_CODE -->, and the output
will automatically be inserted between <!-- START_OUTPUT -->
and <!-- END_OUTPUT -->. It's like magic, but without the rabbits.

This script can be run locally for your convenience, or it can
be integrated with your CI service for automatic updates.
Say goodbye to the tedium of manually updating Markdown files,
and hello to a more efficient workflow!

Example:
-------
```
<!-- START_CODE -->
<!-- print('Hello, world!') -->
<!-- END_CODE -->
<!-- START_OUTPUT -->
This will be overwritten by the output of the CODE_BLOCK above.
<!-- END_OUTPUT -->
```
"""
import contextlib
import io
from pathlib import Path
import textwrap


def to_markdown_comment(text: str) -> str:
    """Format a string as a Markdown comment.

    Parameters
    ----------
    text
        The text to include in the comment.

    Returns
    -------
    str
        A string formatted as a Markdown comment.
    """
    return f"<!-- {text} -->"


AUTO_GENERATED_WARNING = to_markdown_comment(
    "THIS CONTENT IS AUTOMATICALLY GENERATED",
)
START_CODE = to_markdown_comment("START_CODE")
END_CODE = to_markdown_comment("END_CODE")
START_OUTPUT = to_markdown_comment("START_OUTPUT")
END_OUTPUT = to_markdown_comment("END_OUTPUT")


def from_markdown_comment(commented_text: str) -> str:
    """Remove Markdown comment tags from a string.

    Parameters
    ----------
    commented_text
        The text to remove the comment tags from.

    Returns
    -------
    str
        A string with the comment tags removed.

    Raises
    ------
    AssertionError
        If the input string is not in the expected format with `<!--` and `-->` tags.

    Examples
    --------
    >>> from_markdown_comment("<!-- This is a comment -->")
    'This is a comment'
    """
    if not commented_text.startswith("<!-- ") or not commented_text.endswith(
        " -->",
    ):
        msg = "Invalid Markdown comment format"
        raise ValueError(msg)
    return commented_text.replace("<!-- ", "").replace(" -->", "")


def parse_and_execute_markdown(content: list[str]) -> list[str]:
    """Executes code blocks in a list of Markdown-formatted strings and returns the modified list.

    Parameters
    ----------
    content
        A list of Markdown-formatted strings.

    Returns
    -------
    list[str]
        A modified list of Markdown-formatted strings with code block output inserted.
    """
    assert isinstance(content, list), "Input must be a list"
    if not content:
        return content

    new_lines: list[str] = []
    code: list[str] = []
    in_code_block = False
    in_output_block = False
    output: list[str] | None = None

    for line in content:
        if START_CODE in line:
            in_code_block = True
            new_lines.append(line)
            continue

        if START_OUTPUT in line:
            in_output_block = True
            new_lines.append(line)
            msg = AUTO_GENERATED_WARNING
            new_lines.append(msg)
            assert output is not None
            new_lines.extend(output)
            output = None
            continue

        if in_output_block:
            if END_OUTPUT in line:
                in_output_block = False
                new_lines.append(line)
                continue
        else:
            new_lines.append(line)

        if in_code_block:
            if END_CODE in line:
                in_code_block = False
                output = run_code_block(code)
                code = []
            else:
                code.append(from_markdown_comment(line))

    return new_lines


def run_code_block(code: list[str]) -> list[str]:
    """Execute a code block and return its output as a list of strings.

    Parameters
    ----------
    code
        A list of strings representing the code block.

    Returns
    -------
    list[str]
        A list of strings representing the output of the code block.
    """
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        exec("\n".join(code))  # noqa: S102
    return f.getvalue().split("\n")


def ensure_newline_at_end(text: str) -> str:
    """Ensure that a string ends with a newline character.

    Parameters
    ----------
    text
        The input string.

    Returns
    -------
    str
        The input string with a newline character at the end, if it didn't have one already.
    """
    if not text:
        # Empty string, otherwise it would have two newlines.
        return ""

    if not text.endswith("\n"):
        text += "\n"

    return text


def execute_and_write_markdown_file(markdown_path: Path) -> None:
    """Rewrites a Markdown file by parsing and executing the Markdown content.

    Parameters
    ----------
    markdown_path
        The path to the Markdown file.

    Returns
    -------
    None
    """
    with markdown_path.open() as f:
        original_lines = f.readlines()
        original_lines = [line.rstrip("\n") for line in original_lines]
    new_lines = parse_and_execute_markdown(original_lines)
    new_joined_lines = ensure_newline_at_end("\n".join(new_lines))
    with markdown_path.open("w") as f:
        f.write(new_joined_lines)


def test() -> None:
    """Test the script."""
    input_lines = [
        "Some text",
        START_CODE,
        "<!-- print('Hello, world!') -->",
        END_CODE,
        START_OUTPUT,
        "Some content",
        END_OUTPUT,
        "More text",
    ]
    expected_output = [
        "Some text",
        START_CODE,
        "<!-- print('Hello, world!') -->",
        END_CODE,
        START_OUTPUT,
        AUTO_GENERATED_WARNING,
        "Hello, world!",
        "",
        END_OUTPUT,
        "More text",
    ]
    output = parse_and_execute_markdown(input_lines)
    assert output == expected_output

    def assert_parse(input_text: str, expected_output: str) -> None:
        input_text = textwrap.dedent(input_text)
        expected_output = textwrap.dedent(expected_output)
        output = parse_and_execute_markdown(input_text.split("\n"))
        assert output == expected_output.split("\n")

    single_code_block = f"""\
        This text should not change.

        {START_CODE}
        <!-- print("foo") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        bar
        {END_OUTPUT}

        This text should also not change.
        """

    single_code_block_output = f"""\
        This text should not change.

        {START_CODE}
        <!-- print("foo") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        foo

        {END_OUTPUT}

        This text should also not change.
        """
    assert_parse(single_code_block, single_code_block_output)

    double_code_block = f"""\
        This text should not change.

        {START_CODE}
        <!-- print("foo") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        bar
        {END_OUTPUT}

        This text should also not change.

        {START_CODE}
        <!-- print("bar") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        foo
        {END_OUTPUT}
        """

    double_code_block_output = f"""\
        This text should not change.

        {START_CODE}
        <!-- print("foo") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        foo

        {END_OUTPUT}

        This text should also not change.

        {START_CODE}
        <!-- print("bar") -->
        {END_CODE}

        {START_OUTPUT}
        {AUTO_GENERATED_WARNING}
        bar

        {END_OUTPUT}
        """
    assert_parse(double_code_block, double_code_block_output)


if __name__ == "__main__":
    test()
    execute_and_write_markdown_file(Path(__file__).parent.parent / "README.md")
