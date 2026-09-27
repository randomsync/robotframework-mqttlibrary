"""Check built packages: one sdist and one wheel, expected files, metadata.

Usage: python .github/check_dist.py <dist directory>
"""

import re
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

dist = Path(sys.argv[1])
errors = []

wheels = sorted(dist.glob("*.whl"))
sdists = sorted(dist.glob("*.tar.gz"))
if len(wheels) != 1 or len(sdists) != 1:
    sys.exit(f"expected one wheel and one sdist, found {wheels + sdists}")
wheel, sdist = wheels[0], sdists[0]

version_py = Path("src/MQTTLibrary/version.py").read_text()
version = re.search(r"VERSION = ['\"]([^'\"]+)['\"]", version_py).group(1)

with zipfile.ZipFile(wheel) as zf:
    names = zf.namelist()
    meta_name = next(n for n in names if n.endswith(".dist-info/METADATA"))
    meta = Parser().parsestr(zf.read(meta_name).decode())

package_files = sorted(n for n in names if ".dist-info/" not in n)
expected = ["MQTTLibrary/MQTTKeywords.py", "MQTTLibrary/__init__.py", "MQTTLibrary/version.py"]
if package_files != expected:
    errors.append(f"wheel files {package_files}, expected {expected}")
if meta["Version"] != version:
    errors.append(f"wheel version {meta['Version']} != version.py {version}")
if meta["Requires-Python"] != ">=3.9":
    errors.append(f"Requires-Python is {meta['Requires-Python']!r}")

with tarfile.open(sdist) as tf:
    sdist_files = {n.split("/", 1)[1] for n in tf.getnames() if "/" in n}
for required in ("README.rst", "LICENSE.txt", "pyproject.toml", "src/MQTTLibrary/MQTTKeywords.py"):
    if required not in sdist_files:
        errors.append(f"sdist is missing {required}")
unexpected = sorted(f for f in sdist_files if f.startswith(("tests/", "mosquitto/", "design/", ".github/", "docs/")))
if unexpected:
    errors.append(f"sdist has unexpected files {unexpected}")

print(f"wheel: {wheel.name}: {', '.join(package_files)}")
print(f"sdist: {sdist.name}: {', '.join(sorted(sdist_files))}")
print(f"version {meta['Version']}, Requires-Python {meta['Requires-Python']}")
if errors:
    sys.exit("\n".join(errors))
print("ok")
