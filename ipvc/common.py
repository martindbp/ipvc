import os
import io
import sys
import json
from datetime import datetime
import hashlib
import difflib
from functools import wraps
from pathlib import Path

import ipfsapi


def expand_ref(ref: str):
    # TODO: support numbers, i.e. head~10
    if (ref.startswith('@head') or
            ref.startswith('@stage') or
            ref.startswith('@workspace')):
        ref = ref[1:] # get rid of the @
        ref = ref.replace('~', '/parent')
        ref = ref.replace('^', '/merge_parent')
    elif ref.startswith('@'):
        ref = ref[1:]
    return ref


def separate_refpath(refpath: Path):
    """ Separate the ref from path """
    parts = refpath.parts
    if len(parts) == 0:
        return None, None

    if not parts[0].startswith('@'):
        return None, refpath

    return parts[0], Path(*parts[1:])


def make_len(string, num):
    string = string[:num]
    return string + ' '*(num-len(string))


# NOTE: set this variable to True to test that cached properties
#       are cached correctly
TEST_CACHING = False
def cached_property(prop):
    @wraps(prop)
    def _impl(self, *args, **kwargs):
        name = prop.__name__
        if name not in self.ipvc._property_cache:
            self.ipvc._property_cache[name] = prop(self, *args, **kwargs)

        if TEST_CACHING:
            correct = prop(self, *args, **kwargs)
            if correct != self.ipvc._property_cache[name]:
                print('Cache error: ', correct, self.ipvc._property_cache[name])
                import pdb; pdb.set_trace()
            return correct
        else:
            return self.ipvc._property_cache[name]

    return _impl


def atomic(api_method):
    """ Wraps a method to make it atomic on IPFS, meaning the method will
    will save a copy of the entire ipvc data-store before calling the method,
    and restore it to that copy if an exception is raised within the method.
    TODO: implement a lock on the ipvc folder so that concurrent ipvc calls can't
    fail
    """

    @wraps(api_method)
    def _impl(self, *args, **kwargs):
        if self._in_atomic_operation:
            return api_method(self, *args, **kwargs)

        self._in_atomic_operation = True
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S.%f") 
        snapshot_dir = self.namespace / f'ipvc_snapshots/{timestamp}'
        self.ipfs.files_cp(self.namespace / 'ipvc', snapshot_dir)

        try:
            ret = api_method(self, *args, **kwargs)
        except:
            self._in_atomic_operation = False
            self.ipfs.files_rm(self.namespace / 'ipvc', recursive=True)
            self.ipfs.files_cp(snapshot_dir, self.namespace / 'ipvc')
            raise

        self._in_atomic_operation = False
        return ret

    return _impl


