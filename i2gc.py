#!/usr/bin/python3
from os.path import isfile, splitext
from concurrent.futures import ThreadPoolExecutor as PoolExecutor
from functools import partial
from datetime import datetime
import math

from PIL import Image, ImageCms, ImageColor
from pygcode import *
import numpy as np

from utils import color_profile_dir


class I2GC:
    def __init__(
        self,
        img_file: str,
        levels: int = 1,
        profile: str = f"{color_profile_dir}/SC_paper_eci.icc",
        columns: int | None = None,
        rows: int | None = None,
        width: float | None = None,
        height: float | None = None,
        z_step: float | None = None,
        temperature: int | None = None,
        extruder_speed: float | None = None,
        retract: float | None = None,
        verbose: bool = False,
        fast: bool = False,
        join: bool = False,
        grayscale: bool = False,
        custom_colors: list[str] | None = None,
    ):
        self._img_file = img_file
        if not self._img_file or not isfile(self._img_file):
            print(f'Error: File "{self._img_file}" does not exist')
            exit(1)

        self._columns = columns
        self._rows = rows
        self._width = width
        self._height = height
        self._x_step = None
        self._y_step = None
        self._z_step = z_step
        self._levels = levels
        self._profile = profile
        self._grayscale = grayscale
        self._fast = fast
        self.GCodeMove = GCodeRapidMove if self._fast else GCodeLinearMove
        self._join = join
        self._temperature = temperature
        self._e_speed = extruder_speed
        self._retract = retract
        self._custom_colors = custom_colors

        self._verbose = verbose

        self._jgcfh = {}
        self._gcodes = {}

        self._cmyk = [
            (0, 255, 255),  # Cyan
            (255, 0, 255),  # Magenta
            (255, 255, 0),  # Yellow
            (0, 0, 0),  # Kroma / Key
        ]
        self._cmykstr = ["C", "M", "Y", "K"]
        self._custom_channels = []

    def process_level(self, channel, j):
        c = self._cmykstr[channel] if not self._grayscale else "K"
        if self._verbose:
            _level_time = datetime.now()
            print(f"Processing channel {c}, level {j}")
        _gcfh = open(f"{splitext(self._img_file)[0]}_{c}_{j}.gcode", "w+")
        output = Image.new("RGB", (self._columns, self._rows), (255, 255, 255))
        xp, yp, pen_down = 0, self._rows - 1, 0
        row = 0
        threshold = j * 255 / self._levels
        gcodes = [GCodeFeedRate(2000), GCodeRapidMove(Z=max(self._z_step, 0))]
        if self._temperature:
            gcodes.append(f"M109 S{self._temperature}")
        if self._e_speed:
            gcodes.append("M83")
        dy = 0
        if j > 0:
            dy = self._y_step / self._levels
            l = self._levels - j
            k = l // 2 + l % 2
            s = 1 - 2 * ((l + channel) % 2)
            dy = dy * s * k
            gcodes.append(self.GCodeMove(Y=dy))
        e = 0
        xt = 0
        ret = False
        _work_channel = self.channels[channel] if channel < len(self.channels) else self._custom_channels[channel - len(self.channels)]
        for y in range(self._rows - 1, -1, -1):
            start, stop, step = (self._columns - 1, -1, -1) if row % 2 else (0, self._columns, 1)
            for x in range(start, stop, step):
                if _work_channel.getpixel((x, y)) > threshold:
                    e += 1
                    output.putpixel((x, y), self._cmyk[channel] if not self._grayscale else self._cmyk[3])
                    if not pen_down:
                        # Start drawing
                        if y != yp:
                            gcodes.append(
                                self.GCodeMove(
                                    X=(x + (1 if step < 0 else 0)) * self._x_step,
                                    Y=(self._rows - 1 - y) * self._y_step + dy,
                                )
                            )
                        else:
                            gcodes.append(self.GCodeMove(X=(x + (1 if step < 0 else 0)) * self._x_step))
                        gcodes.append(GCodeRapidMove(Z=min(self._z_step, 0)))
                        if self._retract and ret:
                            gcodes[-1] = f"{str(gcodes[-1])} E{self._retract}"
                        xp, yp, pen_down = (x, y, 1)
                elif pen_down:
                    # Stop drawing
                    gcodes.append(self.GCodeMove(X=(x + (1 if step > 0 else 0)) * self._x_step))
                    if self._e_speed:
                        gcodes[-1] = f"{str(gcodes[-1])} E{(e * self._x_step * self._e_speed)}"
                    gcodes.append(GCodeRapidMove(Z=max(self._z_step, 0)))
                    if self._retract:
                        gcodes[-1] = f"{str(gcodes[-1])} E{-self._retract}"
                        ret = True
                    xp, yp, pen_down, e, xt = (x, y, 0, 0, xt + e)
                if x == stop - step and pen_down:
                    # Stop drawing
                    gcodes.append(self.GCodeMove(X=(x + (1 if step > 0 else 0)) * self._x_step))
                    if self._e_speed:
                        gcodes[-1] = f"{str(gcodes[-1])} E{(e * self._x_step * self._e_speed)}"
                    gcodes.append(GCodeRapidMove(Z=max(self._z_step, 0)))
                    if self._retract:
                        gcodes[-1] = f"{str(gcodes[-1])} E{-self._retract}"
                        ret = True
                    xp, yp, pen_down, e, xt = (x, y, 0, 0, xt + e)
            row += 1
        gcodes.append(GCodeRapidMove(X=0, Y=0))
        out_gcode = "\n".join(str(g) for g in gcodes)
        _gcfh.write(out_gcode)
        _gcfh.close()
        output.save(f"{splitext(self._img_file)[0]}_{c}_{j}.png")
        if self._verbose:
            _level_time = datetime.now() - _level_time
            print(f"Channel {c}, level {j}: {_level_time.total_seconds()}s, {xt * self._x_step:.1f}mm")
        if self._join:
            self._gcodes[channel].update({j: out_gcode})

    def process_custom_color(self, _cmyk):
        _new_channel = []
        for y in range(0, self._rows, 1):
            for x in range(0, self._columns, 1):
                _alpha = min(self.channels[n].getpixel((x, y)) / _cmyk[n] if _cmyk[n] else 1 for n in range(4))
                _new_channel.append(math.floor(256 * _alpha))
                for n in range(4):
                    self.channels[n].putpixel((x, y), self.channels[n].getpixel((x, y)) - math.floor(_cmyk[n] * _alpha))
        _ra = np.reshape(_new_channel, (self._rows, self._columns))
        _new_channel = Image.fromarray(np.uint8(_ra), "L")
        self._custom_channels.append(_new_channel)

    def process(self):
        if self._verbose:
            _start_time = datetime.now()
        image = Image.open(self._img_file)
        if self._columns or self._rows:
            height, width = image.size
            interpolation = Image.BOX
            if self._columns > width or self._rows > height:
                interpolation = Image.LANCZOS
            if not self._rows:
                self._rows = int(height * (self._columns / width))
            elif not self._columns:
                self._columns = int(width * (self._rows / height))
            image = image.resize((self._columns, self._rows), resample=interpolation)
        self._columns, self._rows = image.size
        self._x_step, self._y_step = (self._width / self._columns, self._height / self._rows)
        if self._grayscale:
            image = image.convert("L")
        elif "RGB" in image.mode:
            image = ImageCms.profileToProfile(image, f"{color_profile_dir}/sRGB_v4_ICC_preference.icc", self._profile, outputMode="CMYK")
        self.channels = image.split()
        if self._custom_colors:
            if self._grayscale:
                print("Error: Custom colors are incompatible with grayscale! Exiting.")
                exit()
            _cmyks = {}
            for _color in self._custom_colors:
                if self._verbose:
                    print(f"Converting custom color: {_color}")
                _rgb = ImageColor.getrgb(_color)
                if _rgb in [(0, 0, 0), (255, 255, 0), (255, 0, 255), (0, 255, 255)]:
                    print("Custom color: {} is a CMYK color. Skipping.")
                    continue
                if self._verbose:
                    print(f"RGB: {_rgb}")
                _ti = Image.new("RGB", (1, 1), _rgb)
                _ti = ImageCms.profileToProfile(
                    _ti,
                    f"{color_profile_dir}/sRGB_v4_ICC_preference.icc",
                    self._profile,
                    outputMode="CMYK",
                )
                self._cmyk.append(_rgb)
                self._cmykstr.append(_color)
                _cmyk = _ti.getpixel((0, 0))
                _i = 0
                for _v in _cmyk:
                    _i += _v
                _cmyks[_i] = [_cmyk, _color]
                if self._verbose:
                    print(f"CMYK: {_cmyk}")
            for _a in sorted(_cmyks.items()):
                if self._verbose:
                    print(f"Processing custom color: {_a[1][1]}")
                self.process_custom_color(_a[1][0])
        if self._custom_colors and self._verbose:
            print("Custom colors done")
        if self._verbose:
            _setup_time = datetime.now() - _start_time
            print(f"Setup: {_setup_time.total_seconds()}s")
        _results_gen = []
        _r = len(self.channels) + len(self._custom_channels)
        with PoolExecutor() as executor:
            for channel in range(_r):
                self._gcodes.update({channel: {}})
                c = self._cmykstr[channel] if not self._grayscale else "K"
                if self._join:
                    self._jgcfh.update({channel: open(f"{splitext(self._img_file)[0]}_{c}_combined_0-{self._levels - 1}.gcode", "w+")})
                _results_gen.append(executor.map(partial(self.process_level, channel), range(self._levels)))
        if self._join and _results_gen:
            for channel in range(_r):
                for j in range(self._levels):
                    self._jgcfh[channel].write(self._gcodes[channel][j])
                self._jgcfh[channel].close()
        if self._verbose:
            _run_time = datetime.now() - _start_time
            print(f"Run time: {_run_time.total_seconds()}s")


