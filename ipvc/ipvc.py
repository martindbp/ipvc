import os
import sys
from pathlib import Path
from ipvc.repo import RepoAPI
from ipvc.stage import StageAPI
from ipvc.branch import BranchAPI
from ipvc.diff import DiffAPI
from ipvc.param import ParamAPI

import ipfsapi

class IPVC:
    def __init__(self, cwd:Path=None, namespace='/', quiet=False, verbose=False):
        cwd = cwd or Path.cwd()
        assert isinstance(cwd, Path)

        try:
            self.ipfs = ipfsapi.connect()
        except ipfsapi.exceptions.ConnectionError:
            print("Couldn't connect to ipfs, is it running?", file=sys.stderr)
            exit(1)

        args = (self.ipfs, cwd, namespace, quiet, verbose)
        self.repo = RepoAPI(*args)
        self.stage = StageAPI(*args)
        self.branch = BranchAPI(*args)
        self.diff = DiffAPI(*args)
        self.param = ParamAPI(*args)

    def set_cwd(self, cwd):
        assert isinstance(cwd, Path)
        self.repo.fs_cwd = cwd
        self.stage.fs_cwd = cwd
        self.branch.fs_cwd = cwd
        self.diff.fs_cwd = cwd
        self.param.fs_cwd = cwd
