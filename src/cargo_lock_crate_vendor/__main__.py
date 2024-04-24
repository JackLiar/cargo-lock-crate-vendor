#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import asyncio
import io
import json
import logging
import os
import re
from argparse import ArgumentParser
from typing import Dict, List, Optional, Set

import httpx
import toml

CRATE_RE = re.compile(r"[^\s]+(\s.+)*")
LOG_FORMAT = "%(asctime)s [%(levelname)s] - [%(filename)s > %(funcName)s() > %(lineno)s] - %(message)s"


class Crate:
    def __init__(self):
        self.name = ""
        self.version = ""

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, o) -> bool:
        return self.name == o.name and self.version == o.version


class Index:
    def __init__(self):
        self.dir = ""
        self.name = ""
        self.content = ""

    def __hash__(self) -> int:
        return hash((self.dir, self.name, self.content))

    def __eq__(self, o) -> bool:
        return self.dir == o.dir and self.content == o.content and self.name == o.name


def parse_cargo_lock(fp: io.TextIOBase) -> Set[Crate]:
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


def get_directory(crate_name: str):
    if len(crate_name) <= 2:
        return str(len(crate_name))
    elif len(crate_name) == 3:
        return str(len(crate_name)), crate_name[0]

    dir1 = crate_name[0:2]
    dir2 = crate_name[2:4]
    return dir1, dir2


async def get_index(crate_name: str, registry: Optional[str] = None) -> Index:
    subdir = get_directory(crate_name)

    index = Index()
    if isinstance(subdir, str):
        index_sub_path = subdir
    else:
        (dir1, dir2) = subdir
        index_sub_path = os.path.join(dir1, dir2)
    index.dir = index_sub_path
    index.name = crate_name
    logging.debug(index.dir)

    if registry is None:
        if isinstance(subdir, str):
            url = f"https://raw.githubusercontent.com/rust-lang/crates.io-index/master/{subdir}/{crate_name}"
        else:
            (dir1, dir2) = subdir
            url = f"https://raw.githubusercontent.com/rust-lang/crates.io-index/master/{dir1}/{dir2}/{crate_name}"
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url)
            index.content = r.text
    else:
        if isinstance(subdir, str):
            fpath = os.path.join(f"{os.path.abspath(registry)}", subdir, crate_name)
        else:
            (dir1, dir2) = subdir
            fpath = os.path.join(f"{os.path.abspath(registry)}", dir1, dir2, crate_name)
        with open(fpath) as fp:
            content = fp.read()
            index.content = content
    return index


async def get_crate_versions(
    crate_name: str, max_previous: int = 5, registry: Optional[str] = None
) -> List[str]:
    versions = []
    result = get_directory(crate_name)

    if registry is None:
        if isinstance(result, str):
            url = f"https://raw.githubusercontent.com/rust-lang/crates.io-index/master/{result}/{crate_name}"
        else:
            (dir1, dir2) = result
            url = f"https://raw.githubusercontent.com/rust-lang/crates.io-index/master/{dir1}/{dir2}/{crate_name}"
        logging.debug(url)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            r = await client.get(url)
            lines = list(r.content.splitlines())
            for line in lines[max(len(lines) - max_previous, 0) :]:
                crate_info = json.loads(line.decode())
                ver = crate_info["vers"]
                versions.append(ver)
    else:
        if isinstance(result, str):
            fpath = os.path.join(f"{os.path.abspath(registry)}", result, crate_name)
        else:
            (dir1, dir2) = result
            fpath = os.path.join(f"{os.path.abspath(registry)}", dir1, dir2, crate_name)
        # logging.debug(fpath)
        with open(fpath) as fp:
            lines = fp.readlines()
            for line in lines[max(len(lines) - max_previous, 0) :]:
                crate_info = json.loads(line)
                ver = crate_info["vers"]
                versions.append(ver)
    return versions


async def download_crate(crate: Crate) -> bytes:
    logging.info(f"downloading {crate.name} {crate.version}")
    transport = httpx.AsyncHTTPTransport(retries=5)
    async with httpx.AsyncClient(transport=transport) as client:
        url = f"https://static.crates.io/crates/{crate.name}/{crate.name}-{crate.version}.crate"

        r = await client.get(url)
        return r.content


def save_crate(crate: Crate, content: bytes, output_dir: str):
    odir = os.path.join(output_dir, crate.name, crate.version)
    os.makedirs(odir, exist_ok=True)
    fpath = os.path.join(odir, "download")
    with open(fpath, "wb") as fp:
        fp.write(content)


def save_index(index: Index, output_dir: str):
    odir = os.path.join(output_dir, index.dir)
    os.makedirs(odir, exist_ok=True)
    fpath = os.path.join(odir, index.name)
    with open(fpath, "w") as fp:
        fp.write(index.content)


def parse_args() -> Dict:
    parser = ArgumentParser()
    parser.add_argument("-i", "--input", help="Cargo.lock location")
    parser.add_argument(
        "--all", help="download all versions of all crates", action="store_true"
    )
    parser.add_argument(
        "-n", "--name", help="target crate name, must use with --version option"
    )
    parser.add_argument(
        "-v", "--version", help="target crate version, must use with --name option"
    )
    parser.add_argument("-o", "--output", help=".crate save location", default="crates")
    parser.add_argument("--index-ouput", help="index save location", default="index")
    parser.add_argument(
        "-r", "--registry", help="crates.io-index git registry location"
    )
    parser.add_argument("--max-previous", help="max previous crate version", type=int)
    return vars(parser.parse_args())


async def async_main():
    cfg = parse_args()

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    logging.getLogger("httpx").setLevel(logging.INFO)

    output_dir = os.path.abspath(cfg["output"])
    registry = cfg.get("registry", None)
    if registry:
        registry = os.path.abspath(registry)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    index_ouput_dir = os.path.abspath(cfg["index_ouput"])
    if not os.path.exists(index_ouput_dir):
        os.makedirs(index_ouput_dir, exist_ok=True)

    downloaded_crates = get_downloaded_crates(output_dir)

    crates = set()
    if cfg.get("input", None) is not None:
        with open(cfg["input"], "r") as fp:
            crates = parse_cargo_lock(fp)
    elif cfg.get("name", None) is not None and cfg.get("version", None) is not None:
        crate = Crate()
        name = cfg.get("name", None)
        version = cfg.get("version", None)
        if name is None or version is None:
            raise Exception("")
        crate.name = name
        crate.version = version
        crates = set([crate])
    
    indexes = set()
    for crate in crates:
        indexes.add(await get_index(crate.name, registry))
    for index in indexes:
        save_index(index, index_ouput_dir)

    crates = sorted(crates, key=lambda c: (c.name, c.version))
    if cfg.get("all") or cfg.get("max_previous"):
        max_previous = 0
        if cfg.get("all"):
            max_previous = 2**16
        else:
            max_previous = cfg.get("max_previous")
            if max_previous is None:
                raise Exception("no max_previous is provided")

        extra_crates = set()
        for crate in crates:
            versions = await get_crate_versions(crate.name, max_previous, registry)
            for version in versions:
                c = Crate()
                c.name = crate.name
                c.version = version
                extra_crates.add(c)

        crates = set(crates)
        crates.update(extra_crates)

    crates = sorted(crates, key=lambda c: (c.name, c.version))

    for crate in crates:
        if crate in downloaded_crates:
            print(f"{crate.name} {crate.version} is already downloaded")
            continue

        content = await download_crate(crate)
        save_crate(crate, content, output_dir)


def main():
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
