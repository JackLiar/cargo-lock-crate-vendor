#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import asyncio
import io
import os
import re
from argparse import ArgumentParser
from typing import Dict, Set

import httpx
import toml

CRATE_RE = re.compile(r"[^\s]+(\s.+)*")


class Crate:
    def __init__(self):
        self.name = ""
        self.version = ""

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, o: object) -> bool:
        return self.name == o.name and self.version == o.version


def parse_cargo_lock(fp: io.StringIO) -> Set[Crate]:
    crates = set()

    content = toml.load(fp)
    for crate in content["package"]:
        source = crate.get("source", "")
        if not source or source.startswith("git+"):
            # if a crate does not contains source field, it's probably a workspace crate
            continue

        c = Crate()
        c.name = crate["name"]
        c.version = crate["version"]
        crates.add(c)

        deps = crate.get("dependencies", [])
        for dep in deps:
            matches = CRATE_RE.match(dep)
            if not matches:
                raise ValueError(
                    "crate regular expression does cover dependency syntax"
                )

            parts = dep.split(" ")
            name = parts[0]
            if len(parts) == 1:
                continue

            version = parts[1]
            c = Crate()
            c.name = name
            c.version = version
            crates.add(c)

    return crates


def get_downloaded_crates(dir: str) -> Set[Crate]:
    """Get already downloaded crates from output directory

    Args:
        dir: target output directory

    Returns:
        Set[Crate]:  crates already downloaded
    """
    crates = set()

    for root, dirs, files in os.walk(dir):
        for file in files:
            if file != "download":
                continue

            fpath = os.path.join(root, file)
            crate_path = os.path.dirname(fpath)
            crate = Crate()
            crate.version = os.path.basename(crate_path)
            crate.name = os.path.basename(os.path.dirname(crate_path))
            crates.add(crate)

    return crates


def parse_args() -> Dict:
    parser = ArgumentParser()
    parser.add_argument("-i", "--input", help="Cargo.lock location")
    parser.add_argument(
        "-n", "--name", help="target crate name, must use with --version option"
    )
    parser.add_argument(
        "-v", "--version", help="target crate version, must use with --name option"
    )
    parser.add_argument("-o", "--output", help=".crate save location", default="crates")
    return vars(parser.parse_args())


async def async_main():
    cfg = parse_args()
    output_dir = os.path.abspath(cfg["output"])

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    downloaded_crates = get_downloaded_crates(output_dir)

    if cfg.get("input", None) is not None:
        with open(cfg["input"], "r") as fp:
            crates = parse_cargo_lock(fp)
            crates = sorted(crates, key=lambda c: (c.name, c.version))
    elif cfg.get("name", None) is not None and cfg.get("version", None) is not None:
        crate = Crate()
        crate.name = cfg.get("name", None)
        crate.version = cfg.get("version", None)
        crates = [crate]

    for crate in crates:
        if crate in downloaded_crates:
            print(f"{crate.name} {crate.version} is already downloaded")
            continue

        print(f"downloading {crate.name} {crate.version}")
        async with httpx.AsyncClient() as client:
            url = f"https://static.crates.io/crates/{crate.name}/{crate.name}-{crate.version}.crate"

            r = await client.get(url)

            odir = os.path.join(output_dir, crate.name, crate.version)
            os.makedirs(odir, exist_ok=True)
            fpath = os.path.join(odir, "download")
            with open(fpath, "wb") as fp:
                fp.write(r.content)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
