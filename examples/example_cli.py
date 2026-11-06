"""
Example CLI
Example uses of the CLI to start the dataviewer
"""

import subprocess

def run(cmd: str = ""):
    output = subprocess.run(cmd, shell=True, capture_output=True, check=True)
    print(output.stdout.decode())


# run("dataviewer")

run("cd /dls/i10-1/data/2025/nt42193-1; dataviewer .")


