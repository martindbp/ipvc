import os
import io
import sys
import json
import hashlib
from functools import wraps
from pathlib import Path

import ipfsapi


def expand_ref(ref: str):
    # TODO: support numbers, i.e. head~10
    if (ref.startswith('@head') or
            ref.startswith('@stage') or
            ref.startswith('@workspace')):
        ref = ref[1:] # get rid of the @
        ref = ref.replace('~', '/parent1')
        ref = ref.replace('^', '/parent2')
    return ref


def transfer_ref_to_ref(refpath_from: Path, refpath_to: Path):
    """ Transfer the files part from `ref_from` `to ref_to`
    Expected behavior:
        ref_from            ref_to            result
        "@head~/myfolder"    "@stage"           "@stage/myfolder"
        "@head/myfile.txt"   "@head~~"          "@head~~/myfile.txt"
        "@head"              "@head~~"          "@head~~"
        "@head/myfile.txt"   "@head~/myfolder/" raise exception
        "@head/f/myfile.txt" "@stage/f/"        "@stage/f/myfile.txt"
    """
    pass


def separate_refpath(refpath: Path):
    """ Separate the ref from path """
    parts = refpath.parts
    if len(parts) == 0:
        return None, None

    if not parts[0].startswith('@'):
        return None, refpath

    return parts[0], Path(*parts[1:])


def go_to_parent(refpath: Path):
    """ Go to the parent (1) of ref
    Expected behavior:
        "@head" -> "@head~"
        "@head/mydir/ -> "@head~/mydir"
        "@stage" -> raise exception
    """
    pass


def refpath_to_mfs(refpath: Path):
    """ Expands a reference to the files location
    Expected behavior:
        "@head~^/myfolder/myfile.txt" ->
            "head/parent1/parent2/bundle/files/myfolder/myfile.txt"
        "@stage/myfolder/myfile.txt" ->
            "stage/bundle/files/myfolder/myfile.txt"
        "myfolder/myfile.txt" ->
            "workspace/bundle/files/myfolder/myfile.txt"
        "@{commit_hash}/myfolder" ->
            "/ipfs/{commit_hash}/workspace/bundle/files/myfolder"
        "@{branch}/@head/myfolder" ->
            "{branch}/head/bundle/files/myfolder"
    """
    ref, path = separate_refpath(refpath)
    if ref is not None:
        ref = expand_ref(ref)
        if ref not in ['head', 'workspace', 'stage']:
            # Treat it as a commit hash
            return Path('/ipfs') / ref / 'bundle/files' / path, path

        return ref / Path('bundle/files') / path, path
    else:
        # Assume a path in workspace
        return Path('workspace/bundle/files') / refpath, refpath

    return None, None


def print_changes(changes):
    for change in changes:
        type_ = change['Type']
        before = (change['Before'] or {}).get('/', None)
        after = (change['After'] or {}).get('/', None)
        path = change['Path']
        if type_ == 0:
            print(f'+ {path} {after}')
        elif type_ == 1:
            print(f'- {path} {before}')
        elif type_ == 2:
            print(f'{path} {before} --> {after}')


def make_len(string, num):
    string = string[:num]
    return string + ' '*(num-len(string))


def atomic(api_method):
    """ Wraps a method to make it atomic on IPFS, meaning the method will
    operate on a copy of the real mfs ipvc folder and the resulting modified folder
    will replace the original only when the method was executed successfully """

    @wraps(api_method)
    def _impl(self, *args, **kwargs):
        if self._in_atomic_operation:
            return api_method(self, *args, **kwargs)

        self._in_atomic_operation = True
        tmp_namespace = Path('/ipvc_tmp')
        try:
            self.ipfs.files_rm(tmp_namespace / 'ipvc', recursive=True)
        except:
            pass
        self.ipfs.files_mkdir(tmp_namespace, parents=True)
        old_namespace, self.namespace = self.namespace, tmp_namespace
        try:
            self.ipfs.files_cp(old_namespace / 'ipvc', tmp_namespace / 'ipvc')
        except:
            pass
        try:
            ret = api_method(self, *args, **kwargs)
        except:
            self.namespace = old_namespace
            self._in_atomic_operation = False
            raise

        try:
            self.ipfs.files_rm(old_namespace / 'ipvc', recursive=True)
        except:
            pass

        # Note: the api method might not have created an ipvc folder
        # e.g. if first time use and running any command but ipvc repo init
        try:
            self.ipfs.files_cp(tmp_namespace / 'ipvc', old_namespace / 'ipvc')
        except:
            pass
        self.namespace = old_namespace
        self._in_atomic_operation = False
        return ret

    return _impl