class CommonAPI:
    def __init__(self, _ipvc, _ipfs, _fs_cwd, _namespace='/', quiet=False,
                 verbose=False, stdout=None, stderr=None):
        self.ipvc = _ipvc
        self.ipfs = _ipfs
        self.fs_cwd = _fs_cwd
        self.namespace = Path(_namespace)
        self.quiet = quiet
        self.verbose = verbose
        self.stdout = stdout
        self.stderr = stderr
        self._in_atomic_operation = False


    def print(self, *args, **kwargs):
        if self.quiet: return
        print(*args, **kwargs)
        if self.stdout:
            print(*args, **kwargs, file=self.stdout)

    def print_err(self, *args, **kwargs):
        print(*args, **kwargs, file=sys.stderr)
        if self.stderr:
            print(*args, **kwargs, file=self.stderr)

    def print_changes(self, changes):
        for change in changes:
            type_ = change['Type']
            before = (change['Before'] or {}).get('/', None)
            after = (change['After'] or {}).get('/', None)
            path = change['Path']
            path = path + ' ' if path is not '' else ''
            if type_ == 0:
                self.print(f'+ {path}{after}')
            elif type_ == 1:
                self.print(f'- {path}{before}')
            elif type_ == 2:
                self.print(f'{path}{before} --> {after}')

    def invalidate_cache(self, props=None):
        if props is None:
            self.ipvc._property_cache = {}
            return

        for prop in props:
            if prop in self.ipvc._property_cache:
                del self.ipvc._property_cache[prop]


    def refpath_to_mfs(self, refpath: Path):
        """ Expands a reference to the files location
        Expected behavior:
            "@head~^/myfolder/myfile.txt" ->
                "head/parent/merge_parent/bundle/files/myfolder/myfile.txt"
            "@stage/myfolder/myfile.txt" ->
                "stage/bundle/files/myfolder/myfile.txt"
            "myfolder/myfile.txt" ->
                "workspace/bundle/files/myfolder/myfile.txt"
            "@{commit_hash}/myfolder" ->
                "/ipfs/{commit_hash}/bundle/files/myfolder"
            "@{branch}/myfolder" ->
                "{branch}/head/bundle/files/myfolder"

        Returns (branch, mfs_path, workspace_path)
        """
        ref, path = separate_refpath(refpath)
        if ref is not None:
            ref = expand_ref(ref)
            if ref in ['head', 'workspace', 'stage']:
                return None, ref / Path('bundle/files') / path, path
            elif ref in self.branches:
                return (ref, *self.refpath_to_mfs(Path(path))[1:])
            else:
                # Treat it as a commit hash
                return None, Path('/ipfs') / ref / 'bundle/files' / path, path

        else:
            # Assume a path in workspace
            return None, Path('workspace/bundle/files') / refpath, refpath

        return None, None, None

    def get_mfs_path(self, fs_repo_root=None, branch=None, repo_info=None,
                     branch_info=None, ipvc_info=None):
        path = Path(self.namespace) / 'ipvc'
        if ipvc_info is not None:
            return path / ipvc_info
        if fs_repo_root is None:
            return path
        # Encode the repo path in hex so that we can store the path
        # information in the directory name itself. Then there's no need to name
        # it and # store the path some other way
        repo_hex = str(fs_repo_root).encode('utf-8').hex()
        path = path / 'repos' / repo_hex
        if repo_info is not None:
            return path / repo_info
        if branch is None:
            if branch_info is not None:
                branch = self.active_branch
            else:
                return path
        path = path / 'branches' / branch
        if branch_info is not None:
            return path / branch_info
        return path

    @property
    @cached_property
    def active_branch(self):
        return self.get_active_branch(self.fs_repo_root)

    def get_active_branch(self, fs_repo_root):
        mfs_branch = self.get_mfs_path(
            fs_repo_root, repo_info='active_branch_name')
        branch = self.ipfs.files_read(mfs_branch).decode('utf-8')
        return branch

    @property
    @cached_property
    def branches(self):
        mfs_branches_path = self.get_mfs_path(
            self.fs_repo_root, repo_info='branches')
        ls_ret = self.ipfs.files_ls(mfs_branches_path)
        return [entry['Name'] for entry in ls_ret['Entries']]

    def list_repo_paths(self, fs_cwd=None):
        fs_cwd = fs_cwd or self.fs_cwd
        try:
            repos_mfs_path = self.get_mfs_path(ipvc_info='repos')
            ls = self.ipfs.files_ls(repos_mfs_path)
            for entry in ls['Entries'] or []:
                repo_hex = entry['Name']
                fs_repo_path = bytes.fromhex(repo_hex).decode('utf-8')
                repo_mfs_path = Path(repos_mfs_path) / repo_hex
                repo_hash = self.ipfs.files_stat(repo_mfs_path)['Hash']
                yield repo_hash, fs_repo_path
        except ipfsapi.exceptions.StatusError:
            return

    def set_cwd(self, cwd):
        self.fs_cwd = cwd
        self.invalidate_cache()

    @property
    @cached_property
    def fs_repo_root(self):
        return self.get_repo_root()

    def get_repo_root(self, fs_cwd=None):
        fs_cwd = fs_cwd or self.fs_cwd
        for _, fs_repo_path in self.list_repo_paths(fs_cwd):
            repo_parts = Path(fs_repo_path).parts
            if fs_cwd.parts[:len(repo_parts)] == repo_parts:
                return Path(fs_repo_path)
        return None

    def workspace_changes(self, fs_add_path, fs_repo_root, metadata, update_meta=True):
        """ Returns a list of updated, removed and modified file paths under
        'fs_add_path' as compared to the stored metadata
        """
        fs_add_path_relative = Path(fs_add_path).relative_to(fs_repo_root)
        metadata_files = set()
        for path in metadata.keys():
            try:
                Path(path).relative_to(fs_add_path_relative)
                metadata_files.add(path)
            except:
                pass
        if fs_add_path.is_file():
            fs_add_files = set([str(fs_add_path_relative)])
        else:
            fs_add_files = set(str(p.relative_to(fs_repo_root))
                               for p in fs_add_path.glob('**/*')
                               if not p.is_dir())

        added = fs_add_files - metadata_files
        removed = metadata_files - fs_add_files
        persistent = metadata_files & fs_add_files
        timestamps = {str(path): (fs_repo_root / path).stat().st_mtime_ns for path
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
        data_bytes = io.BytesIO(json.dumps(data).encode('utf-8'))
        self.ipfs.files_write(path, data_bytes, create=True, truncate=True)

    def get_metadata_file(self, ref):
        return self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=f'{ref}/bundle/files_metadata')

    def read_files_metadata(self, ref):
        return self.mfs_read_json(self.get_metadata_file(ref))

    def write_files_metadata(self, metadata, ref):
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

        mfs_files_root = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=f'{mfs_ref}/bundle/files')

        # Copy over the current ref root to a temporary
        mfs_new_files_root = Path(self.namespace) / 'ipvc' / 'tmp'
        try:
            self.ipfs.files_rm(mfs_new_files_root, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass
        
        self.ipfs.files_cp(mfs_files_root, mfs_new_files_root)
        add_path_relative = fs_add_path.relative_to(self.fs_repo_root)

        # Find the changes between the ref and the workspace, and modify the tmp root
        files_metadata = self.read_files_metadata(mfs_ref)
        added, removed, modified = self.workspace_changes(
            fs_add_path, self.fs_repo_root, files_metadata)

        for fs_path in removed | modified:
            self.ipfs.files_rm(mfs_new_files_root / fs_path, recursive=True)

        for fs_path in removed:
            del files_metadata[str(fs_path)]

        num_hashed = 0
        printed_header = False
        for fs_path in added | modified:
            try:
                dir_path = (mfs_new_files_root / fs_path).parent
                self.ipfs.files_mkdir(dir_path, parents=True)
            except ipfsapi.exceptions.StatusError:
                pass
            h = self.ipfs.add(self.fs_repo_root / fs_path)["Hash"]
            self.ipfs.files_cp(f'/ipfs/{h}', mfs_new_files_root / fs_path)

            num_hashed += 1
            if self.verbose:
                if not printed_header:
                    self.print('Updating workspace:')
                    printed_header = True
                fs_path_from_cwd = Path(fs_path).relative_to(self.fs_cwd)
                self.print(make_len(str(fs_path_from_cwd), 80), end='\r')

        if self.verbose and num_hashed > 0:
            self.print(make_len(f'added {num_hashed} files', 80), end='\r\n')
            self.print('-'*80)

        new_files_root_hash = self.ipfs.files_stat(mfs_new_files_root)['Hash']
        self.write_files_metadata(files_metadata, mfs_ref)
        try:
            self.ipfs.files_rm(mfs_files_root, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass

        try:
            self.ipfs.files_mkdir(mfs_files_root.parent)
        except ipfsapi.exceptions.StatusError:
            pass

        self.ipfs.files_cp(mfs_new_files_root, mfs_files_root)
        diff = self.ipfs.object_diff(
            self.ipfs.files_stat(mfs_files_root)['Hash'], new_files_root_hash)

        return diff.get('Changes', []), num_hashed

    def get_mfs_changes(self, refpath_from, refpath_to):
        mfs_from_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=refpath_from)
        mfs_to_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=refpath_to)
        try:
            stat = self.ipfs.files_stat(mfs_from_path)
            from_hash = stat['Hash']
            from_empty = False
        except ipfsapi.exceptions.StatusError:
            from_empty = True

        try:
            self.ipfs.files_stat(mfs_to_path)
            to_hash = self.ipfs.files_stat(mfs_to_path)['Hash']
            to_empty = False
        except ipfsapi.exceptions.StatusError:
            to_empty = True

        if from_empty and to_empty:
            changes = []
        elif from_empty:
            changes = [{
                'Type': 0, 'Before': {'/': None}, 'After': {'/': to_hash},
                'Path': ''
            }]
        elif to_empty:
            changes = [{
                'Type': 1, 'Before': {'/': from_hash}, 'After': {'/': None},
                'Path': ''
            }]
        else:
            changes = self.ipfs.object_diff(
                from_hash, to_hash)['Changes'] or []
        return changes, from_empty, to_empty

    def add_ref_changes_to_ref(self, ref_from, ref_to, add_path):
        """ Add changes from 'ref_from' to 'ref_to' under
        `add_path` (relative to repo root) and returns the changes"""
        _, mfs_refpath_from, _ = self.refpath_to_mfs(Path(f'@{ref_from}') / add_path)
        _, mfs_refpath_to, _ = self.refpath_to_mfs(Path(f'@{ref_to}') / add_path)

        mfs_from_add_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=mfs_refpath_from)
        mfs_to_add_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=mfs_refpath_to)

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
            from_metadata = self.read_files_metadata(ref_from)
            to_metadata = self.read_files_metadata(ref_to)
            # First remove any file under `add_path` in to_metadata
            new_to_metadata = {}
            for path, val in to_metadata.items():
                try:
                    Path(path).relative_to(add_path)
                except:
                    new_to_metadata[path] = val
            # Then copy over all metadata under `path` from from_metadata
            for path, val in from_metadata.items():
                try:
                    Path(path).relative_to(add_path)
                    new_to_metadata[path] = val
                except:
                    pass

            self.write_files_metadata(new_to_metadata, ref_to)

        return changes

    def update_mfs_repo(self):
        return self.add_fs_to_mfs(
            self.fs_repo_root, 'workspace')

    def common(self):
        if self.fs_repo_root is None:
            self.print_err('No ipvc repository here')
            raise RuntimeError()

        self.update_mfs_repo()
        return self.fs_repo_root, self.active_branch

    def get_refpath_files_hash(self, refpath):
        branch, files, _ = self.refpath_to_mfs(refpath)
        mfs_commit_files = self.get_mfs_path(self.fs_repo_root, branch=branch, branch_info=files)
        try:
            commit_files_hash = self.ipfs.files_stat(mfs_commit_files)['Hash']
        except ipfsapi.exceptions.StatusError:
            self.print_err('No such ref')
            raise RuntimeError()

        return commit_files_hash

    def get_branch_info_hash(self, branch, info):
        mfs_commit_path = self.get_mfs_path(self.fs_repo_root, branch=branch, branch_info=info)
        try:
            commit_hash = self.ipfs.files_stat(mfs_commit_path)['Hash']
        except ipfsapi.exceptions.StatusError:
            self.print_err('No such ref')
            raise RuntimeError()

        return commit_hash

    def _diff_resolve_refs(self, to_refpath=None, from_refpath=None,
                           to_default="@workspace", from_default='@stage'):
        to_refpath, from_refpath  = Path(to_refpath), Path(from_refpath)
        if from_refpath is None and to_refpath is None:
            to_refpath = '@workspace'
            from_refpath = '@stage'
            _, mfs_to_refpath, _ = self.refpath_to_mfs(to_refpath)
            _, mfs_from_refpath, _ = self.refpath_to_mfs(from_refpath)
        elif from_refpath is None:
            _, mfs_to_refpath, files_part = self.refpath_to_mfs(to_refpath)
            _, mfs_from_refpath, _ = self.refpath_to_mfs(from_default / files_part)
        else:
            _, mfs_to_refpath, _ = self.refpath_to_mfs(to_refpath)
            _, mfs_from_refpath, _ = self.refpath_to_mfs(from_refpath)

        return mfs_to_refpath, mfs_from_refpath

    def _diff(self, to_refpath, from_refpath, files):
        # TODO: change the files parameter to 'diff_content_only'
        to_refpath, from_refpath = self._diff_resolve_refs(to_refpath, from_refpath)
        changes, *_ = self.get_mfs_changes(from_refpath, to_refpath)
        if files:
            self.print_changes(changes)

            return changes
        else:
            for change in changes:
                from_lines = (self.ipfs.cat(change['Before']['/']).decode('utf-8').split('\n')
                              if change['Before'] is not None else [])
                to_lines = (self.ipfs.cat(change['After']['/']).decode('utf-8').split('\n')
                            if change['After'] is not None else [])

                if change['Type'] == 2: # modified
                    from_file_path = change['Path']
                    to_file_path = from_file_path
                elif change['Type'] == 1: # deleted
                    to_file_path = '/dev/null'
                    from_file_path = change['Path']
                elif change['Type'] == 0: # added
                    to_file_path = change['Path']
                    from_file_path = '/dev/null'
                diff = difflib.unified_diff(from_lines, to_lines, lineterm='',
                                            fromfile=from_file_path,
                                            tofile=to_file_path)
                self.print('\n'.join(list(diff)[:-1]))

            return changes

