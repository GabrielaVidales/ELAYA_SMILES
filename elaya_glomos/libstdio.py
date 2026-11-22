import os.path
#------------------------------------------------------------------------------------------
def _clean_lines(filepath):
    with open(filepath, 'r') as f:
        for line in f:
            line = line.split('#')[0].strip()
            if line:
                yield line.split()
#------------------------------------------------------------------------------------------
def get_value_from_file(filepath, key, dtype=str, default=None):
    """Read one ``key value`` pair from a parameter file (comments start with #).

in:
    filepath (str): path to the input file.
    key (str): parameter name (case-insensitive).
    dtype (type): int, float or str.
    default: returned when the key is missing, the file does not exist or the
        value cannot be converted.
"""
    if not os.path.isfile(filepath):
        return default
    for parts in _clean_lines(filepath):
        if len(parts) >= 2 and parts[0].lower() == key.lower():
            try:
                return dtype(parts[1])
            except ValueError:
                print("Warning: could not convert '%s' to %s for key '%s'. Using default %r."
                      % (parts[1], dtype.__name__, key, default))
                return default
    return default
#------------------------------------------------------------------------------------------
class read_main_input:
    """Typed reader for GLOMOS INPUT files."""

    def __init__(self, filename):
        self.filename = filename

    def get_int(self, key, default):
        return get_value_from_file(self.filename, key, int, default)

    def get_float(self, key, default):
        return get_value_from_file(self.filename, key, float, default)

    def get_str(self, key, default):
        return get_value_from_file(self.filename, key, str, default)

    def get_bool(self, key, default):
        v = get_value_from_file(self.filename, key, str, None)
        if v is None:
            return default
        return v.strip().lower() in ('1', 'true', 'yes', 'on', 'y')

    def get_floatlist(self, key, default):
        """Space separated floats after ``key``."""
        if not os.path.isfile(self.filename):
            return default
        for parts in _clean_lines(self.filename):
            if len(parts) >= 2 and parts[0].lower() == key.lower():
                try:
                    return [float(v) for v in parts[1:]]
                except ValueError:
                    print("Warning: could not convert %r to a list of floats. Using default." % (parts[1:],))
                    return default
        return default
#------------------------------------------------------------------------------------------