class CommonAPI:
    def __init__(self, _ipfs, _fs_cwd, _namespace='/', quiet=False, verbose=False):
        self.ipfs = _ipfs
        self.fs_cwd = _fs_cwd
        self.namespace = Path(_namespace)
        self.quiet = quiet
        self.verbose = verbose
        self._in_atomic_operation = False

    def get_mfs_path(self, fs_workspace_root=None, branch=None, repo_info=None,
                     branch_info=None, ipvc_info=None):
        path = Path(self.namespace) / 'ipvc'
        if ipvc_info is not None:
            return path / ipvc_info
        if fs_workspace_root is None:
            return path
        # Encode the workspace path in hex so that we can store the path
        # information in the directory name itself. Then there's no need to name
        # it and # store the path some other way
        workspace_hex = str(fs_workspace_root).encode('utf-8').hex()
        path = path / 'repos' / workspace_hex
        if repo_info is not None:
            return path / repo_info
        if branch is None:
            return path
        path = path / branch
        if branch_info is not None:
            return path / branch_info
        return path

    def ipfs_object_diff(self, hash_a, hash_b):
        ret = self.ipfs.object_diff(hash_a, hash_b)
        # Due to a bug in go-ipfs 0.4.13 diffing an emtpy directory with itself
        # results in a bogus change, so filter out empty changes:
        changes = ret['Changes'] or []
        changes = [change for change in changes
                   if change['Before'] != change['After']]
        ret['Changes'] = changes
        return ret

    def get_active_branch(self, fs_workspace_root):
        mfs_branch = self.get_mfs_path(
            fs_workspace_root, repo_info='active_branch_name')
        branch = self.ipfs.files_read(mfs_branch).decode('utf-8')
        return branch

    def get_workspace_root(self, fs_cwd=None):
        fs_cwd = fs_cwd or self.fs_cwd
        try:
            ls = self.ipfs.files_ls(self.get_mfs_path(ipvc_info='repos'))
            workspaces_hex = set(entry['Name'] for entry in ls['Entries'])
        except ipfsapi.exceptions.StatusError:
            return None

        for workspace_hex in workspaces_hex:
            workspace = bytes.fromhex(workspace_hex).decode('utf-8')
            workspace_parts = Path(workspace).parts
            if fs_cwd.parts[:len(workspace_parts)] == workspace_parts:
                return Path(workspace)
        return None

    def workspace_changes(self, fs_add_path, metadata, update_meta=True):
        """ Returns a list of updated, removed and modified file paths under
        'fs_add_path' as compared to the stored metadata
        """
        metadata_files = set(Path(path) for path in metadata.keys()
                             if str(fs_add_path) in path)
        if fs_add_path.is_file():
            fs_add_files = set([fs_add_path])
        else:
            fs_add_files = set(p for p in fs_add_path.glob('**/*')
                               if not p.is_dir())

        added = fs_add_files - metadata_files
        removed = metadata_files - fs_add_files
        persistent = metadata_files & fs_add_files
        timestamps = {str(path): path.stat().st_mtime_ns for path
                      in (persistent | added)}
        modified = set(
            (path for path in persistent if metadata.get(str(path), {})\
             .get('timestamp', None) != timestamps[str(path)]))

        if update_meta:
            for path, ts in timestamps.items():
                metadata.setdefault(path, {})['timestamp'] = ts

        return added, removed, modified

    def mfs_read_json(self, path):
        try:
            return json.loads(self.ipfs.files_read(path).decode('utf-8'))
        except ipfsapi.exceptions.StatusError:
            return {}

    def mfs_write_json(self, data, path):
        try:
            self.ipfs.files_rm(path)
        except ipfsapi.exceptions.StatusError:
            pass
        data_bytes = io.BytesIO(json.dumps(data).encode('utf-8'))
        self.ipfs.files_write(path, data_bytes, create=True, truncate=True)

    def get_metadata_file(self, ref):
        fs_workspace_root = self.get_workspace_root()
        branch = self.get_active_branch(fs_workspace_root)
        return self.get_mfs_path(
            fs_workspace_root, branch, branch_info=f'{ref}/bundle/metadata')

    def read_metadata(self, ref):
        return self.mfs_read_json(self.get_metadata_file(ref))

    def write_metadata(self, metadata, ref):
        self.mfs_write_json(metadata, self.get_metadata_file(ref))

    def read_global_params(self):
        return self.mfs_read_json(self.get_mfs_path(ipvc_info='params.json'))

    def write_global_params(self, params):
        mfs_params = self.get_mfs_path(ipvc_info='params.json')
        return self.mfs_write_json(params, mfs_params)

    def add_fs_to_mfs(self, fs_add_path, mfs_ref):
        """ Adds the changes in a workspace under fs_add_path to a ref and
        returns the changes, and number of files that needed hashing

        Speed: ipfs.add does not check timestamps (timestamps are not stored
        in ipfs folder/file structure) which means it re-hashes large files over
        and over. This would be too slow for our purposes, therefore we keep
        metadata for each file in a ref and use that to build up the tree
        instead

        Symlinks: ipfs.add doesn't follow symlinks, for good reason (just like git)
        but we want symlinks within a repo to be traversable in ipfs, so we need
        to store symlinks as normal hash-links in ipfs, but as symlinks when
        checked out / mounted. We can therefore store the symlink info in the
        metadata but follow the symlink in the bundle files.
        """

        fs_workspace_root = self.get_workspace_root()
        branch = self.get_active_branch(fs_workspace_root)
        mfs_files_root = self.get_mfs_path(
            fs_workspace_root, branch, branch_info=f'{mfs_ref}/bundle/files')

        # Copy over the current ref root to a temporary
        mfs_new_files_root = Path(f'{self.namespace}/ipvc/tmp')
        try:
            self.ipfs.files_rm(mfs_new_files_root, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass
        
        self.ipfs.files_cp(mfs_files_root, mfs_new_files_root)
        add_path_relative = fs_add_path.relative_to(fs_workspace_root)

        # Find the changes between the ref and the workspace, and modify the tmp root
        metadata = self.read_metadata(mfs_ref)
        added, removed, modified = self.workspace_changes(fs_add_path, metadata)

        def _mfs_files_path(fs_path):
            relative_path = fs_path.relative_to(fs_workspace_root)
            return mfs_new_files_root / relative_path


        for fs_path in removed | modified:
            self.ipfs.files_rm(_mfs_files_path(fs_path), recursive=True)

        for fs_path in removed:
            del metadata[str(fs_path)]

        num_hashed = 0
        printed_header = False
        for fs_path in added | modified:
            try:
                dir_path = _mfs_files_path(fs_path).parent
                self.ipfs.files_mkdir(dir_path, parents=True)
            except ipfsapi.exceptions.StatusError:
                pass
            self.ipfs.files_cp(f'/ipfs/{self.ipfs.add(fs_path)["Hash"]}',
                               _mfs_files_path(fs_path))
            num_hashed += 1
            if self.verbose:
                if not printed_header:
                    if not self.quiet: print('Updating workspace:')
                    printed_header = True
                if not self.quiet:
                    print(make_len(f'{fs_path[len(self.fs_cwd):]}', 80), end='\r')

        if self.verbose and num_hashed > 0:
            if not self.quiet:
                print(make_len(f'added {num_hashed} files', 80), end='\r\n')
                print('-'*80)

        new_files_root_hash = self.ipfs.files_stat(mfs_new_files_root)['Hash']
        metadata = self.write_metadata(metadata, mfs_ref)
        try:
            self.ipfs.files_rm(mfs_files_root, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass

        try:
            self.ipfs.files_mkdir(mfs_files_root.parent)
        except ipfsapi.exceptions.StatusError:
            pass

        self.ipfs.files_cp(mfs_new_files_root, mfs_files_root)
        diff = self.ipfs_object_diff(
            self.ipfs.files_stat(mfs_files_root)['Hash'], new_files_root_hash)

        return diff.get('Changes', []), num_hashed

    def get_mfs_changes(self, refpath_from, refpath_to):
        fs_workspace_root = self.get_workspace_root()
        branch = self.get_active_branch(fs_workspace_root)

        mfs_from_path = self.get_mfs_path(
            fs_workspace_root, branch, branch_info=refpath_from)
        mfs_to_path = self.get_mfs_path(
            fs_workspace_root, branch, branch_info=refpath_to)
        try:
            stat = self.ipfs.files_stat(mfs_from_path)
            mfs_from_hash = stat['Hash']
            from_empty = False
        except ipfsapi.exceptions.StatusError:
            from_empty = True

        try:
            self.ipfs.files_stat(mfs_to_path)
            mfs_to_hash = self.ipfs.files_stat(mfs_to_path)['Hash']
            to_empty = False
        except ipfsapi.exceptions.StatusError:
            to_empty = True

        if from_empty and to_empty:
            changes = []
        elif from_empty:
            changes = [{
                'Type': 0, 'Before': {'/': None}, 'After': {'/': mfs_to_hash},
                'Path': ''
            }]
        elif to_empty:
            changes = [{
                'Type': 1, 'Before': {'/': mfs_from_hash}, 'After': {'/': None},
                'Path': ''
            }]
        else:
            changes = self.ipfs_object_diff(
                mfs_from_hash, mfs_to_hash)['Changes'] or []
        return changes, from_empty, to_empty

    def add_ref_changes_to_ref(self, ref_from, ref_to, path):
        """ Add changes from 'ref_from' to 'ref_to' and returns the changes"""
        fs_workspace_root = self.get_workspace_root()
        branch = self.get_active_branch(fs_workspace_root)

        mfs_refpath_from, _ = refpath_to_mfs(f'@{ref_from}' / path)
        mfs_refpath_to, _ = refpath_to_mfs(f'@{ref_to}' / path)

        mfs_from_add_path = self.get_mfs_path(
            fs_workspace_root, branch, branch_info=mfs_refpath_from)
        mfs_to_add_path = self.get_mfs_path(
            fs_workspace_root, branch, branch_info=mfs_refpath_to)

        # Get the reverse changes from the copying direction
        changes, to_empty, from_empty = self.get_mfs_changes(
            mfs_refpath_to, mfs_refpath_from)

        # Remove to_path so we can copy over the subtree
        if not to_empty:
            try:
                self.ipfs.files_rm(mfs_to_add_path, recursive=True)
            except ipfsapi.exceptions.StatusError:
                pass

        if not from_empty:
            # Transfer the subtree
            try:
                self.ipfs.files_mkdir(mfs_to_add_path.parent, parents=True)
            except ipfsapi.exceptions.StatusError:
                pass
            self.ipfs.files_cp(mfs_from_add_path, mfs_to_add_path)

            # Transfer the metadata for files under the add path
            from_metadata = self.read_metadata(ref_from)
            to_metadata = self.read_metadata(ref_to)
            # First filter out any path under mfs_add_path
            to_metadata = {path: val for path, val in to_metadata.items()
                           if not path.startswith(str(mfs_to_add_path))}
            # Then copy over all metadata under mfs_add_path
            to_metadata.update((path, val) for path, val in from_metadata.items()
                               if path.startswith(str(mfs_to_add_path)))
            self.write_metadata(to_metadata, ref_to)

        return changes

    def update_mfs_workspace(self):
        fs_workspace_root = self.get_workspace_root()
        changes, num_hashed = self.add_fs_to_mfs(
            fs_workspace_root, 'workspace')

    def common(self):
        fs_workspace_root = self.get_workspace_root()
        if fs_workspace_root is None:
            if not self.quiet: print('No ipvc repository here', file=sys.stderr)
            raise RuntimeError()

        self.update_mfs_workspace()
        branch = self.get_active_branch(fs_workspace_root)
        return fs_workspace_root, branch
