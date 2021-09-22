#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from setuptools import find_namespace_packages, setup

setup(
    name="cargo-lock-crate-vendor",
    version="0.1.0",
    package_dir={"": "src"},
    packages=find_namespace_packages(where="src"),
    install_requires=["httpx", "toml"],
    entry_points={
            "console_scripts": [
                "cargo-lock-crate-vendor=cargo_lock_crate_vendor.__main__:main"
            ],
        },
)
