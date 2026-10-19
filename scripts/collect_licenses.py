"""Collect installed runtime dependency notices for a binary build.

Run after build dependencies are installed. Does not certify compliance for
native libraries, firmware, LGPL corresponding source, or external tools.
"""
from importlib.metadata import distribution
import json
from pathlib import Path
import shutil

from packaging.requirements import Requirement


def collect(root: Path):
    target = root / "build" / "licenses"
    target.mkdir(parents=True, exist_ok=True)
    pending = ["bumble", "libusb1", "libusb-package", "pystray", "pillow"]
    seen = set()
    records = []
    while pending:
        name = pending.pop()
        dist = distribution(name)
        key = dist.metadata["Name"].lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        copied = []
        for file in dist.files or ():
            if any(token in file.name.lower() for token in ("license", "licence", "copying", "notice")):
                source = Path(dist.locate_file(file))
                if source.is_file():
                    destination = target / key / Path(str(file))
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)
                    copied.append(str(destination.relative_to(target)).replace("\\", "/"))
        records.append({"name": key, "version": dist.version,
                        "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                        "project_urls": dist.metadata.get_all("Project-URL", []), "notices": copied})
        for spec in dist.requires or ():
            requirement = Requirement(spec)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    (target / "dependencies.json").write_text(json.dumps(sorted(records, key=lambda row: row["name"]), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Collected notices for {len(records)} runtime packages in {target}")


if __name__ == "__main__":
    collect(Path(__file__).resolve().parents[1])
