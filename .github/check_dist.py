"""Check built packages before they are tested or published.

Usage: python .github/check_dist.py <dist directory>

Checks the wheel and sdist for the version in version.py:
- the wheel contains exactly the package files tracked by git
- the sdist contains exactly those files plus the allowed top-level files
- Version and Requires-Python in the wheel metadata match pyproject.toml

Untracked files in the working tree are rejected, so a local build that
picked up stray files fails here instead of being published.
Needs Python 3.11+ (tomllib) and the `packaging` library.
"""

import re
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from email.parser import Parser
from pathlib import Path

from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = "src/MQTTLibrary"
SDIST_EXTRA_FILES = {"PKG-INFO", "pyproject.toml", "README.rst", "LICENSE.txt", "CHANGELOG.md", ".gitignore"}


def fail(message):
    sys.exit(f"check_dist: {message}")


pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
project = pyproject["project"]
version_cfg = pyproject["tool"]["hatch"]["version"]
match = re.search(version_cfg["pattern"], (ROOT / version_cfg["path"]).read_text(), re.MULTILINE)
if not match:
    fail(f"version pattern not found in {version_cfg['path']}")
version = str(Version(match.group("version")))
requires_python = project["requires-python"]

tracked = subprocess.run(
    ["git", "ls-files", "--", PACKAGE_DIR], cwd=ROOT, check=True, capture_output=True, text=True
).stdout.split()
if not tracked:
    fail(f"git lists no files under {PACKAGE_DIR}")
expected_wheel = sorted(f.removeprefix("src/") for f in tracked)
expected_sdist = sorted(set(tracked) | SDIST_EXTRA_FILES)

dist = Path(sys.argv[1])
stem = f"{canonicalize_name(project['name']).replace('-', '_')}-{version}"
wheels = sorted(dist.glob(f"{stem}-*.whl"))
sdists = sorted(dist.glob(f"{stem}.tar.gz"))
if len(wheels) != 1 or len(sdists) != 1:
    fail(f"expected one wheel and one sdist for {version} in {dist}, found {[p.name for p in wheels + sdists]}")
wheel, sdist = wheels[0], sdists[0]
errors = []

with zipfile.ZipFile(wheel) as zf:
    names = zf.namelist()
    meta_names = [n for n in names if n.endswith(".dist-info/METADATA")]
    if len(meta_names) != 1:
        fail(f"{wheel.name} has {len(meta_names)} METADATA files, expected 1")
    meta = Parser().parsestr(zf.read(meta_names[0]).decode())

wheel_files = sorted(n for n in names if ".dist-info/" not in n)
if wheel_files != expected_wheel:
    errors.append(f"wheel files differ from git-tracked package files: "
                  f"extra {sorted(set(wheel_files) - set(expected_wheel))}, "
                  f"missing {sorted(set(expected_wheel) - set(wheel_files))}")
if meta["Version"] != version:
    errors.append(f"wheel Version {meta['Version']} != {version} from {version_cfg['path']}")
if meta["Requires-Python"] != requires_python:
    errors.append(f"wheel Requires-Python {meta['Requires-Python']!r} != {requires_python!r} from pyproject.toml")

with tarfile.open(sdist) as tf:
    sdist_files = sorted(m.name.split("/", 1)[1] for m in tf.getmembers() if m.isfile() and "/" in m.name)
if sdist_files != expected_sdist:
    errors.append(f"sdist files differ from the allow-list: "
                  f"extra {sorted(set(sdist_files) - set(expected_sdist))}, "
                  f"missing {sorted(set(expected_sdist) - set(sdist_files))}")

print(f"wheel {wheel.name}: {', '.join(wheel_files)}")
print(f"sdist {sdist.name}: {', '.join(sdist_files)}")
print(f"Version {meta['Version']}, Requires-Python {meta['Requires-Python']}")
if errors:
    fail("\n".join(errors))
print("ok")
