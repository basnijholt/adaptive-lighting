"""Helper functions for the Adaptive Lighting custom components."""

from __future__ import annotations

import base64
import colorsys
import logging
import math
from typing import cast

_LOGGER = logging.getLogger(__name__)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))


def find_a_b(x1: float, x2: float, y1: float, y2: float) -> tuple[float, float]:
    """Compute the values of 'a' and 'b' for a scaled and shifted tanh function.

    Given two points (x1, y1) and (x2, y2), this function calculates the coefficients 'a' and 'b'
    for a tanh function of the form y = 0.5 * (tanh(a * (x - b)) + 1) that passes through these points.

    The derivation is as follows:

    1. Start with the equation of the tanh function:
       y = 0.5 * (tanh(a * (x - b)) + 1)

    2. Rearrange the equation to isolate tanh:
       tanh(a * (x - b)) = 2*y - 1

    3. Take the inverse tanh (or artanh) on both sides to solve for 'a' and 'b':
       a * (x - b) = artanh(2*y - 1)

    4. Plug in the points (x1, y1) and (x2, y2) to get two equations.
       Using these, we can solve for 'a' and 'b' as:
       a = (artanh(2*y2 - 1) - artanh(2*y1 - 1)) / (x2 - x1)
       b = x1 - (artanh(2*y1 - 1) / a)

    Parameters
    ----------
    x1
        x-coordinate of the first point.
    x2
        x-coordinate of the second point.
    y1
        y-coordinate of the first point (should be between 0 and 1).
    y2
        y-coordinate of the second point (should be between 0 and 1).

    Returns
    -------
    a
        Coefficient 'a' for the tanh function.
    b
        Coefficient 'b' for the tanh function.

    Notes
    -----
    The values of y1 and y2 should lie between 0 and 1, inclusive.
    """
    a = (math.atanh(2 * y2 - 1) - math.atanh(2 * y1 - 1)) / (x2 - x1)
    b = x1 - (math.atanh(2 * y1 - 1) / a)
    return a, b


def scaled_tanh(
    x: float,
    a: float,
    b: float,
    y_min: float = 0.0,
    y_max: float = 100.0,
) -> float:
    """Apply a scaled and shifted tanh function to a given input.

    This function represents a transformation of the tanh function that scales and shifts
    the output to lie between y_min and y_max. For values of 'x' close to 'x1' and 'x2'
    (used to calculate 'a' and 'b'), the output of this function will be close to 'y_min'
    and 'y_max', respectively.

    The equation of the function is as follows:
    y = y_min + (y_max - y_min) * 0.5 * (tanh(a * (x - b)) + 1)

    Parameters
    ----------
    x
        The input to the function.
    a
        The scale factor for the tanh function, found using 'find_a_b' function.
    b
        The shift factor for the tanh function, found using 'find_a_b' function.
    y_min
        The minimum value of the output range. Defaults to 0.
    y_max
        The maximum value of the output range. Defaults to 100.

    Returns
    -------
        float: The output of the function, which lies in the range [y_min, y_max].
    """
    return y_min + (y_max - y_min) * 0.5 * (math.tanh(a * (x - b)) + 1)


def lerp_color_hsv(
    rgb1: tuple[float, float, float],
    rgb2: tuple[float, float, float],
    t: float,
) -> tuple[int, int, int]:
    """Linearly interpolate between two RGB colors in HSV color space."""
    t = abs(t)
    assert 0 <= t <= 1

    # Convert RGB to HSV
    hsv1 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb1])
    hsv2 = colorsys.rgb_to_hsv(*[x / 255.0 for x in rgb2])

    # Linear interpolation in HSV space
    hsv = (
        hsv1[0] + t * (hsv2[0] - hsv1[0]),
        hsv1[1] + t * (hsv2[1] - hsv1[1]),
        hsv1[2] + t * (hsv2[2] - hsv1[2]),
    )

    # Convert back to RGB
    rgb = tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(*hsv))
    assert all(0 <= x <= 255 for x in rgb), f"Invalid RGB color: {rgb}"
    return cast(tuple[int, int, int], rgb)


def lerp(x, x1, x2, y1, y2):
    """Linearly interpolate between two values."""
    return y1 + (x - x1) * (y2 - y1) / (x2 - x1)


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
