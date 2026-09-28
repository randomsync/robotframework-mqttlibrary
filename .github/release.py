"""Release checks for the publish job.

Usage:
  python .github/release.py check <tag>   the tag must equal the package
                                          version (read like hatchling, via
                                          [tool.hatch.version] in
                                          pyproject.toml); prints whether it is a
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

import tomllib
from packaging.version import InvalidVersion, Version

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
# A link reference definition, as in the block at the end of CHANGELOG.md.
LINK_DEFINITION = re.compile(r"^\[[^\]]+\]: \S+")


def fail(message):
    sys.exit(f"release: {message}")


def package_version():
    """The version as hatchling reads it: [tool.hatch.version] in pyproject."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    config = pyproject["tool"]["hatch"]["version"]
    path = ROOT / config["path"]
    match = re.search(config["pattern"], path.read_text(encoding="utf-8"), re.M)
    if not match:
        fail(f"the [tool.hatch.version] pattern does not match {config['path']}")
    return match.group("version")


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
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    section = lines[start + 1 : end]
    # The last section is followed by the link definitions for the headings.
    while section and (not section[-1].strip() or LINK_DEFINITION.match(section[-1])):
        section.pop()
    body = "\n".join(section).strip()
    if not body:
        fail(f"the CHANGELOG section for {version} is empty")
    print(body)


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in ("check", "notes"):
        sys.exit(__doc__)
    {"check": check, "notes": notes}[sys.argv[1]](sys.argv[2])


if __name__ == "__main__":
    main()
