import io
import sys
import shutil

import ipfsapi
from ipvc.common import CommonAPI, atomic

class RepoAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def ls(self):
        """
        Lists all the repositories on the connected ipfs node MFS
        """
        repos = list(self.list_repo_paths())
        if not self.quiet:
            print('Found repositories at:')
            for h, path in repos:
                print(f'{h}: {path}')
        return repos

    @atomic
    def init(self):
        """
        Initializes a new repository at the current working directory
        """
        # Create the new repository folder structure
        fs_workspace_root = self.get_workspace_root()
        if fs_workspace_root is not None:
            if self.quiet:
                raise RuntimeError()

            if len(str(fs_workspace_root)) < len(str(self.fs_cwd)):
                print(f'A repository already exists upstream from here at \
                      {fs_workspace_root}', file=sys.stderr)
            elif len(str(fs_workspace_root)) > len(str(self.fs_cwd)):
                print(f'A repository already exists downstream from here at \
                      {fs_workspace_root}', file=sys.stderr)
            else:
                print('A repository already exists here', file=sys.stderr)
            raise RuntimeError()

        # Create empty stage, workspace and head files
        # Note: the reason we do this is so that we have something (an empty
        # folder) to diff against rather than having to handle it as a special case
        for ref in ['stage', 'workspace', 'head']:
            mfs_files = self.get_mfs_path(
                self.fs_cwd, 'master', branch_info=f'{ref}/bundle/files')
            self.ipfs.files_mkdir(mfs_files, parents=True)

        # Store the active branch name in 'active_branch_name'
        active_branch_path = self.get_mfs_path(
            self.fs_cwd, repo_info='active_branch_name')
        self.ipfs.files_write(
            active_branch_path, io.BytesIO(b'master'), create=True, truncate=True)

        self.update_mfs_workspace()

        if not self.quiet: print(f'Successfully created repository')
        return True

    @atomic
    def mv(self, path1, path2):
        """ Move a repository from one path to another """
        if path2 is None:
            fs_workspace_root = self.get_workspace_root()
            if fs_workspace_root is None:
                if not self.quiet:
                    print('No ipvc repository here', file=sys.stderr)
                raise RuntimeError()
            path2 = path1
            path1 = fs_workspace_root
        else:
            path1 = self.get_workspace_root(path1)
            if path1 is None:
                if not self.quiet:
                    print(f'No ipvc repository at {path1}', file=sys.stderr)
                raise RuntimeError()

        if self.get_workspace_root(path2) is not None:
            if not self.quiet:
                print(f'There is already a repository above or below {path2}',
                      file=sys.stderr)
            raise RuntimeError()

        try:
            shutil.move(path1, path2)
        except:
            if not self.quiet:
                print(f'Unable to move directory to {path2}', file=sys.stderr)
            raise RuntimeError()

        self.ipfs.files_cp(self.get_mfs_path(path1), self.get_mfs_path(path2))
        self.ipfs.files_rm(self.get_mfs_path(path1), recursive=True)
        return True

    @atomic
    def rm(self, path):
        """ Remove a repository at a given path"""
        fs_workspace_root = self.get_workspace_root(path)

        if fs_workspace_root is None:
            if not self.quiet:
                if path is None:
                    print('No ipvc repository here', file=sys.stderr)
                else:
                    print(f'No ipvc repository at {path}', file=sys.stderr)
            raise RuntimeError()

        mfs_workspace_root = self.get_mfs_path(fs_workspace_root)
        h = self.ipfs.files_stat(mfs_workspace_root)['Hash']
        self.ipfs.files_rm(mfs_workspace_root, recursive=True)
        print(f'Repository with hash {h} removed')
        return True
