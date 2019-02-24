import os
import io
import json
import sys
from pathlib import Path
from datetime import datetime

import ipfsapi
from ipvc.common import CommonAPI, print_changes, atomic


class StageAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _get_relative_paths(self, fs_paths, fs_repo_root):
        fs_paths = fs_paths if isinstance(fs_paths, list) else [fs_paths]
        for fs_path in fs_paths:
            fs_path = Path(os.path.abspath(fs_path))
            try: 
                yield fs_path.relative_to(fs_repo_root)
            except:
                # Doesn't start with workspace_root
                if not self.quiet:
                    print(f'Path outside workspace {fs_path}', file=sys.stderr)
                raise

    def _notify_pull_merge(self, fs_repo_root, branch):
        mfs_merge_parent = self.get_mfs_path(fs_repo_root, branch, branch_info='merge_parent')
        try:
            self.ipfs.files_stat(mfs_merge_parent)
            if not self.quiet:
                print(('NOTE: you are in the merge conflict state, the next '
                       'commit will be the merge commit. To abort merge, run '
                       '`ipvc branch pull --abort`\n'))
        except:
            pass

    @atomic
    def add(self, fs_paths=None):
        """ Add the path to ipfs, and replace the stage files at that path with
        the new hash.
        """
        self.common()
        fs_paths = self.fs_cwd if fs_paths is None else fs_paths
        changes = []
        for fs_path_relative in self._get_relative_paths(fs_paths, self.fs_repo_root):
            changes = changes + self.add_ref_changes_to_ref(
                'workspace', 'stage', fs_path_relative)

        if not self.quiet: 
            if len(changes) == 0:
                print('No changes')
            else:
                print('Changes:')
                print_changes(changes)
        return changes

    @atomic
    def remove(self, fs_paths):
        """ Add the path to ipfs, and replace the stage files at that path with
        the new hash.
        """
        self.common()
        changes = []
        for fs_path_relative in self._get_relative_paths(fs_paths, self.fs_repo_root):
            changes = changes + self.add_ref_changes_to_ref(
                'head', 'stage', fs_path_relative)

        if not self.quiet:
            if len(changes) == 0:
                print('No changes')
            else:
                print('Changes:')
                print_changes(changes)
        return changes

    @atomic
    def status(self):
        """ Show diff between workspace and stage, and between stage and head """
        self.common()
        self._notify_pull_merge(self.fs_repo_root, self.active_branch)

        head_stage_changes, *_ = self.get_mfs_changes(
            'head/bundle/files', 'stage/bundle/files')
        if not self.quiet: 
            if len(head_stage_changes) == 0:
                print('No staged changes')
            else:
                print('Staged:')
                print_changes(head_stage_changes)
                print('-'*80)

        stage_workspace_changes, *_ = self.get_mfs_changes(
            'stage/bundle/files', 'workspace/bundle/files')
        if not self.quiet:
            if len(stage_workspace_changes) == 0:
                print('No unstaged changes')
            else:
                print('Unstaged:')
                print_changes(stage_workspace_changes)

        return head_stage_changes, stage_workspace_changes

    @atomic
    def commit(self, message):
        """ Creates a new commit with the staged changes and returns new commit hash"""
        self.common()

        mfs_head = self.get_mfs_path(self.fs_repo_root, self.active_branch, branch_info='head')
        mfs_stage = self.get_mfs_path(self.fs_repo_root, self.active_branch, branch_info='stage')
        head_hash = self.ipfs.files_stat(mfs_head)['Hash']
        stage_hash = self.ipfs.files_stat(mfs_stage)['Hash']
        if head_hash == stage_hash:
            print('Nothing to commit', file=sys.stderr)
            raise RuntimeError

        # Set head to stage
        try:
            self.ipfs.files_rm(mfs_head, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass

        self.ipfs.files_cp(mfs_stage, mfs_head)

        # Add parent pointer to previous head
        self.ipfs.files_cp(f'/ipfs/{head_hash}', f'{mfs_head}/parent')

        # Add merge_parent to merged head if this was a merge commit
        mfs_merge_parent = self.get_mfs_path(self.fs_repo_root, self.active_branch,
                                             branch_info='merge_parent')
        is_merge = False
        try:
            self.ipfs.files_cp(mfs_merge_parent, f'{mfs_head}/merge_parent')
            mfs_merge_stage_backup = self.get_mfs_path(
                self.fs_repo_root, self.active_branch, branch_info='merge_stage_backup')
            mfs_merge_workspace_backup = self.get_mfs_path(
                self.fs_repo_root, self.active_branch, branch_info='merge_workspace_backup')
            self.ipfs.files_rm(mfs_merge_parent, recursive=True)
            self.ipfs.files_rm(mfs_merge_stage_backup, recursive=True)
            self.ipfs.files_rm(mfs_merge_workspace_backup, recursive=True)
            is_merge = True
        except:
            pass

        # Add metadata
        params = self.read_global_params()
        metadata = {
            'message': message,
            'author': params.get('author', None),
            'timestamp': datetime.utcnow().isoformat(),
            'is_merge': is_merge
        }

        metadata_bytes = io.BytesIO(json.dumps(metadata).encode('utf-8'))
        self.ipfs.files_write(
            f'{mfs_head}/commit_metadata', metadata_bytes, create=True, truncate=True)

        return self.ipfs.files_stat(mfs_head)['Hash']

    @atomic
    def uncommit(self):
        # What to do with workspace changes?
        # Ask whether to overwrite or not?
        pass

    @atomic
    def diff(self):
        """ Content diff from head to stage """
        self.common()
        self._notify_pull_merge(self.fs_repo_root, self.active_branch)
        return self._diff(Path('@stage'), Path('@head'), files=False)
