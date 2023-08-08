"""Simple web app to visualize brightness over time."""

import matplotlib.pyplot as plt
import numpy as np
from shiny import App, render, ui
from pathlib import Path
from contextlib import suppress
import datetime as dt
from astral import LocationInfo
from astral.location import Location


def date_range():
    start_of_day = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = (
        start_of_day + dt.timedelta(days=1) - dt.timedelta(seconds=1)
    )  # one second before the next day
    hours_range = [start_of_day]
    while hours_range[-1] < end_of_day:
        hours_range.append(hours_range[-1] + dt.timedelta(minutes=5))
    return hours_range


def copy_color_and_brightness_module():
    with suppress(Exception):
        webapp_folder = Path(__file__).parent.absolute()
        module = (
            webapp_folder.parent
            / "custom_components"
            / "adaptive_lighting"
            / "color_and_brightness.py"
        )
        new_module = webapp_folder / module.name
        with module.open() as f:
            lines = [
                line.replace("homeassistant.util.color", "homeassistant_util_color")
                for line in f.readlines()
            ]
        with new_module.open("r") as f:
            existing_lines = f.readlines()
        if existing_lines != lines:
            with new_module.open("w") as f:
                f.writelines(lines)


copy_color_and_brightness_module()

from color_and_brightness import SunLightSettings


