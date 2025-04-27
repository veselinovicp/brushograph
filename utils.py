# Color utils
color_profile_dir = "color_profiles"

cmyk_to_name = {
    "C": "cyan",
    "M": "magenta",
    "Y": "yellow",
    "K": "kroma",
}

# Debug utils
last_traced_filename = None
all_traced_filenames = set()


def trace_py_files(frame, event, arg):
    """Trace python files that are accessed. Usage: sys.settrace(trace_py_files)"""
    if event == "call":
        filename = frame.f_globals.get("__file__")
        if filename and filename.endswith(".py"):
            import os

            filename = os.path.abspath(filename)
            cwd = os.getcwd()

            if filename.startswith(cwd):
                filename = filename.removeprefix(cwd).removeprefix("/")
                if "env" not in filename and "venv" not in filename:
                    all_traced_filenames.add(filename)
                    global last_traced_filename
                    if filename != last_traced_filename:
                        print(f"Accessing python file: {filename}")
                    last_traced_filename = filename
    return trace_py_files
