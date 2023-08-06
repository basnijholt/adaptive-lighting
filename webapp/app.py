"""Simple web app to visualize brightness over time."""

import math

import matplotlib.pyplot as plt
import numpy as np
from shiny import App, render, ui


def lerp(x, x1, x2, y1, y2):
    """Linearly interpolate between two values."""
    return y1 + (x - x1) * (y2 - y1) / (x2 - x1)


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp value between minimum and maximum."""
    return max(minimum, min(value, maximum))


def find_a_b(x1: float, x2: float, y1: float, y2: float) -> tuple[float, float]:
    a = (math.atanh(2 * y2 - 1) - math.atanh(2 * y1 - 1)) / (x2 - x1)
    b = x1 - (math.atanh(2 * y1 - 1) / a)
    return a, b


def scaled_tanh(
    x: float,
    a: float,
    b: float,
    y_min: float = 0.0,
    y_max: float = 1.0,
) -> float:
    """Apply a scaled and shifted tanh function to a given input."""
    return y_min + (y_max - y_min) * 0.5 * (math.tanh(a * (x - b)) + 1)


def is_closer_to_sunrise_than_sunset(time, sunrise_time, sunset_time):
    """Return True if the time is closer to sunrise than sunset."""
    return abs(time - sunrise_time) < abs(time - sunset_time)


def brightness_linear(
    time,
    sunrise_time,
    sunset_time,
    time_light,
    time_dark,
    max_brightness,
    min_brightness,
):
    """Calculate the brightness for the 'linear' mode."""
    closer_to_sunrise = is_closer_to_sunrise_than_sunset(
        time,
        sunrise_time,
        sunset_time,
    )
    if closer_to_sunrise:
        brightness = lerp(
            time,
            x1=sunrise_time - time_dark,
            x2=sunrise_time + time_light,
            y1=min_brightness,
            y2=max_brightness,
        )
    else:
        brightness = lerp(
            time,
            x1=sunset_time - time_light,
            x2=sunset_time + time_dark,
            y1=max_brightness,
            y2=min_brightness,
        )
    return clamp(brightness, min_brightness, max_brightness)


def brightness_tanh(
    time,
    sunrise_time,
    sunset_time,
    time_light,
    time_dark,
    max_brightness,
    min_brightness,
):
    """Calculate the brightness for the 'tanh' mode."""
    closer_to_sunrise = is_closer_to_sunrise_than_sunset(
        time,
        sunrise_time,
        sunset_time,
    )
    if closer_to_sunrise:
        a, b = find_a_b(
            x1=-time_dark,
            x2=time_light,
            y1=0.05,  # be at 5% of range at x1
            y2=0.95,  # be at 95% of range at x2
        )
        brightness = scaled_tanh(
            time - sunrise_time,
            a=a,
            b=b,
            y_min=min_brightness,
            y_max=max_brightness,
        )
    else:
        a, b = find_a_b(
            x1=-time_light,  # shifted timestamp for the start of sunset
            x2=time_dark,  # shifted timestamp for the end of sunset
            y1=0.95,  # be at 95% of range at the start of sunset
            y2=0.05,  # be at 5% of range at the end of sunset
        )
        brightness = scaled_tanh(
            time - sunset_time,
            a=a,
            b=b,
            y_min=min_brightness,
            y_max=max_brightness,
        )
    return clamp(brightness, min_brightness, max_brightness)


SEC_PER_HR = 60 * 60

# Shiny UI
app_ui = ui.page_fluid(
    ui.layout_sidebar(
        ui.panel_sidebar(
            ui.input_slider("min_brightness", "min_brightness", 0, 100, 30, post="%"),
            ui.input_slider("max_brightness", "max_brightness", 0, 100, 100, post="%"),
            ui.input_slider(
                "dark_time",
                "brightness_mode_time_dark",
                0,
                5 * SEC_PER_HR,
                3 * SEC_PER_HR,
                post=" sec",
            ),
            ui.input_slider(
                "light_time",
                "brightness_mode_time_light",
                0,
                5 * SEC_PER_HR,
                0.5 * SEC_PER_HR,
                post=" sec",
            ),
            ui.input_slider(
                "sunrise_time",
                "sunrise_time",
                0,
                24,
                6,
                step=0.5,
                post=" hr",
            ),
            ui.input_slider(
                "sunset_time",
                "sunset_time",
                0,
                24,
                18,
                step=0.5,
                post=" hr",
            ),
        ),
        ui.panel_main(ui.output_plot(id="brightness_plot")),
    ),
)


def server(input, output, session):
    @output
    @render.plot
    def brightness_plot():
        return plot_brightness(
            min_brightness=input.min_brightness() / 100,
            max_brightness=input.max_brightness() / 100,
            brightness_mode_time_dark=input.dark_time() / SEC_PER_HR,
            brightness_mode_time_light=input.light_time() / SEC_PER_HR,
            sunrise_time=input.sunrise_time(),
            sunset_time=input.sunset_time(),
        )


def plot_brightness(
    min_brightness,
    max_brightness,
    brightness_mode_time_dark,
    brightness_mode_time_light,
    sunrise_time=6,  # 6 AM
    sunset_time=18,  # 6 PM
):
    # Define the time range for our simulation
    time_range = np.linspace(0, 24, 1000)  # From 0 to 24 hours

    # Calculate the brightness for each time in the time range for both modes
    brightness_linear_values = [
        brightness_linear(
            time,
            sunrise_time,
            sunset_time,
            brightness_mode_time_light,
            brightness_mode_time_dark,
            max_brightness,
            min_brightness,
        )
        for time in time_range
    ]
    brightness_tanh_values = [
        brightness_tanh(
            time,
            sunrise_time,
            sunset_time,
            brightness_mode_time_light,
            brightness_mode_time_dark,
            max_brightness,
            min_brightness,
        )
        for time in time_range
    ]

    # Plot the brightness over time for both modes
    plt.figure(figsize=(10, 6))
    plt.plot(time_range, brightness_linear_values, label="Linear Mode")
    plt.plot(time_range, brightness_tanh_values, label="Tanh Mode")
    plt.vlines(sunrise_time, 0, 1, color="C2", label="Sunrise", linestyles="dashed")
    plt.vlines(sunset_time, 0, 1, color="C3", label="Sunset", linestyles="dashed")
    plt.xlim(0, 24)
    plt.xticks(np.arange(0, 25, 1))
    yticks = np.arange(0, 1.05, 0.05)
    ytick_labels = [f"{100*label:.0f}%" for label in yticks]
    plt.yticks(yticks, ytick_labels)
    plt.xlabel("Time (hours)")
    plt.ylabel("Brightness")
    plt.title("Brightness over Time for Different Modes")

    # Add text box
    textstr = "\n".join(
        (
            f"Sunrise Time = {sunrise_time}:00:00",
            f"Sunset Time = {sunset_time}:00:00",
            f"Max Brightness = {max_brightness*100:.0f}%",
            f"Min Brightness = {min_brightness*100:.0f}%",
            f"Time Light = {brightness_mode_time_light:.1f} hours",
            f"Time Dark = {brightness_mode_time_dark:.1f} hours",
        ),
    )

    # these are matplotlib.patch.Patch properties
    props = {"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5}

    plt.legend()
    plt.grid(True)

    # place a text box in upper left in axes coords
    plt.gca().text(
        0.4,
        0.55,
        textstr,
        transform=plt.gca().transAxes,
        fontsize=10,
        verticalalignment="center",
        bbox=props,
    )

    return plt.gcf()


app = App(app_ui, server)
