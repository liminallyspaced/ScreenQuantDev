#!/usr/bin/env python3
import os, sys, subprocess
blender = os.environ.get("QT_BLENDER", "/home/box/apps/blender-5.2.0-linux-x64/blender")
args = [blender] + sys.argv[1:]
print("RUN", args, flush=True)
os.execv(blender, args)