def plot_brightness(kw, sleep_mode: bool):
    # Define the time range for our simulation
    sun_linear = SunLightSettings(**kw, brightness_mode="linear")
    sun_tanh = SunLightSettings(**kw, brightness_mode="tanh")
    sun = SunLightSettings(**kw, brightness_mode="default")
    # Calculate the brightness for each time in the time range for both modes
    dt_range = date_range()
    assert 0, dt_range
    time_range = [time_to_float(dt) for dt in dt_range]
    brightness_linear_values = [
        sun_linear.brightness_pct(dt, sleep_mode) for dt in dt_range
    ]
    brightness_tanh_values = [
        sun_tanh.brightness_pct(dt, sleep_mode) for dt in dt_range
    ]
    brightness_default_values = [sun.brightness_pct(dt, sleep_mode) for dt in dt_range]

    # Plot the brightness over time for both modes
    plt.figure(figsize=(10, 6))
    plt.plot(time_range, brightness_linear_values, label="Linear Mode")
    plt.plot(time_range, brightness_tanh_values, label="Tanh Mode")
    plt.plot(time_range, brightness_default_values, label="Default Mode")
    plt.vlines(
        time_to_float(sun.sunrise_time),
        0,
        100,
        color="C2",
        label="Sunrise",
        linestyles="dashed",
    )
    plt.vlines(
        time_to_float(sun.sunset_time),
        0,
        100,
        color="C3",
        label="Sunset",
        linestyles="dashed",
    )
    plt.xlim(0, 24)
    plt.xticks(np.arange(0, 25, 1))
    yticks = np.arange(0, 105, 5)
    ytick_labels = [f"{label:.0f}%" for label in yticks]
    plt.yticks(yticks, ytick_labels)
    plt.xlabel("Time (hours)")
    plt.ylabel("Brightness")
    plt.title("Brightness over Time for Different Modes")

    # Add text box
    textstr = "\n".join(
        (
            f"Sunrise Time = {sun.sunrise_time}",
            f"Sunset Time = {sun.sunset_time}",
            f"Max Brightness = {sun.max_brightness:.0f}%",
            f"Min Brightness = {sun.min_brightness:.0f}%",
            f"Time Light = {sun.brightness_mode_time_light} hours",
            f"Time Dark = {sun.brightness_mode_time_dark} hours",
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


SEC_PER_HR = 60 * 60
desc = """
**Experience the Dynamics of [Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting) in Real-Time.**

Have you ever wondered how the intricate settings of [Adaptive Lighting](https://github.com/basnijholt/adaptive-lighting) impact your home ambiance? The Adaptive Lighting Simulator WebApp is here to demystify just that.

Harnessing the technology of the popular Adaptive Lighting integration for Home Assistant, this webapp provides a hands-on, visual platform to explore, tweak, and understand the myriad of parameters that dictate the behavior of your smart lights. Whether you're aiming for a subtle morning glow or a cozy evening warmth, observe firsthand how each tweak changes the ambiance.

**Why Use the Simulator?**
- **Interactive Exploration**: No more guesswork. See in real-time how changes to settings influence the lighting dynamics.
- **Circadian Cycle Preview**: Understand how Adaptive Lighting adjusts throughout the day based on specific parameters, ensuring your lighting aligns with your circadian rhythms.
- **Tailored Testing**: Play with parameters and find the perfect combination that suits your personal or family's needs.
- **Educational Experience**: For both newbies and experts, delve deep into the intricacies of Adaptive Lighting's logic and potential.

Dive into the simulator, experiment with different settings, and fine-tune the behavior of Adaptive Lighting to perfection. Whether you're setting it up for the first time or optimizing an existing setup, this tool ensures you get the most out of your smart lighting experience.
"""

# Shiny UI
app_ui = ui.page_fluid(
    ui.panel_title("🌞 Adaptive Lighting Simulator WebApp 🌛"),
    ui.layout_sidebar(
        ui.panel_sidebar(
            ui.input_switch("adapt_until_sleep", "adapt_until_sleep", False),
            ui.input_switch("sleep_mode", "sleep_mode", False),
            ui.input_slider("min_brightness", "min_brightness", 1, 100, 30, post="%"),
            ui.input_slider("max_brightness", "max_brightness", 1, 100, 100, post="%"),
            ui.input_numeric("min_color_temp", "min_color_temp", 2000),
            ui.input_numeric("max_color_temp", "max_color_temp", 6666),
            ui.input_slider(
                "sleep_brightness", "sleep_brightness", 1, 100, 1, post="%"
            ),
            ui.input_radio_buttons(
                "sleep_rgb_or_color_temp",
                "sleep_rgb_or_color_temp",
                ["rgb_color", "color_temp"],
            ),
            ui.input_numeric("sleep_color_temp", "sleep_color_temp", 2000),
            ui.input_text("sleep_rgb_color", "sleep_rgb_color", "255,0,0"),
            ui.input_slider(
                "brightness_mode_time_dark",
                "brightness_mode_time_dark",
                1,
                5 * SEC_PER_HR,
                3 * SEC_PER_HR,
                post=" sec",
            ),
            ui.input_slider(
                "brightness_mode_time_light",
                "brightness_mode_time_light",
                1,
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
        ui.panel_main(ui.markdown(desc), ui.output_plot(id="brightness_plot")),
    ),
)


def float_to_time(value: float) -> dt.time:
    hours = int(value)
    minutes = int((value - hours) * 60)
    time = dt.time(hours, minutes)
    return time


def time_to_float(time: dt.time) -> float:
    return time.hour + time.minute / 60


def server(input, output, session):
    @output
    @render.plot
    def brightness_plot():
        kw = dict(
            name="Adaptive Lighting Simulator",
            adapt_until_sleep=input.adapt_until_sleep(),
            max_brightness=input.max_brightness(),
            min_brightness=input.min_brightness(),
            min_color_temp=input.min_color_temp(),
            max_color_temp=input.max_color_temp(),
            sleep_brightness=input.sleep_brightness(),
            sleep_rgb_or_color_temp=input.sleep_rgb_or_color_temp(),
            sleep_color_temp=input.sleep_color_temp(),
            sleep_rgb_color=input.sleep_rgb_color(),
            sunrise_time=float_to_time(input.sunrise_time()),
            sunset_time=float_to_time(input.sunset_time()),
            # sunrise_time=None,
            # sunset_time=None,
            brightness_mode_time_dark=dt.timedelta(
                seconds=input.brightness_mode_time_dark()
            ),
            brightness_mode_time_light=dt.timedelta(
                seconds=input.brightness_mode_time_light()
            ),
            sunrise_offset=dt.timedelta(0),
            sunset_offset=dt.timedelta(0),
            min_sunrise_time=None,
            max_sunrise_time=None,
            min_sunset_time=None,
            max_sunset_time=None,
            astral_location=Location(LocationInfo()),
        )
        return plot_brightness(kw, sleep_mode=input.sleep_mode())


app = App(app_ui, server)
