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
    """Find 'a' and 'b' for a scaled and shifted tanh function.

    Given two points (x1, y1) and (x2, y2), this function solves for 'a' and 'b' such that
    the scaled and shifted tanh function passes through these points. The function is
    defined as: y = 0.5 * (tanh(a * (x - b)) + 1)

    The steps to find 'a' and 'b' are as follows:
    1. Set up two equations based on the definition of the scaled and shifted tanh function:
        y1 = 0.5 * (tanh(a * (x1 - b)) + 1)
        y2 = 0.5 * (tanh(a * (x2 - b)) + 1)
    2. Rearrange these equations:
        tanh(a * (x1 - b)) = 2*y1 - 1
        tanh(a * (x2 - b)) = 2*y2 - 1
    3. Take the inverse tanh (or artanh) of both sides:
        a * (x1 - b) = artanh(2*y1 - 1)
        a * (x2 - b) = artanh(2*y2 - 1)
    4. Solve these linear equations to find the values of 'a' and 'b'.

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
    tuple
        A tuple containing the values of 'a' and 'b'.

    Raises
    ------
    ValueError
        If 'y1' or 'y2' is not between 0 and 1.
    """
    # Check the y values
    if not (0 <= y1 <= 1) or not (0 <= y2 <= 1):
        msg = "y1 and y2 should be between 0 and 1."
        raise ValueError(msg)

    # Calculate the inverse tanh values
    z1 = math.atanh(2 * y1 - 1)
    z2 = math.atanh(2 * y2 - 1)

    # Solve the equations to find 'a' and 'b'
    a = (z2 - z1) / (x2 - x1)
    b = (x1 * z2 - x2 * z1) / (x1 - x2)

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