def main():
    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument("-i", "--image", dest="img_file", default=None, help="Input image", type=str, required=True)
    argparser.add_argument("-l", "--levels", dest="levels", default=1, help="Levels per channel", type=int)
    argparser.add_argument("-c", "--color_profile", dest="profile", default=f"{color_profile_dir}/SC_paper_eci.icc", help="CMYK color profile", type=str)
    argparser.add_argument("-x", "--columns", dest="columns", default=None, help="Output columns", type=int)
    argparser.add_argument("-y", "--rows", dest="rows", default=None, help="Output rows", type=int)
    argparser.add_argument("-X", "--width", dest="width", default=None, help="Output width in mm", type=float, required=True)
    argparser.add_argument("-Y", "--height", dest="height", default=None, help="Output height in mm", type=float, required=True)
    argparser.add_argument("-Z", "--z_step", dest="z_step", default=-7, help="Z step (pen down) in mm", type=float)
    argparser.add_argument("-S", "--temp", dest="temp", default=None, help="Extruder temperature in C", type=int)
    argparser.add_argument("-E", "--extruder_s", dest="e_speed", default=None, help="Extruder speed in mm/mm", type=float)
    argparser.add_argument("-R", "--retract", dest="retract", default=None, help="Retraction amount in mm", type=float)
    argparser.add_argument("-v", "--verbose", dest="verbose", action="store_true", help="Verbose")
    argparser.add_argument("-f", "--fast", dest="fast", action="store_true", help="Use fast move, less accurate")
    argparser.add_argument("-j", "--join", dest="join", action="store_true", help="Also output joined gcodes for all levels in a channel")
    argparser.add_argument("-g", "--grayscale", dest="grayscale", action="store_true", help="Grayscale output (experimental)")
    argparser.add_argument("-C", "--custom_color", dest="custom_color", action="extend", nargs="+", default=None, help="Specify additional custom color channels", type=str)

    args = argparser.parse_args()

    if args.verbose:
        print("Configuration:")
        for key, value in vars(args).items():
            print(f"  {key}={value}")

        from utils import trace_py_files
        import sys

        sys.settrace(trace_py_files)

    i2gc = I2GC(
        img_file=args.img_file,
        levels=args.levels,
        profile=args.profile,
        columns=args.columns,
        rows=args.rows,
        width=args.width,
        height=args.height,
        z_step=args.z_step,
        verbose=args.verbose,
        fast=args.fast,
        join=args.join,
        grayscale=args.grayscale,
        temperature=args.temp,
        extruder_speed=args.e_speed,
        retract=args.retract,
        custom_colors=args.custom_color,
    )
    i2gc.process()

    if args.verbose:
        from utils import all_traced_filenames

        print(f"All accessed python files: {all_traced_filenames}")

    print("Done i2gc.")


if __name__ == "__main__":
    main()
