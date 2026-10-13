# -*- coding: utf-8 -*-
"""``python -m lingshu_ng``：命令行入口（见 :mod:`lingshu_ng.integrations.cli`）。"""
import sys

from .integrations.cli import main

if __name__ == "__main__":
    sys.exit(main())
