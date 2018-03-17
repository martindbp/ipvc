import io
import os
import sys
import webbrowser
from pathlib import Path

import ipfsapi
from ipvc.common import CommonAPI, expand_ref, refpath_to_mfs, make_len, atomic

class BranchAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def status(self, name=False):
        fs_workspace_root, branch = self.common()
        active = self.ipfs.files_read(
            self.get_mfs_path(self.fs_cwd, repo_info='active_branch_name')).decode('utf-8')
        if not self.quiet: print(active)
        return active

    @atomic
    def create(self, name, from_commit="@head", no_checkout=False):
        fs_workspace_root, branch = self.common()

        if not name.replace('_', '').isalnum():
            if not self.quiet:
                print('Branch name has to be alpha numeric with underscores',
                      file=sys.stderr)
            raise RuntimeError()

        try:
            self.ipfs.files_stat(self.get_mfs_path(self.fs_cwd, name))
            if not self.quiet: print('Branch name already exists', file=sys.stderr)
            raise RuntimeError()
        except ipfsapi.exceptions.StatusError:
            pass

        if from_commit == "@head":
            # Simply copy the current branch to the new branch
            self.ipfs.files_cp(
                self.get_mfs_path(self.fs_cwd, branch),
                self.get_mfs_path(self.fs_cwd, name))
        else:
            # Create the branch directory along with an empty stage and workspace
            for ref in ['stage', 'workspace']:
                mfs_ref = self.get_mfs_path(self.fs_cwd, name, branch_info=ref)
                self.ipfs.files_mkdir(mfs_ref, parents=True)

            # Copy the commit to the new branch's head
            commit_path = expand_ref(from_commit)
            mfs_commit_path = self.get_mfs_path(
                self.fs_cwd, branch, branch_info=commit_path)
            mfs_head_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='head')

            try:
                self.ipfs.files_stat(mfs_commit_path)
            except ipfsapi.exceptions.StatusError:
                if not self.quiet:
                    print('No such commit', file=sys.stderr)
                raise RuntimeError()

            self.ipfs.files_cp(mfs_commit_path, mfs_head_path)

            # Copy commit bundle to workspace and stage, plus a parent1 link
            # from stage to head
            mfs_commit_bundle_path = f'{mfs_commit_path}/bundle'
            mfs_workspace_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='workspace/bundle')
            mfs_stage_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='stage/bundle')
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_workspace_path)
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_stage_path)

        if not no_checkout:
            self.checkout(name)

    def _load_ref_into_workspace(self, fs_workspace_root, branch, ref,
                                 without_timestamps=False):
        """ Syncs the fs workspace with the files in ref """
        metadata = self.read_metadata(ref)
        added, removed, modified = self.workspace_changes(
            fs_workspace_root, metadata, update_meta=False)

        mfs_refpath, _ = refpath_to_mfs(Path(f'@{ref}'))

        for path in added:
            os.remove(path)

        for path in removed | modified:
            mfs_path = self.get_mfs_path(
                fs_workspace_root, branch,
                branch_info=(mfs_refpath / path.relative_to(fs_workspace_root)))

            timestamp = metadata[str(path)]['timestamp']

            with open(path, 'wb') as f:
                f.write(self.ipfs.files_read(mfs_path))

            os.utime(path, ns=(timestamp, timestamp))

    @atomic
    def checkout(self, name, without_timestamps=False):
        """ Checks out a branch"""
        fs_workspace_root, _ = self.common()

        try:
            self.ipfs.files_stat(self.get_mfs_path(self.fs_cwd, name))
        except ipfsapi.exceptions.StatusError:
            if not self.quiet: print('No branch by that name exists', file=sys.stderr)
            raise RuntimeError()

        # Write the new branch name to active_branch_name
        # NOTE: truncate here is needed to clear the file before writing
        self.ipfs.files_write(
            self.get_mfs_path(self.fs_cwd, repo_info='active_branch_name'),
            io.BytesIO(bytes(name, 'utf-8')),
            create=True, truncate=True)

        self._load_ref_into_workspace(
            fs_workspace_root, name, 'workspace', without_timestamps)

    @atomic
    def history(self, show_ref=False):
        """ Shows the commit history for the current branch. Currently only shows
        the linear history on the first parents side"""
        fs_workspace_root, branch = self.common()

        # Traverse the commits backwards by adding /parent1/parent1/parent1/... etc
        # to the mfs path until it stops
        curr_commit = Path('head')
        commits = []
        while True:
            mfs_commit = self.get_mfs_path(
                fs_workspace_root, branch, branch_info=curr_commit)
            mfs_commit_meta = mfs_commit / 'metadata'
            try:
                mfs_commit_hash = self.ipfs.files_stat(mfs_commit)['Hash']
                mfs_commit_ref_hash = self.ipfs.files_stat(
                    mfs_commit / 'bundle/files')['Hash']
            except ipfsapi.exceptions.StatusError:
                # Reached the root of the graph
                break

            meta = self.mfs_read_json(mfs_commit_meta)
            if len(meta) == 0:
                # Reached the root of the graph
                break

            h, ts, msg = mfs_commit_hash[:6], meta['timestamp'], meta['message']
            auth = make_len(meta['author'] or '', 30)
            if not self.quiet: 
                if show_ref:
                    print(f'* {mfs_commit_ref_hash} {ts} {auth}   {msg}')
                else:
                    print(f'* {ts} {auth}   {msg}')

            commits.append(mfs_commit_hash)
            curr_commit = curr_commit / 'parent1'

        return commits

    @atomic
    def show(self, refpath):
        """ Opens a ref in the ipfs file browser """
        fs_workspace_root, branch = self.common()

        files, _ = refpath_to_mfs(refpath)
        try:
            mfs_commit = self.get_mfs_path(fs_workspace_root, branch, branch_info=files)
            mfs_commit_hash = self.ipfs.files_stat(mfs_commit)['Hash']
        except ipfsapi.exceptions.StatusError:
            if not self.quiet: print('No such ref', file=sys.stderr)
            raise RuntimeError()

        url = f'http://localhost:8080/ipfs/{mfs_commit_hash}'
        if not self.quiet: print(f'Opening {url}')
        webbrowser.open(url)


    @atomic
    def merge(self, refpath):
        """ Merge refpath into this branch

        """
        pass
