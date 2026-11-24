#!/usr/bin/env bash
# Set up the isolated benchmark inputs. Run under the same affinity as measure.py.
set -euo pipefail

work=$(realpath "$1")
mkdir -p "$work/repos"
uv_bin=${UV_BIN:-uv}

checkout() {
    local name=$1 url=$2 revision=$3 destination="$work/repos/$1"
    if [[ ! -d "$destination/.git" ]]; then
        git init -q "$destination"
    fi
    if ! git -C "$destination" cat-file -e "$revision^{commit}" 2>/dev/null; then
        git -C "$destination" fetch -q --depth=1 "$url" "$revision"
    fi
    git -C "$destination" checkout -q --detach "$revision"
}

checkout more-itertools https://github.com/more-itertools/more-itertools.git 4aeb4338ae1407d8da9723e86da99efeb446f719
checkout rich https://github.com/Textualize/rich.git 6ac483cbea39cab124dfd3483bba70ffafb71050
checkout pytest https://github.com/pytest-dev/pytest.git 3d10b5148e03eb82b3ee29181dbdc73cf82699e2

wheel=codmap-0.0.48-py3-none-any.whl
python3 - "$work" "$wheel" <<'PY'
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import urlopen

work, wheel = Path(sys.argv[1]), sys.argv[2]
with urlopen("https://pypi.org/pypi/codmap/0.0.48/json", timeout=30) as response:
    release = json.load(response)
entry = next(file for file in release["urls"] if file["filename"] == wheel)
with urlopen(entry["url"], timeout=30) as response:
    data = response.read()
digest = hashlib.sha256(data).hexdigest()
if digest != entry["digests"]["sha256"]:
    raise RuntimeError("Published wheel digest mismatch")
(work / wheel).write_bytes(data)
(work / "wheel.sha256").write_text(f"{digest}  {wheel}\n")
PY

"$uv_bin" venv --python 3.12 "$work/.venv"
"$uv_bin" pip install --python "$work/.venv/bin/python" --index-url https://pypi.org/simple \
    "codmap[mcp] @ file://$work/$wheel"
"$work/.venv/bin/codemap" --version
