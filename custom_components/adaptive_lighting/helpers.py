"""Helper functions for the Adaptive Lighting custom components."""

from __future__ import annotations

import base64
import math


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))


def int_to_base36(num: int) -> str:
    """Convert an integer to its base-36 representation using numbers and uppercase letters.

    Base-36 encoding uses digits 0-9 and uppercase letters A-Z, providing a case-insensitive
    alphanumeric representation. The function takes an integer `num` as input and returns
    its base-36 representation as a string.

    Parameters
    ----------
    num
        The integer to convert to base-36.

    Returns
    -------
    str
        The base-36 representation of the input integer.

    Examples
    --------
    >>> num = 123456
    >>> base36_num = int_to_base36(num)
    >>> print(base36_num)
    '2N9'
    """
    alphanumeric_chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

    if num == 0:
        return alphanumeric_chars[0]

    base36_str = ""
    base = len(alphanumeric_chars)

    while num:
        num, remainder = divmod(num, base)
        base36_str = alphanumeric_chars[remainder] + base36_str

    return base36_str


def short_hash(string: str, length: int = 4) -> str:
    """Create a hash of 'string' with length 'length'."""
    return base64.b32encode(string.encode()).decode("utf-8").zfill(length)[:length]


def remove_vowels(input_str: str, length: int = 4) -> str:
    """Remove vowels from a string and return a string of length 'length'."""
    vowels = "aeiouAEIOU"
    output_str = "".join([char for char in input_str if char not in vowels])
    return output_str.zfill(length)[:length]


def color_difference_redmean(
    rgb1: tuple[float, float, float],
    rgb2: tuple[float, float, float],
) -> float:
    """Distance between colors in RGB space (redmean metric).

    The maximal distance between (255, 255, 255) and (0, 0, 0) ≈ 765.

    Sources:
    - https://en.wikipedia.org/wiki/Color_difference#Euclidean
    - https://www.compuphase.com/cmetric.htm
    """
    r_hat = (rgb1[0] + rgb2[0]) / 2
    delta_r, delta_g, delta_b = (
        (col1 - col2) for col1, col2 in zip(rgb1, rgb2, strict=True)
    )
    red_term = (2 + r_hat / 256) * delta_r**2
    green_term = 4 * delta_g**2
    blue_term = (2 + (255 - r_hat) / 256) * delta_b**2
    return math.sqrt(red_term + green_term + blue_term)
