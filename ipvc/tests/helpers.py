import os
import shutil
import pytest
from pathlib import Path
from ipvc import IPVC
import cProfile, pstats, io

# Set a prefix so we don't interfere with live ipvc objects
NAMESPACE = Path('/test')
REPO = Path('/tmp/ipvc/repo')
REPO2 = Path('/tmp/ipvc/repo2')

def get_environment(path=REPO, mkdirs=True):
    ipvc = IPVC(path, NAMESPACE, delete_mfs=True)

    try:
        shutil.rmtree('/tmp/ipvc')
    except:
        pass

    if mkdirs:
        path.mkdir(parents=True)
    return ipvc


def write_file(path, string):
    with open(path, 'w') as f:
        f.write(string)


class Profile():
    def __init__(self):
        pass

    def __enter__(self):
        self.pr = cProfile.Profile()
        self.pr.enable()

    def __exit__(self, *args):
        self.pr.disable()
        s = io.StringIO()
        self.ps = pstats.Stats(self.pr, stream=s)
        self.ps.print_stats()
        print(s.getvalue())
