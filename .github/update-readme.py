# Copyright (c) 2023, Bas Nijholt
# All rights reserved.
# When using this code, please cite the original source.
# and include the LICENSE file in your project.
"""Automatically update Markdown files with code block output.

Add code blocks between <!-- START_CODE --> and <!-- END_CODE --> in your Markdown file.
The output will be inserted between <!-- START_OUTPUT --> and <!-- END_OUTPUT -->.

Example:
-------
```
<!-- START_CODE -->
<!-- print('Hello, world!') -->
<!-- END_CODE -->
<!-- START_OUTPUT -->
This will be replaced by the output of the code block above.

<!-- END_OUTPUT -->
```
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path


def md_comment(text: str) -> str:
    """Format a string as a Markdown comment."""
    return f"<!-- {text} -->"


MARKERS = {
    "warning": md_comment("THIS CONTENT IS AUTOMATICALLY GENERATED"),
    "start_code": md_comment("START_CODE"),
    "end_code": md_comment("END_CODE"),
    "start_output": md_comment("START_OUTPUT"),
    "end_output": md_comment("END_OUTPUT"),
}


def remove_md_comment(commented_text: str) -> str:
    """Remove Markdown comment tags from a string."""
    if not (commented_text.startswith("<!-- ") and commented_text.endswith(" -->")):
        raise ValueError("Invalid Markdown comment format")
    return commented_text[5:-4]


def execute_code_block(code: list[str]) -> list[str]:
    """Execute a code block and return its output as a list of strings."""
    f = io.StringIO()
    with contextlib.redirect_stdout(f):
        exec("\n".join(code))  # noqa: S102
    return f.getvalue().split("\n")


def process_markdown(content: list[str]) -> list[str]:
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
    new_lines = []
    code = []
    in_code_block = in_output_block = False
    output = None

    for line in content:
        if MARKERS["start_code"] in line:
            in_code_block = True
        elif MARKERS["start_output"] in line:
            in_output_block = True
            new_lines.extend([line, MARKERS["warning"]] + output)
            output = None
        elif MARKERS["end_output"] in line:
            in_output_block = False
        elif in_code_block:
            if MARKERS["end_code"] in line:
                in_code_block = False
                output = execute_code_block(code)
                code = []
            else:
                code.append(remove_md_comment(line))

        if not in_output_block:
            new_lines.append(line)

    return new_lines


def update_markdown_file(filepath: Path) -> None:
    """Rewrite a Markdown file by executing and updating code blocks."""
    with filepath.open() as f:
        original_lines = [line.rstrip("\n") for line in f.readlines()]

    new_lines = process_markdown(original_lines)
    updated_content = "\n".join(new_lines).rstrip() + "\n"

    with filepath.open("w") as f:
        f.write(updated_content)


def test_process_markdown():
    def assert_process(input_lines, expected_output):
        output = process_markdown(input_lines)
        assert output == expected_output, f"Expected {expected_output}, got {output}"

    # Test case 1: Single code block
    input_lines = [
        "Some text",
        MARKERS["start_code"],
        md_comment("print('Hello, world!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        "This content will be replaced",
        MARKERS["end_output"],
        "More text",
    ]
    expected_output = [
        "Some text",
        MARKERS["start_code"],
        md_comment("print('Hello, world!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        MARKERS["warning"],
        "Hello, world!",
        "",
        MARKERS["end_output"],
        "More text",
    ]
    assert_process(input_lines, expected_output)

    # Test case 2: Two code blocks
    input_lines = [
        "Some text",
        MARKERS["start_code"],
        md_comment("print('Hello, world!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        "This content will be replaced",
        MARKERS["end_output"],
        "More text",
        MARKERS["start_code"],
        md_comment("print('Hello again!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        "This content will also be replaced",
        MARKERS["end_output"],
    ]
    expected_output = [
        "Some text",
        MARKERS["start_code"],
        md_comment("print('Hello, world!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        MARKERS["warning"],
        "Hello, world!",
        "",
        MARKERS["end_output"],
        "More text",
        MARKERS["start_code"],
        md_comment("print('Hello again!')"),
        MARKERS["end_code"],
        MARKERS["start_output"],
        MARKERS["warning"],
        "Hello again!",
        "",
        MARKERS["end_output"],
    ]
    assert_process(input_lines, expected_output)

    # Test case 3: No code blocks
    input_lines = [
        "Some text",
        "More text",
    ]
    expected_output = [
        "Some text",
        "More text",
    ]
    assert_process(input_lines, expected_output)


if __name__ == "__main__":
    test_process_markdown()
    update_markdown_file(Path(__file__).parent.parent / "README.md")
