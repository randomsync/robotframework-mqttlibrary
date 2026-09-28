"""Release checks for the publish job.

Usage:
  python .github/release.py check <tag>   the tag must equal the version in
                                          version.py; prints whether it is a
                                          pre-release and writes
                                          prerelease=true|false to
                                          $GITHUB_OUTPUT when set
  python .github/release.py notes <version>
                                          prints that version's CHANGELOG
                                          section, without its heading
"""

import os
import re
import sys
from pathlib import Path

from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src/MQTTLibrary/version.py"
CHANGELOG = ROOT / "CHANGELOG.md"


def fail(message):
    sys.exit(f"release: {message}")


def package_version():
    match = re.search(
        r"VERSION = ['\"]([^'\"]+)['\"]", VERSION_FILE.read_text(encoding="utf-8")
    )
    if not match:
        fail(f"no VERSION in {VERSION_FILE}")
    return match.group(1)


def check(tag):
    version = package_version()
    if tag != version:
        fail(f"tag {tag} does not match version {version} in version.py")
    try:
        parsed = Version(version)
    except InvalidVersion:
        fail(f"version {version} is not a valid PEP 440 version")
    if str(parsed) != version:
        fail(f"version {version} is not in canonical form ({parsed})")
    prerelease = "true" if parsed.is_prerelease else "false"
    print(f"tag {tag} matches version.py; prerelease={prerelease}")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as fh:
            fh.write(f"prerelease={prerelease}\n")


def notes(version):
    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    heading = re.compile(r"^## \[" + re.escape(version) + r"\](\s|$)")
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        fail(f"CHANGELOG.md has no section for {version}")
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("## [") or re.match(r"^\[[^\]]+\]: ", lines[i])
        ),
        len(lines),
    )
    body = "\n".join(lines[start + 1 : end]).strip()
    if not body:
        fail(f"the CHANGELOG section for {version} is empty")
    print(body)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "notes"):
        sys.exit(__doc__)
    {"check": check, "notes": notes}[sys.argv[1]](sys.argv[2])


if __name__ == "__main__":
    main()
