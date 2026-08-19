import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402


def main():
    section("nvidia-smi factory-startup paths")
    path = os.path.join(PROJECT_ROOT, "scenequant", "analysis", "memory_model.py")
    src = open(path, encoding="utf-8").read()
    check("def nvidia_smi_binaries" in src, "nvidia_smi_binaries is defined")
    check("shutil.which" in src, "PATH lookup uses shutil.which")
    check("System32" in src and "nvidia-smi.exe" in src,
          "Windows System32 nvidia-smi is a candidate")
    check("NVSMI" in src and "nvidia-smi.exe" in src,
          "legacy NVSMI install dir is a candidate")
    finish()


main()
