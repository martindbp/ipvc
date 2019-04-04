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
        self.print('Found repositories at:')
        for h, path in repos:
            self.print(f'{h}: {path}')
        return repos

    @atomic
    def init(self, path=None):
        """
        Initializes a new repository at the current working directory
        """
        path = path or self.fs_cwd
        # Create the new repository folder structure
        fs_repo_root = self.get_repo_root(path)
        if fs_repo_root is not None:
            if len(str(fs_repo_root)) < len(str(path)):
                self.print_err(f'A repository already exists upstream from here at \
                               {fs_repo_root}')
            elif len(str(fs_repo_root)) > len(str(path)):
                self.print_err(f'A repository already exists downstream from here at \
                               {fs_repo_root}')
            else:
                self.print_err('A repository already exists here')
            raise RuntimeError()

        # Create empty stage, workspace and head files
        # Note: the reason we do this is so that we have something (an empty
        # folder) to diff against rather than having to handle it as a special case
        for ref in ['stage', 'workspace', 'head']:
            mfs_files = self.get_mfs_path(
                path, 'master', branch_info=f'{ref}/data/bundle/files')
            self.ipfs.files_mkdir(mfs_files, parents=True)

        # Store the active branch name in 'active_branch_name'
        active_branch_path = self.get_mfs_path(
            path, repo_info='active_branch_name')
        self.ipfs.files_write(
            active_branch_path, io.BytesIO(b'master'), create=True, truncate=True)
        self.invalidate_cache()

        # Write default ipfs id (self)
        self.ipfs.files_write(self.get_mfs_path(path, repo_info='id'),
                              io.BytesIO(b'self'), create=True, truncate=True)

        # We cache this per repo, because repo_stat() is profoundly slow
        self.print('Getting ipfs repo info (this can be slow...)')
        mfs_ipfs_repo_path = self.get_mfs_path(
            path, repo_info='ipfs_repo_path')
        ipfs_repo_path = self.ipfs.repo_stat()['RepoPath']
        self.ipfs.files_write(
            mfs_ipfs_repo_path, io.BytesIO(ipfs_repo_path.encode('utf-8')),
            create=True, truncate=True)

        self.print('Reading workspace files')
        self.update_mfs_repo()

        self.print(f'Successfully created repository')
        return True

    @atomic
    def mv(self, path1, path2):
        """ Move a repository from one path to another """
        if path2 is None:
            fs_repo_root = self.get_repo_root()
            if fs_repo_root is None:
                self.print_err('No ipvc repository here')
                raise RuntimeError()
            path2 = path1
            path1 = fs_repo_root
        else:
            path1 = self.get_repo_root(path1)
            if path1 is None:
                self.print_err(f'No ipvc repository at {path1}')
                raise RuntimeError()

        if self.get_repo_root(path2) is not None:
            self.print_err(f'There is already a repository above or below {path2}')
            raise RuntimeError()

        try:
            shutil.move(path1, path2)
        except:
            self.print_err(f'Unable to move directory to {path2}')
            raise RuntimeError()

        self.ipfs.files_cp(self.get_mfs_path(path1), self.get_mfs_path(path2))
        self.ipfs.files_rm(self.get_mfs_path(path1), recursive=True)
        self.invalidate_cache()
        return True

    @atomic
    def rm(self, path):
        """ Remove a repository at a given path"""
        fs_repo_root = self.get_repo_root(path)

        if fs_repo_root is None:
            if path is None:
                self.print_err('No ipvc repository here')
            else:
                self.print_err(f'No ipvc repository at {path}')
            raise RuntimeError()

        mfs_repo_root = self.get_mfs_path(fs_repo_root)
        h = self.ipfs.files_stat(mfs_repo_root)['Hash']
        self.ipfs.files_rm(mfs_repo_root, recursive=True)
        self.invalidate_cache()
        self.print('Repository successfully removed')
        return True

    @atomic
    def id(self, key=None):
        """ Get/Set the ID to use for this repo """
        fs_repo_root , _  = self.common()
        if key is not None and key not in self.all_ipfs_ids():
            self.print_err('No such key')
            self.print_err('Run `ipvc id` to list available keys')
            raise RuntimeError()

        if key is None:
            self.print(f'Key: {self.repo_id}')
            peer_id = self.id_peer_keys(self.repo_id)['peer_id']
            self.print_id(peer_id, self.ids['local'].get(self.repo_id, {}))
        else:
            mfs_id_path = self.get_mfs_path(fs_repo_root, repo_info='id')
            self.ipfs.files_write(mfs_id_path, io.BytesIO(key.encode('utf-8')),
                                  create=True, truncate=True)
            self.invalidate_cache(['repo_id', 'ids'])

    @atomic
    def name(self, name=None):
        """ Get/Set the ID to use for this repo """
        fs_repo_root , _  = self.common()
        if name is None:
            self.print(self.repo_name)
        else:
            mfs_repo_namepath = self.get_mfs_path(fs_repo_root, repo_info='name')
            self.ipfs.files_write(mfs_repo_namepath, io.BytesIO(name.encode('utf-8')),
                                  create=True, truncate=True)

    @atomic
    def publish(self, lifetime='8760h'):
        """ Publish repo with a name to IPNS """
        self.common()

        if self.repo_name is None:
            self.print_err(('This repo has no name, set one with '
                           '`ipvc repo name <name>` and publish again'))
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'][self.repo_id]
        self.print(f'Publishing repo with name "{self.repo_name}" to {peer_id}')

        mfs_repo_path = self.get_mfs_path(
            ipvc_info=f'published/{self.repo_id}/repos/{self.repo_name}')
        try:
            self.ipfs.files_rm(mfs_repo_path, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass

        changed = False
        for branch in self.branches:
            changed = changed or self.prepare_publish_branch(
                self.repo_id, branch, self.repo_name)

        if not changed:
            self.print('None of the branches changed since last published')
            return

        self.publish_ipns(self.repo_id, lifetime)

    @atomic
    def unpublish(self, lifetime='8760h'):
        self.common()

        if self.repo_name is None:
            self.print_err('This repo has not been published')
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'][self.repo_id]
        mfs_repo_path = self.get_mfs_path(
            ipvc_info=f'published/{self.repo_id}/repos/{self.repo_name}')
        try:
            self.ipfs.files_rm(mfs_repo_path, recursive=True)
        except ipfsapi.exceptions.StatusError:
            self.print_err('This repo has not been published')
            raise RuntimeError()

        self.print(f'Updating IPNS entry for {peer_id}')
        self.publish_ipns(self.repo_id, lifetime)
