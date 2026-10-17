#!/usr/bin/env python3
import sys

from cricketstats.mongodb_assistant import main

if __name__ == "__main__":
    raise SystemExit(main(["--ipl", *sys.argv[1:]]))
