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
        self.print('Found repositories at:')
        for name, h, path in self.repos:
            if name is None:
                self.print(f'{h}: {path}')
            else:
                self.print(f'{name} {h}: {path}')
        return self.repos

    @atomic
    def init(self, name=None):
        """
        Initializes a new repository at the current working directory
        """
        # Create the new repository folder structure
        if self.fs_repo_root is not None:
            if len(str(self.fs_repo_root)) < len(str(self.fs_cwd)):
                self.print_err(f'A repository already exists upstream from here at \
                               {self.fs_repo_root}')
            elif len(str(self.fs_repo_root)) > len(str(self.fs_cwd)):
                self.print_err(f'A repository already exists downstream from here at \
                               {self.fs_repo_root}')
            else:
                self.print_err('A repository already exists here')
            raise RuntimeError()

        # Create empty stage, workspace and head files
        # Note: the reason we do this is so that we have something (an empty
        # folder) to diff against rather than having to handle it as a special case
        for ref in ['stage', 'workspace', 'head']:
            mfs_files = self.get_mfs_path(
                self.fs_cwd, 'master', branch_info=f'{ref}/data/bundle/files')
            self.ipfs.files_mkdir(mfs_files, parents=True)

        if name is None:
            self.print('Initializing unnamed repository')
            self.print('You can use `ipvc repo name <name>` to set name at a later time')
        else:
            self.print(f'Initializing repository with name "{name}"')
            self.set_repo_name(self.fs_cwd, name)

        # Store the active branch name in 'active_branch_name'
        self.set_active_branch(self.fs_cwd, 'master')

        # Write default ipfs id (self)
        self.set_repo_id(self.fs_cwd, 'self')

        # We cache this per repo, because repo_stat() is profoundly slow
        self.print('Getting ipfs repo info (this can be slow...)')
        mfs_ipfs_repo_path = self.get_mfs_path(
            self.fs_cwd, repo_info='ipfs_repo_path')
        ipfs_repo_path = self.ipfs.repo_stat()['RepoPath']
        self.ipfs.files_write(
            mfs_ipfs_repo_path, io.BytesIO(ipfs_repo_path.encode('utf-8')),
            create=True, truncate=True)

        self.print('Reading workspace files')
        self.add_fs_to_mfs(self.fs_repo_root, 'workspace')

        self.print(f'Successfully created repository')
        self.invalidate_cache()
        return True

    @atomic
    def mv(self, path1, path2):
        """ Move a repository from one path to another """
        if path2 is None:
            if self.fs_repo_root is None:
                self.print_err('No ipvc repository here')
                raise RuntimeError()
            path2 = path1
            path1 = self.fs_repo_root
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
    def rm(self, path=None):
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
        self.common()
        if key is not None and key not in self.ipfs_keys():
            self.print_err('No such key')
            self.print_err('Run `ipvc id` to list available keys')
            raise RuntimeError()

        if key is None:
            self.print(f'Key: {self.repo_id}')
            peer_id = self.id_peer_keys(self.repo_id)['peer_id']
            self.print_id(peer_id, self.ids['local'].get(self.repo_id, {}))
        else:
            self.set_repo_id(self.fs_repo_root, key)

    @atomic
    def name(self, name=None):
        """ Get/Set the ID to use for this repo """
        self.common()
        if name is None:
            self.print(self.repo_name)
            return name
        else:
            self.set_repo_name(self.fs_repo_root, name)

    @atomic
    def publish(self, lifetime='8760h'):
        """ Publish repo with a name to IPNS """
        self.common()

        if self.repo_name is None:
            self.print_err(('This repo has no name, set one with '
                           '`ipvc repo name <name>` and publish again'))
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'].get(self.repo_id, {})

        changed = False
        for branch in self.branches:
            changed = changed or self.prepare_publish_branch(
                self.repo_id, branch, self.repo_name)

        if not changed:
            self.print('None of the branches changed since last published')
            return

        self.print((f'Publishing repo with name "{self.repo_name}" to '
                    f'{peer_id} with lifetime {lifetime}'))
        self.publish_ipns(self.repo_id, lifetime)

    @atomic
    def unpublish(self, lifetime='8760h'):
        self.common()

        if self.repo_name is None:
            self.print_err('This repo has not been published')
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'].get(self.repo_id, {})
        mfs_repo_path = self.get_mfs_path(
            ipvc_info=f'published/{self.repo_id}/repos/{self.repo_name}')
        try:
            self.ipfs.files_rm(mfs_repo_path, recursive=True)
        except ipfsapi.exceptions.StatusError:
            self.print_err('This repo has not been published')
            raise RuntimeError()

        self.print(f'Updating IPNS entry for {peer_id} with lifetime {lifetime}')
        self.publish_ipns(self.repo_id, lifetime)

    @atomic
    def remote(self, peer_id, repo_name):
       pass

    @atomic
    def clone(self, remote, as_name=None):
        if self.fs_repo_root is not None:
            self.print_err('There is already a repo here')
            raise RuntimeError()

        try:
            peer_id, peer_repo = remote.split('/')
        except:
            self.print_err('Remote must be on the format "{PeerID}/{repository}')
            raise RuntimeError()
        repo_name = as_name or peer_repo

        if repo_name in self.repos:
            self.print_err(f'You already have a local repo by the name {repo_name}')
            self.print_err(('To clone by a different name, supply it with the '
                           'argument --as-name <name>'))
            raise RuntimeError()

        self.print(f'Resolving name: {peer_id}')
        ipfs_path = None
        try:
            ret = self.ipfs.name_resolve(peer_id)
            ipfs_path = ret['Path']
        except ipfsapi.exceptions.StatusError:
            self.print_err('Could not resolve')
            raise RuntimeError()

        self.print(f'Resolved name to {ipfs_path}')
        self.print('Confirming repository presence')
        ipfs_repos_path = f'{ipfs_path}/repos'
        ipfs_repo_path = f'{ipfs_repos_path}/{repo_name}'
        try:
            remote_repos = self.ipfs.ls(ipfs_repos_path)
            remote_repos = [l['Name'] for l in remote_repos['Objects'][0]['Links']]
        except ipfsapi.exceptions.StatusError:
            self.print_err('Remote IPNS has no {PeerID}/ipvc/repos directory')
            raise RuntimeError()

        try:
            self.ipfs.ls(ipfs_repo_path)
        except ipfsapi.exceptions.StatusError:
            self.print_err(f'Remote has no repo by that name')
            self.print_err(f'Available repos:')
            self.print_err('\n'.join(remote_repos))
            raise RuntimeError()

        repo_hash = self.ipfs.files_stat(ipfs_repo_path)['Hash']

        self.print('Downloading/pinning repo. This might take a while, and there is no '
                   'completion information')
        self.ipfs.pin_add(repo_hash)
        self.print('Download complete, checking out to workspace')

        # Copy repo hash to our mfs repos dir
        mfs_repo_path = self.get_mfs_path(self.fs_cwd)
        try:
            self.ipfs.files_mkdir(mfs_repo_path, parents=True)
        except ipfsapi.exceptions.StatusError:
            pass
        mfs_repo_branches_path = self.get_mfs_path(self.fs_cwd, repo_info='branches')
        for branch_head in self.ipfs.ls(repo_hash)['Objects'][0]['Links']:
            bname = branch_head['Name']
            self.ipfs.files_mkdir(f'{mfs_repo_branches_path}/{bname}', parents=True)
            self.ipfs.files_cp(f'/ipfs/{repo_hash}/{bname}',
                               f'{mfs_repo_branches_path}/{bname}/head')

        self.invalidate_cache()

        # Set the repo name, remote and active branch
        self.set_repo_name(self.fs_repo_root, repo_name)
        self.set_repo_remotes(self.fs_repo_root, remote)

        if len(self.branches) == 0:
            self.print('Cloned repository has no branches')
            return

        branch = 'master' if 'master' in self.branches else self.branches[0]

        self.set_active_branch(self.fs_repo_root, branch)
        self._load_ref_into_repo(self.fs_repo_root, branch, 'head')
