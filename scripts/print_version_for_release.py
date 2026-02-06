from __future__ import print_function

import ast
import re
import sys

from packaging.version import Version

source_dir = sys.argv[1]

_version_re = re.compile(r"__version__\s+=\s+(.*)")

with open(f"{source_dir}/__init__.py") as f:
    version = str(ast.literal_eval(_version_re.search(f.read()).group(1)))

version_obj = Version(version)
# Strip .devN
print(version_obj.base_version)
