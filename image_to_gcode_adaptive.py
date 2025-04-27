#!/usr/bin/python3
import os
import shutil
import threading
import json
import subprocess
import traceback
from typing import Literal
from xml.etree import ElementTree

from PIL import Image
from openscad_runner import OpenScadRunner
from wand.image import Image as WImage

from copicograf import Copicograf
from utils import color_profile_dir, cmyk_to_name


class CMYK:
    def __init__(
        self,
        file: str,
        output: str,
        configuration: str,
        steps: Literal["all", "cmyk", "gcode"] | str,
    ):
        self.file = file
        self.output = output
        self.configuration = configuration
        self.steps = steps

        # Load configuration in JSON as a dictionary
        with open(self.configuration) as f:
            self.conf = json.load(f)

        print("Cyan tray x:", self.conf["trays"]["cyan"]["x"])
        print("First additional:", self.conf["additionals"][0])

        self.colors = []
        for color in self.conf["color_order"]:
            if self.conf["separation"]["selection"]:
                self.colors.append(color)
            elif color in self.conf["separation"]["selection"]["additionals"]:
                if color in self.conf["trays"]["additionals"]:
                    self.colors.append(color)
                else:
                    print(f"Warning: color in color_order not in trays.additionals, skipping: {color}")
            else:
                print(f"Warning: color in color_order not in separation.selection.additionals, skipping: {color}")

        self.rgb_profile = ""
        self.cmyk_profile = f"{color_profile_dir}/SC_paper_eci.icc"

        self.OPENSCAD = "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
        # self.Slic3r = "/Applications/Ultimaker-Cura.app/Contents/MacOS/CuraEngine"
        # self.Slic3r = "cura-slicer.cura-engine"
        self.Slic3r = "cura-slicer"
        self.fallback_Slic3r = "prusa-slicer"

        self.image_width = int(self.conf["brushograph"]["width"])
        self.image_height = int(self.conf["brushograph"]["height"])

        self.diff_img_file = "diff_img.png"
        self.result_approx_forecast = "approx_forecast.png"

    def _set_dimensions(self, im_path, svg_dpi=96):
        if im_path.endswith(".svg"):
            tree = ElementTree.parse(im_path)
            root = tree.getroot()

            # Namespace handling for SVG
            ns = {"svg": "http://www.w3.org/2000/svg"}
            ElementTree.register_namespace("", ns["svg"])

            # Extract width and height attributes
            width = root.attrib.get("width")
            height = root.attrib.get("height")

            if width and height:
                # Remove units (e.g., 'px', 'mm', 'cm') if present
                def parse_length(value):
                    if value.endswith("px"):
                        return float(value[:-2])
                    elif value.endswith("mm"):
                        return float(value[:-2]) * (svg_dpi / 25.4)  # 1 inch = 25.4 mm
                    elif value.endswith("cm"):
                        return float(value[:-2]) * (svg_dpi / 2.54)  # 1 cm = 10 mm
                    else:  # Assume pixels if no unit
                        return float(value)

                self.im_width_px = round(parse_length(width))
                self.im_height_px = round(parse_length(height))
                self.im_dpi = svg_dpi
            else:
                raise ValueError("SVG file does not specify width and height.")
        else:
            im = Image.open(im_path)
            self.im_dpi = im.info["dpi"][0]
            self.im_width_px = im.width
            self.im_height_px = im.height

        print("DPI: ", self.im_dpi)
        print("Width (px): ", self.im_width_px)
        print("Height (px): ", self.im_height_px)

    def process(self):  # image_to_gcode
        if self.steps == "all":
            if self.file.endswith(".svg"):
                self._collect_svgs()
            else:
                self._cmyk_separation_script(self.file)
                self._convert_jpgs_to_svgs()
            self._convert_svgs_to_stls()
            self._create_slicer_gcodes()
            self._create_copicograf_gcode(self.output)
        elif self.steps == "cmyk":
            if self.file.endswith(".svg"):
                raise ValueError("Cannot process a svg file with cmyk steps")
            else:
                self._cmyk_separation_script(self.file)
        elif self.steps == "gcode":
            if self.file.endswith(".svg"):
                self._collect_svgs()
            else:
                self._convert_jpgs_to_svgs()
            self._convert_svgs_to_stls()
            self._create_slicer_gcodes()
            self._create_copicograf_gcode(self.output)
        else:
            raise ValueError(f"Unknown steps value: {self.steps}")

    def _cmyk_separation_script(self, im_path):
        # TODO: replace by a call or multiprocessing
        print("Running i2gc.py")
        cmd = ["python3", "i2gc.py", "-i", im_path, "-X", str(self.image_width), "-Y", str(self.image_width), "--join", "--verbose"]

        # TODO: pass self.colors instead?
        for color in self.conf["additionals"]:
            cmd.extend(["--custom_color", color])

        cmd.extend(["--levels", str(self.conf["separation"]["levels"])])

        print(cmd)
        subprocess.run(cmd)
        # TODO: check return code (or do TODO above)

    def _resize_image(self, im_path):
        with WImage(filename=im_path) as img:
            img.resize(self.image_width, self.image_width)
            img.save(filename=im_path)

    def _create_copicograf_gcode(self, result_gcode_path):
        copicograf = Copicograf(conf=self.conf)

        for color in self.colors:
            print("copicograf gcode", color)
            color_name = cmyk_to_name.get(color, color)
            if color_name in self.conf["trays"]:
                color_tray_x = int(self.conf["trays"][color_name]["x"])
                color_tray_y = int(self.conf["trays"][color_name]["y"])
            elif color_name in self.conf["trays"]["additionals"]:
                color_tray_x = int(self.conf["trays"]["additionals"][color_name]["x"])
                color_tray_y = int(self.conf["trays"]["additionals"][color_name]["y"])
            else:
                print(f"Warning: unhandled color in copicograf: {color}")
                continue

            copicograf.prepare_path(f"threshold_{color_name}_slicer.gcode", color_tray_x, color_tray_y)

        copicograf.save_gcode(result_gcode_path)

    def _create_slicer_gcode(self, orig_file, result_file, diameter, draw_walls):
        cmd = [
            self.Slic3r,
            "-v",
            "-o",
            result_file,
            "--layer_height=1",
            "--wall_thickness=1",
            "--top_bottom_thickness=0",
            "--infill_line_distance=4",
            "--infill_angles=[0]",
            "--retraction_hop=5",
            "--material_print_temperature=0",
            "--retraction_hop_enabled=true",
            "--brim_line_count=0",
            "--retraction_combing=off",
            "--wall_line_count=1",
            "--material_diameter=1",
            "--initial_bottom_layers=0",
            "--layer_height=1",
            "--layer_height_0=1",
            f"--infill_pattern={self.conf['slicer']['infill_pattern']}",  # lines
            "--cool_min_temperature=0",
            "--nozzle_diameter=1",
            "--machine_center_is_zero=true",
            "--machine_nozzle_diameter=1",
            # "--wall_line_count=1",
            f"--infill_line_distance={self.conf['slicer']['infill_line_distance']}",
            "--infill_sparse_density=0",  # 100
            # "--infill_line_width=1",
            "--initial_bottom_layers=0",
            "--retraction_combing=off",
            orig_file,
        ]
        print(cmd)
        try:
            subprocess.run(cmd)
        except FileNotFoundError:
            traceback.print_exc()
            print("Warning: slicer not found, attempting fallback slicer")
            cmd = [
                self.fallback_Slic3r,
                "--gcode",
                "--output",
                result_file,
                orig_file,
            ]
            print(cmd)
            subprocess.run(cmd)

    def _create_slicer_gcodes(self):
        diam = "2.0"
        draw_walls = False

        threads = []
        for color in self.colors:
            color_name = cmyk_to_name.get(color, color)
            threads.append(
                threading.Thread(
                    target=self._create_slicer_gcode,
                    args=(
                        f"threshold_{color_name}.stl",
                        f"threshold_{color_name}_slicer.gcode",
                        diam,
                        draw_walls,
                    ),
                )
            )

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    def _create_scad_file(self, scad_file, svg_file):
        with open(scad_file, "w") as f:
            f.write("module converter() {\n")
            f.write("difference(){\n")
            f.write("linear_extrude(1) {\n")
            f.write("inch_in_cm = 2.54;\n")
            f.write("inch_in_mm = inch_in_cm * 10;\n")
            f.write(f"desired_width_mm = {self.image_width};\n")
            f.write(f"desired_height_mm = {self.image_height};\n")
            f.write(f"width_px = {self.im_width_px};\n")
            f.write(f"height_px = {self.im_height_px};\n")
            f.write(f"dpi = {self.im_dpi};\n")
            f.write("width_mm = (width_px * inch_in_mm)/dpi;\n")
            f.write("height_mm = (height_px * inch_in_mm)/dpi;\n")
            f.write("scale_factor_x = desired_width_mm / width_mm;\n")
            f.write("scale_factor_y= desired_height_mm / height_mm;\n")
            f.write("scale([scale_factor_y,scale_factor_x])\n")
            f.write(f'import("{svg_file}");\n')
            f.write("}\n")
            f.write("}\n")
            f.write("}\n")
            f.write("converter();\n")

    def _convert_svg_to_stl(self, scad_file, orig_file, result_file):
        self._create_scad_file(scad_file=scad_file, svg_file=orig_file)
        osr = OpenScadRunner(scriptfile=scad_file, outfile=result_file)
        osr.run()
        for line in osr.echos:
            print(line)
        for line in osr.warnings:
            print(line)
        for line in osr.errors:
            print(line)
        if osr.good():
            print("Successfully created", result_file)

    def _convert_svgs_to_stls(self):
        dimensions_set = False
        if os.path.exists(self.file):
            self._set_dimensions(self.file)
            dimensions_set = True

        for color in self.colors:
            color_name = cmyk_to_name.get(color, color)

            if self.file.endswith(".svg") and not os.path.exists(self.file):
                self._set_dimensions(f"threshold_{color_name}.svg")
                dimensions_set = True

            if not dimensions_set:
                print("Warning: image dimensions are not set, scad generation may fail")

            self._convert_svg_to_stl(
                f"threshold_{color_name}.scad",
                f"threshold_{color_name}.svg",
                f"threshold_{color_name}.stl",
            )

    def _collect_svgs(self):
        base_file = os.path.splitext(self.file)[0]
        for color in self.colors:
            print("collecting svgs for color ", color)
            if color in self.conf["separation"]["selection"]:
                color_level = self.conf["separation"]["selection"][color]
            elif color in self.conf["separation"]["selection"]["additionals"]:
                color_level = self.conf["separation"]["selection"]["additionals"][color]
            else:
                print(f"Warning: unhandled color: {color}")
                continue

            color_name = cmyk_to_name.get(color, color)
            shutil.copyfile(f"{base_file}_{color}_{color_level}.svg", f"threshold_{color_name}.svg")

    def _convert_jpg_to_svg(self, orig_file, pbm_file, result_file):
        subprocess.run(["convert", orig_file, pbm_file])
        subprocess.run(["potrace", pbm_file, "-s", "-o", result_file])  # "-t", "100", "-O", "0.7"

    def _convert_jpgs_to_svgs(self):
        base_file = os.path.splitext(self.file)[0]
        for color in self.colors:
            if color in self.conf["separation"]["selection"]:
                color_level = self.conf["separation"]["selection"][color]
            elif color in self.conf["separation"]["selection"]["additionals"]:
                color_level = self.conf["separation"]["selection"]["additionals"][color]
            else:
                print(f"Warning: unhandled color: {color}")
                continue

            color_name = cmyk_to_name.get(color, color)
            self._convert_jpg_to_svg(
                f"{base_file}_{color}_{color_level}.png",
                f"threshold_{color_name}.pbm",
                f"threshold_{color_name}.svg",
            )
