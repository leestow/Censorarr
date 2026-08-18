from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import InvalidVersion, Version


ROOTS = {
    "nvidia-cuda-runtime-cu12": None,
    "nvidia-cublas-cu12": "12.9.2.10",
    "nvidia-cudnn-cu12": "9.24.0.43",
}


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "Censorarr-GPU-Worker-build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def latest_satisfying(name: str, specifier) -> str:
    data = fetch_json(f"https://pypi.org/pypi/{name}/json")
    candidates = []
    for raw in data.get("releases", {}):
        try:
            version = Version(raw)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        if specifier and version not in specifier:
            continue
        files = data["releases"].get(raw) or []
        if files and not all(bool(x.get("yanked")) for x in files):
            candidates.append(version)
    if not candidates:
        raise RuntimeError(f"No stable PyPI release found for {name}{specifier or ''}")
    return str(max(candidates))


def release_data(name: str, version: str | None) -> tuple[str, dict]:
    if version is None:
        base = fetch_json(f"https://pypi.org/pypi/{name}/json")
        version = str(base["info"]["version"])
    return version, fetch_json(f"https://pypi.org/pypi/{name}/{version}/json")


def select_wheel(data: dict, platform: str) -> dict:
    files = data.get("urls") or []
    if platform == "windows-amd64":
        matches = [x for x in files if str(x.get("filename", "")).endswith("win_amd64.whl")]
    elif platform == "linux-amd64":
        matches = [
            x for x in files
            if str(x.get("filename", "")).endswith("x86_64.whl")
            and "manylinux" in str(x.get("filename", ""))
        ]
    else:
        raise ValueError(platform)
    matches = [x for x in matches if not x.get("yanked")]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {platform} wheel for {data.get('info', {}).get('name')} "
            f"{data.get('info', {}).get('version')}, found {[x.get('filename') for x in matches]}"
        )
    return matches[0]


def resolve(platform: str) -> dict:
    queue: list[tuple[str, str | None]] = list(ROOTS.items())
    chosen: dict[str, str] = {}
    package_data: dict[str, dict] = {}

    while queue:
        raw_name, requested_version = queue.pop(0)
        name = normalize(raw_name)
        if name in chosen:
            if requested_version and chosen[name] != requested_version:
                raise RuntimeError(
                    f"Conflicting versions requested for {name}: {chosen[name]} vs {requested_version}"
                )
            continue

        version, data = release_data(name, requested_version)
        chosen[name] = version
        package_data[name] = data

        for raw_req in data.get("info", {}).get("requires_dist") or []:
            req = Requirement(raw_req)
            dep_name = normalize(req.name)
            if not dep_name.startswith("nvidia-"):
                continue
            if req.marker and not req.marker.evaluate():
                continue
            dep_version = latest_satisfying(dep_name, req.specifier)
            queue.append((dep_name, dep_version))

    packages = []
    for name in sorted(chosen):
        version = chosen[name]
        data = package_data[name]
        wheel = select_wheel(data, platform)
        packages.append({
            "name": name,
            "version": version,
            "filename": wheel["filename"],
            "url": wheel["url"],
            "sha256": wheel["digests"]["sha256"],
            "size": int(wheel["size"]),
        })

    return {
        "schema": 1,
        "platform": platform,
        "roots": ROOTS,
        "packages": packages,
        "download_bytes": sum(x["size"] for x in packages),
        "source": "NVIDIA-maintained packages on PyPI; exact wheel URLs and SHA-256 hashes resolved at build time",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", choices=["windows-amd64", "linux-amd64"], required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    data = resolve(args.platform)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
