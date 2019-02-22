import os
import sys
import time
from pathlib import Path
from collections import defaultdict
from functools import wraps
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


        def object_diff(hash_a, hash_b):
            # NOTE: use ipfs.object_diff when it's released
            return self.ipfs._client.request(
                '/object/diff', (hash_a, hash_b), decoder='json')
        setattr(self.ipfs, 'object_diff', object_diff)

        self._timings = defaultdict(lambda: 0)
        self._call_count = defaultdict(lambda: 0)
        self.print_calls = False
        def _profile(method):
            @wraps(method)
            def _impl(*args, **kwargs):
                t0 = time.time()
                ret = method(*args, **kwargs)
                t1 = time.time()
                self._call_count[method.__name__] += 1
                self._timings[method.__name__] += t1 - t0
                if self.print_calls:
                    print(f'{(t1-t0):.3} {method.__name__}', *args)
                return ret
            return _impl

        profile_methods = [
            'files_rm', 'files_cp', 'files_write', 'files_mkdir', 'files_stat',
            'files_ls', 'files_read', 'ls', 'cat', 'object_diff'
        ]
        for m in profile_methods:
            setattr(self.ipfs, m, _profile(getattr(self.ipfs, m)))

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

    def print_ipfs_profile_info(self):
        print('Call counts:')
        for name, count in self._call_count.items():
            print(f'{name}: {count}')
        print('Timings:')
        for name, timing in self._timings.items():
            print(f'{name}: {timing}')
