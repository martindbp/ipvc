import os
import io
import json
import sys
import difflib
from pathlib import Path
from datetime import datetime

import ipfsapi
from ipvc.common import CommonAPI, refpath_to_mfs, print_changes, atomic


class StageAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _get_relative_paths(self, fs_paths, fs_workspace_root):
        fs_paths = fs_paths if isinstance(fs_paths, list) else [fs_paths]
        for fs_path in fs_paths:
            fs_path = Path(os.path.abspath(fs_path))
            try: 
                yield fs_path.relative_to(fs_workspace_root)
            except:
                # Doesn't start with workspace_root
                if not self.quiet:
                    print(f'Path outside workspace {fs_path}', file=sys.stderr)
                raise

    @atomic
    def add(self, fs_paths=None):
        """ Add the path to ipfs, and replace the stage files at that path with
        the new hash.
        """
        fs_workspace_root, branch = self.common()
        fs_paths = self.fs_cwd if fs_paths is None else fs_paths
        changes = []
        for fs_path_relative in self._get_relative_paths(fs_paths, fs_workspace_root):
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
        fs_workspace_root, branch = self.common()
        changes = []
        for fs_path_relative in self._get_relative_paths(fs_paths, fs_workspace_root):
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
        fs_workspace_root, branch = self.common()

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
        """ Create a new commit object, and point head to it """
        fs_workspace_root, branch = self.common()

        mfs_head = self.get_mfs_path(fs_workspace_root, branch, branch_info='head')
        mfs_stage = self.get_mfs_path(fs_workspace_root, branch, branch_info='stage')
        head_hash = self.ipfs.files_stat(mfs_head)['Hash']

        # Set head to stage
        try:
            self.ipfs.files_rm(mfs_head, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass
        self.ipfs.files_cp(mfs_stage, mfs_head)

        # Add parent1 pointer to previous head
        self.ipfs.files_cp(f'/ipfs/{head_hash}', f'{mfs_head}/parent1')

        # Add metadata
        params = self.read_global_params()
        metadata = {
            'message': message,
            'author': params.get('author', None),
            'timestamp': datetime.utcnow().isoformat()
        }

        metadata_bytes = io.BytesIO(json.dumps(metadata).encode('utf-8'))
        self.ipfs.files_write(
            f'{mfs_head}/metadata', metadata_bytes, create=True, truncate=True)

        return True

    @atomic
    def uncommit(self):
        # What to do with workspace changes?
        # Ask whether to overwrite or not?
        pass

    @atomic
    def diff(self):
        """ Content diff from head to stage """
        fs_workspace_root, branch = self.common()

        mfs_from_refpath, _ = refpath_to_mfs(Path("@head"))
        mfs_to_refpath, _ = refpath_to_mfs(Path("@stage"))
        changes, *_ = self.get_mfs_changes(
            mfs_from_refpath, mfs_to_refpath)
        for change in changes:
            if change['Type'] != 2:
                continue # only show modifications
            file1 = self.ipfs.cat(change['Before']['/']).decode('utf-8').split('\n')
            file2 = self.ipfs.cat(change['After']['/']).decode('utf-8').split('\n')
            diff = difflib.unified_diff(file1, file2, lineterm='')
            if not self.quiet:
                print('\n'.join(list(diff)[:-1]))

        return changes
