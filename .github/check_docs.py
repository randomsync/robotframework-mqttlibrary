"""Check that docs/index.html documents the installed MQTTLibrary.

Usage: python .github/check_docs.py <path to index.html>

Regenerates the keyword documentation with libdoc and compares the library
data libdoc embeds in both files. The generation time and the absolute
source paths differ on every machine, so they are ignored, and so is the
surrounding HTML, which changes with the Robot Framework version. Run
`make docs` to regenerate the file.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

MARKER = "libdoc = "
IGNORED_KEYS = {"generated", "source"}


def fail(message):
    sys.exit(f"check_docs: {message}")


def library_data(path):
    html = Path(path).read_text(encoding="utf-8")
    start = html.find(MARKER)
    if start < 0:
        fail(f"{path} has no embedded libdoc data")
    try:
        data, _ = json.JSONDecoder().raw_decode(html, start + len(MARKER))
    except json.JSONDecodeError as exc:
        fail(f"cannot read the libdoc data in {path}: {exc}")
    return normalize(data)


def normalize(value):
    if isinstance(value, dict):
        return {
            key: normalize(item)
            for key, item in value.items()
            if key not in IGNORED_KEYS
        }
    if isinstance(value, list):
        return [normalize(item) for item in value]
    return value


def differences(committed, current):
    diffs = []
    for key in sorted(set(committed) | set(current)):
        if key == "keywords":
            continue
        if committed.get(key) != current.get(key):
            diffs.append(f"library {key}")
    old = {kw["name"]: kw for kw in committed.get("keywords", [])}
    new = {kw["name"]: kw for kw in current.get("keywords", [])}
    for name in sorted(set(old) | set(new)):
        if name not in old:
            diffs.append(f"keyword {name} is missing")
        elif name not in new:
            diffs.append(f"keyword {name} no longer exists")
        elif old[name] != new[name]:
            diffs.append(f"keyword {name} differs")
    return diffs


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    committed = library_data(sys.argv[1])
    with tempfile.TemporaryDirectory() as tmp:
        generated = Path(tmp, "index.html")
        subprocess.run(
            [sys.executable, "-m", "robot.libdoc", "MQTTLibrary", str(generated)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        current = library_data(generated)
    diffs = differences(committed, current)
    if diffs:
        fail(
            f"{sys.argv[1]} is out of date ({'; '.join(diffs)}). "
            "Regenerate it with `make docs`."
        )
    print(f"{sys.argv[1]} matches the installed library")


if __name__ == "__main__":
    main()
