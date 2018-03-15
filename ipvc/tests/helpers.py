import os
import shutil
import pytest
from pathlib import Path
from ipvc import IPVC

# Set a prefix so we don't interfere with live ipvc objects
NAMESPACE = Path('/test')
REPO = Path('/tmp/ipvc/repo')
REPO2 = Path('/tmp/ipvc/repo2')

def get_environment(path=REPO, mkdirs=True):
    ipvc = IPVC(path, NAMESPACE)
    try:
        ipvc.ipfs.files_rm(NAMESPACE, recursive=True)
    except:
        pass
    ipvc.ipfs.files_mkdir(NAMESPACE)

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
