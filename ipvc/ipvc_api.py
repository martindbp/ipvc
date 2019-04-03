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
from ipvc.id import IdAPI

import ipfsapi


class IPVC:
    def __init__(self, cwd:Path=None, mfs_namespace=None, ipfs_ip=None,
                 delete_mfs=False, init_mfs=True, quiet=False, quieter=False,
                 verbose=False, stdout=None, stderr=None):
        cwd = cwd or Path.cwd()
        mfs_namespace = mfs_namespace or '/'
        assert isinstance(cwd, Path)

        ip_port_args = []
        if ipfs_ip is not None:
            try:
                ip, port = ipfs_ip.split(':')
                ip_port_args.append(ip)
                if len(port) > 0:
                    ip_port_args.append(int(port))
            except:
                print("IPFS ip/port '{ipfs_ip}' is not on the right format, e.g. '127.0.0.1:5000'",
                      file=sys.stderr)
                raise RuntimeError
            if ip not in ['localhost', '127.0.0.1']:
                # NOTE: since we cannot get a peer_id's public/private key
                # through the go-ipfs HTTP API as of writing, we have to get
                # the keys by first calling repo_stat() to get the location of
                # the ipfs repo, and then read the keys from the filesystem,
                # therefore, the node we're connecting to has to be local
                print('Currently only localhost ipfs nodes are supported',
                      file=sys.stderr)
                raise RuntimeError


        try:
            self.ipfs = ipfsapi.connect(*ip_port_args)
        except ipfsapi.exceptions.ConnectionError:
            print("Couldn't connect to IPFS, is it running?", file=sys.stderr)
            exit(1)

        if delete_mfs:
            try:
                self.ipfs.files_rm(Path(mfs_namespace) / 'ipvc', recursive=True)
            except:
                pass
            try:
                self.ipfs.files_rm(Path(mfs_namespace) / 'ipvc_snapshots', recursive=True)
            except:
                pass

        if init_mfs:
            # Create the ipvc dir, and snapshots, since it will be used when
            # making api calls atomic
            try:
                self.ipfs.files_mkdir(Path(mfs_namespace) / 'ipvc', parents=True)
                self.ipfs.files_mkdir(Path(mfs_namespace) / 'ipvc_snapshots', parents=True)
            except:
                pass

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

        args = (self, self.ipfs, cwd, mfs_namespace, quiet, quieter, verbose,
                stdout, stderr)
        self.repo = RepoAPI(*args)
        self.stage = StageAPI(*args)
        self.branch = BranchAPI(*args)
        self.diff = DiffAPI(*args)
        self.id = IdAPI(*args)
        self._property_cache = {}

    def set_cwd(self, cwd):
        assert isinstance(cwd, Path)
        self.repo.set_cwd(cwd)
        self.stage.set_cwd(cwd)
        self.branch.set_cwd(cwd)
        self.diff.set_cwd(cwd)
        self.id.set_cwd(cwd)

    def print_ipfs_profile_info(self):
        print('Call counts:')
        for name, count in self._call_count.items():
            print(f'{name}: {count}')
        print('Timings:')
        for name, timing in self._timings.items():
            print(f'{name}: {timing}')
