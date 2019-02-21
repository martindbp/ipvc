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

        args = (self, self.ipfs, cwd, namespace, quiet, verbose)
        self.repo = RepoAPI(*args)
        self.stage = StageAPI(*args)
        self.branch = BranchAPI(*args)
        self.diff = DiffAPI(*args)
        self.param = ParamAPI(*args)
        self._property_cache = {}

    def set_cwd(self, cwd):
        assert isinstance(cwd, Path)
        self.repo.set_cwd(cwd)
        self.stage.set_cwd(cwd)
        self.branch.set_cwd(cwd)
        self.diff.set_cwd(cwd)
        self.param.set_cwd(cwd)

