import os.path
#------------------------------------------------------------------------------------------
def get_value_from_file(filepath, key, dtype=str, default=None):
    """Read a single key-value pair from a parameter file, ignoring comments.

in:
    filepath (str): path to the input file.
    key (str): parameter name to search for (case-insensitive).
    dtype (type): Python type to cast the value to (int, float, or str).
    default: value to return if the key is not found or the file does not exist.
out:
    parsed value of type dtype, or default if the key is missing or conversion fails.
"""
    if not os.path.isfile(filepath):
        return default
    with open(filepath, 'r') as f:
        for line in f:
            line = line.split('#')[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0].lower() == key.lower():
                value_str = parts[1]
                try:
                    return dtype(value_str)
                except ValueError:
                    print(f"Warning: Could not convert '{value_str}' to {dtype.__name__}. Returning default.")
                    return default
    return default
#------------------------------------------------------------------------------------------
class read_main_input:
    """Convenience class for reading typed parameters from an AEGOn input file."""

    def __init__(self, filename):
        """Initialize the input reader bound to a specific file.

in:
    filename (str): path to the AEGOn input file.
out:
    read_main_input instance.
"""
        self.filename = filename

    def get_int(self, key, default):
        """Read an integer parameter from the input file.

in:
    key (str): parameter name.
    default (int): fallback value if key is not found.
out:
    int: parsed value or default.
"""
        return get_value_from_file(self.filename, key, int, default)

    def get_float(self, key, default):
        """Read a float parameter from the input file.

in:
    key (str): parameter name.
    default (float): fallback value if key is not found.
out:
    float: parsed value or default.
"""
        return get_value_from_file(self.filename, key, float, default)

    def get_str(self, key, default):
        """Read a string parameter from the input file.

in:
    key (str): parameter name.
    default (str): fallback value if key is not found.
out:
    str: parsed value or default.
"""
        return get_value_from_file(self.filename, key, str, default)

    def get_floatlist(self, key, default):
        """Read a space-separated list of floats for a given key from the input file.

in:
    key (str): parameter name.
    default (list of float): fallback value if key is not found or the file
        does not exist.
out:
    list of float: parsed values (one or more numbers after the key), or
        default if the key is missing or any value fails to convert.
"""
        if not os.path.isfile(self.filename):
            return default
        with open(self.filename, 'r') as f:
            for line in f:
                line = line.split('#')[0].strip()
                if not line:
                    continue
                parts = line.split()
                if len(parts) >= 2 and parts[0].lower() == key.lower():
                    try:
                        return [float(v) for v in parts[1:]]
                    except ValueError:
                        print(f"Warning: Could not convert '{parts[1:]}' to a list of floats. Returning default.")
                        return default
        return default

#------------------------------------------------------------------------------------------
