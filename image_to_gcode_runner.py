#!/usr/bin/python3


def main():
    print("Parsing args")

    import argparse

    argparser = argparse.ArgumentParser()
    argparser.add_argument("-f", "--file", dest="file", default=None, help="Input file (image)", type=str, required=True)
    argparser.add_argument("-o", "--output", dest="output", default=None, help="Output file (gcode)", type=str)
    argparser.add_argument("-c", "--configuration", dest="configuration", default=None, help="Configuration file (conf)", type=str, required=True)
    argparser.add_argument("-s", "--steps", dest="steps", default="all", help="Steps (possible values: all, cmyk, gcode)", type=str)
    argparser.add_argument("-v", "--verbose", dest="verbose", default=False, action="store_true", help="Verbose")
    args = argparser.parse_args()

    if args.verbose:
        import sys

        print("Configuration:")
        for key, value in vars(args).items():
            print(f"  {key}={value}")

        from utils import trace_py_files

        sys.settrace(trace_py_files)

    print("Processing image (CMYK)")
    from image_to_gcode_adaptive import CMYK

    cmyk = CMYK(
        file=args.file,
        output=args.output,
        configuration=args.configuration,
        steps=args.steps,
    )
    cmyk.process()

    if args.verbose:
        from utils import all_traced_filenames

        print(f"All accessed python files: {all_traced_filenames}")

    print("Done image_to_gcode_runner.")


if __name__ == "__main__":
    main()

    # New examples:
    # python3 image_to_gcode_runner.py -f tro/tro.jpg -c small_machineM.conf -o c4.gcode -s cmyk
    # python3 image_to_gcode_runner.py -f tro/tro.jpg -c small_machineM.conf -o c4.gcode -s gcode

    # Old examples:
    # cmyk.diff_to_cmyk('men_washing_clothes.png', 'men_2_2.jpg')

    # 'diff_img.png'
    # python3 i2gc.py -i men_washing_3/men_washing_clothes.jpg -X 940 -Y 940 -j -v -C "#DFC7A3"  -C "#8C4AEF" -l 4
