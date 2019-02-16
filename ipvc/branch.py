import io
import os
import sys
import json
import difflib
import webbrowser
from pathlib import Path

import ipfsapi
from ipvc.common import CommonAPI, expand_ref, make_len, atomic

class BranchAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def status(self, name=False):
        _, branch = self.common()
        active = self.ipfs.files_read(
            self.get_mfs_path(self.fs_cwd, repo_info='active_branch_name')).decode('utf-8')
        if not self.quiet: print(active)
        return active

    @atomic
    def create(self, name, from_commit="@head", no_checkout=False):
        self._branches = None
        _, branch = self.common()

        if not name.replace('_', '').isalnum():
            if not self.quiet:
                print('Branch name has to be alpha numeric with underscores',
                      file=sys.stderr)
            raise RuntimeError()
        elif name in ['head', 'workspace', 'stage']:
            if not self.quiet:
                print(f'"{name}" is a reserved keyword, please pick a different branch name',
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

            # Copy commit bundle to workspace and stage
            mfs_commit_bundle_path = f'{mfs_commit_path}/bundle'
            mfs_workspace_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='workspace/bundle')
            mfs_stage_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='stage/bundle')
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_workspace_path)
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_stage_path)

        if not no_checkout:
            self.checkout(name)

    def _load_ref_into_repo(self, fs_repo_root, branch, ref,
                            without_timestamps=False):
        """ Syncs the fs workspace with the files in ref """
        files_metadata = self.read_files_metadata(ref)
        added, removed, modified = self.workspace_changes(
            fs_repo_root, fs_repo_root, files_metadata, update_meta=False)

        _, mfs_refpath, _ = self.refpath_to_mfs(Path(f'@{ref}'))

        for path in added:
            os.remove(fs_repo_root / path)

        for path in removed | modified:
            mfs_path = self.get_mfs_path(
                fs_repo_root, branch,
                branch_info=(mfs_refpath / path))

            timestamp = files_metadata[str(path)]['timestamp']

            with open(fs_repo_root / path, 'wb') as f:
                f.write(self.ipfs.files_read(mfs_path))

            os.utime(fs_repo_root / path, ns=(timestamp, timestamp))

    @atomic
    def checkout(self, name, without_timestamps=False):
        """ Checks out a branch"""
        self._branches = None
        fs_repo_root, _ = self.common()

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

        self._load_ref_into_repo(
            fs_repo_root, name, 'workspace', without_timestamps)

    def get_commit_parents(self, commit_hash):
        """ Returns hash and metadata of parent commit and merge parent (if present) """
        try:
            parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/parent')['Hash']
            parent_metadata = self.get_commit_metadata(commit_hash)
        except ipfsapi.exceptions.StatusError:
            # Reached the root of the graph
            return None, None, None, None

        try:
            merge_parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/merge_parent')['Hash']
            merge_parent_metadata = self.get_commit_metadata(commit_hash)
            return parent_hash, parent_metadata, merge_parent_hash, merge_parent_metadata
        except:
            return parent_hash, parent_metadata, None, None

    def get_commit_metadata(self, commit_hash):
        # NOTE: the root commit doesn't have a commit_metadata file, so this
        # might fail
        return json.loads(self.ipfs.cat(f'/ipfs/{commit_hash}/commit_metadata').decode('utf-8'))

    @atomic
    def history(self, show_hash=False):
        """ Shows the commit history for the current branch. Currently only shows
        the linear history on the first parents side"""
        fs_repo_root, branch = self.common()

        # Traverse the commits backwards by via the {commit}/parent/ link
        mfs_commit_path = self.get_mfs_path(
            fs_repo_root, branch, branch_info=Path('head'))
        commit_hash = self.ipfs.files_stat(
            mfs_commit_path)['Hash']
        commit_metadata = self.get_commit_metadata(commit_hash)

        commits = []
        while True:
            h, ts, msg = commit_hash[:6], commit_metadata['timestamp'], commit_metadata['message']
            auth = make_len(commit_metadata['author'] or '', 30)
            if not self.quiet: 
                if show_hash:
                    print(f'* {commit_hash} {ts} {auth}   {msg}')
                else:
                    print(f'* {ts} {auth}   {msg}')

            parent_hash, parent_metadata, merge_parent_hash, _ = self.get_commit_parents(commit_hash)

            commit_hash = parent_hash
            if commit_hash is None:
                # Reached the root
                break

            commits.append((commit_hash, parent_hash, merge_parent_hash))

        return commits

    @atomic
    def pull(self, their_branch=None, replay=False, abort=False):
        """ Pulls changes from `their_branch` since the last common parent
        By default, tries to merge the two branches and create a merge commit.
        If replay is True, then try to "replay" the commits from `their_branch`
        onto our branch without creating a merge commit.

        For a merge, this is the general procedure:
        1. Get the commits hashes for our branch and `their_branch`
        2. Find the lowest common ancestor of the two commits
        3. Find the diff between LCA and both commits
        4. If diff doesn't conflict, apply, otherwise give user option to either:
            1. Keep "ours", "theirs", or "manual editing"

        For replaying commits, the procedure is:
        1. Create a new temporary branch from the their branch
        2. Find LCA as with merge
        3. Now instead of finding the diff for all the changes in both commits,
           we first find the diff for the whole their branch, but then we find
           the diff for one commit at a time in our branch.
        4. For each such commit, if it can be applied without conflict, then apply it
           otherwise, ask user same as in step 4 of merge
        5. If manual editing is picked, we pause the replay until user has edited
           files and resumed
        """
        # TODO: implement fast-forward merges
        fs_repo_root, branch = self.common()

        mfs_merge_parent = self.get_mfs_path(fs_repo_root, branch, branch_info='merge_parent')
        mfs_merge_stage_backup = self.get_mfs_path(
            fs_repo_root, branch, branch_info='merge_stage_backup')
        mfs_merge_workspace_backup = self.get_mfs_path(
            fs_repo_root, branch, branch_info='merge_workspace_backup')

        if abort:
            try:
                # Check that merge_parent is there, otherwise it will raise
                self.ipfs.files_rm(mfs_merge_parent, recursive=True)
            except:
                print('There is no pull merge in progress', file=sys.stderr)
                raise RuntimeError()

            # Reset workspace and stage
            mfs_stage = self.get_mfs_path(fs_repo_root, branch, branch_info='stage')
            self.ipfs.files_rm(mfs_stage, recursive=True)
            self.ipfs.files_cp(
                mfs_merge_stage_backup,
                mfs_stage)
            mfs_workspace = self.get_mfs_path(fs_repo_root, branch, branch_info='workspace')
            self.ipfs.files_rm(mfs_workspace, recursive=True)
            self.ipfs.files_cp(
                mfs_merge_workspace_backup,
                mfs_workspace)
            # Load the workspace backup back into the repo
            self._load_ref_into_repo(
                fs_repo_root, branch, 'workspace')

            # Remove backups
            self.ipfs.files_rm(mfs_merge_stage_backup, recursive=True)
            self.ipfs.files_rm(mfs_merge_workspace_backup, recursive=True)
            return

        our_commit_hash = self.get_branch_info_hash(branch, 'head')
        our_workspace_hash = self.get_branch_info_hash(branch, 'workspace')
        our_stage_hash = self.get_branch_info_hash(branch, 'stage')
        their_commit_hash = self.get_branch_info_hash(their_branch, 'head')

        # Find the Lowest Common Ancestor
        curr_our_hash = our_commit_hash
        curr_their_hash = their_commit_hash
        our_set = set([curr_our_hash])
        their_set = set([curr_their_hash])
        while curr_our_hash not in their_set and curr_their_hash not in our_set:
            curr_our_hash, *_ = self.get_commit_parents(curr_our_hash)
            curr_their_hash, *_ = self.get_commit_parents(curr_their_hash)
            our_set.add(curr_our_hash)
            their_set.add(curr_their_hash)
            if curr_our_hash is None or curr_their_hash is None:
                # Reached the root in one of the branches
                break

        lca_commit_hash = None
        if curr_our_hash in their_set: lca_commit_hash = curr_our_hash
        if curr_their_hash in our_set: lca_commit_hash = curr_their_hash

        def _fdiff(change):
            from_lines = (self.ipfs.cat(change['Before']['/']).decode('utf-8').split('\n')
                          if change['Before'] is not None else [])
            to_lines = (self.ipfs.cat(change['After']['/']).decode('utf-8').split('\n')
                        if change['After'] is not None else [])
            return difflib.ndiff(from_lines, to_lines)

        lca_files_hash = self.ipfs.files_stat(f'/ipfs/{lca_commit_hash}/bundle/files')['Hash']
        def _get_file_changes(files_hash, from_hash=lca_files_hash):
            changes = self.ipfs_object_diff(from_hash, files_hash)['Changes']
            return {change['Path']: change for change in changes}

        our_files_hash = self.ipfs.files_stat(f'/ipfs/{our_commit_hash}/bundle/files')['Hash']
        our_workspace_files_hash = self.ipfs.files_stat(f'/ipfs/{our_workspace_hash}/bundle/files')['Hash']
        our_stage_files_hash = self.ipfs.files_stat(f'/ipfs/{our_stage_hash}/bundle/files')['Hash']
        their_files_hash = self.ipfs.files_stat(f'/ipfs/{their_commit_hash}/bundle/files')['Hash']
        if replay is False:
            # Check collisions with stage and workspace changes
            # NOTE: Check staged changes first since workspace contains changes based
            # on the staged changes
            our_workspace_file_changes = _get_file_changes(our_workspace_files_hash, our_files_hash)
            our_stage_file_changes = _get_file_changes(our_stage_files_hash, our_files_hash)
            their_file_changes = _get_file_changes(their_files_hash)
            stage_conflict_set = our_stage_file_changes.keys() & their_file_changes.keys()
            if len(stage_conflict_set) > 0:
                print('Pull conflicts with local staged changes in:', file=sys.stderr)
                print('\n'.join(list(stage_conflict_set)), file=sys.stderr)
                raise RuntimeError()
            workspace_conflict_set = our_workspace_file_changes.keys() & their_file_changes.keys()
            if len(workspace_conflict_set) > 0:
                print('Pull conflicts with local workspace changes in:', file=sys.stderr)
                print('\n'.join(list(workspace_conflict_set)), file=sys.stderr)
                raise RuntimeError()

            our_file_changes = _get_file_changes(our_files_hash)

            merged_files, conflict_files, pulled_files = set(), set(), set()
            for filename, their_change in their_file_changes.items():
                has_merge_conflict, has_merges = False, False
                if filename not in our_file_changes:
                    # Write the file from their change
                    with open(fs_repo_root / filename, 'wb') as f:
                        f.write(self.ipfs.cat(f'/ipfs/{their_files_hash}/{filename}'))
                else:
                    our_change = our_file_changes[filename]
                    our_diff = list(_fdiff(our_change))
                    their_diff = list(_fdiff(their_change))
                    diff_diff = list(difflib.ndiff(our_diff, their_diff))
                    diff_diff = [l for l in diff_diff if not l.startswith('?')]
                    lines_in, lines_out = [], []
                    f = open(fs_repo_root / filename, 'w')
                    for line in diff_diff:
                        if line.startswith(' '):
                            if  len(lines_out) > 0 and len(lines_in) > 0:
                                has_merge_conflict = True
                                f.write('>>>>>>> ours\n')
                                f.write('\n'.join(lines_out) + '\n')
                                f.write('======= theirs\n')
                                f.write('\n'.join(lines_in) + '\n')
                                f.write('<<<<<<<\n')
                            else:
                                # NOTE: one of lines_out/in will be empty
                                for l in lines_in + lines_out:
                                    f.write(l + '\n')
                                has_merges = True
                            lines_in, lines_out = [], []
                            f.write(line[4:] + '\n')
                        else:
                            if line.startswith('+ + ') or line.startswith('+   '):
                                # Difflines that start with + come in from their commit,
                                # use only the ones starting with + or space, meaning they
                                # were added or unmodified
                                lines_in.append(line[4:])
                            elif line.startswith('- + ') or line.startswith('-   '):
                                # Similarly, the lines coming from our commit are the
                                # ones removed in the diff (leading minus), but present
                                # in the original diff (+ or space)
                                lines_out.append(line[4:])

                    # Write the left over lines if there are any
                    for l in lines_in + lines_out:
                        f.write(l + '\n')
                    f.close()

                if not has_merge_conflict:
                    # Add the file to workspace, and then to stage
                    self.add_fs_to_mfs(fs_repo_root / filename, 'workspace')
                    self.add_ref_changes_to_ref('workspace', 'stage', filename)

                if has_merge_conflict:
                    print(f'Merge conflict in {filename}')
                    conflict_files.add(filename)
                elif has_merges:
                    print(f'Successfully merged {filename}')
                    merged_files.add(filename)
                else:
                    pulled_files.add(filename)

            if len(conflict_files) > 0:
                print(('Pull produced merge conflicts. Edit the conflicts and '
                       'commit, or run `ipvc branch pull --abort` to abort'))
            else:
                print(('Pull merge successful. Commit with a merge message or '
                       'run `ipvc branch pull --abort` to abort'))

            # Save their commit as the merge_parent
            self.ipfs.files_cp(f'/ipfs/{their_commit_hash}', mfs_merge_parent)
            # Save backup of previous stage and workspace
            self.ipfs.files_cp(f'/ipfs/{our_workspace_hash}', mfs_merge_workspace_backup)
            self.ipfs.files_cp(f'/ipfs/{our_stage_hash}', mfs_merge_stage_backup)

            return pulled_files, merged_files, conflict_files
        else:
            pass


    @atomic
    def show(self, refpath, browser=False):
        """ Opens a ref in the ipfs file browser """
        commit_files_hash = self.get_refpath_files_hash(refpath)
        if browser:
            # TODO: read IPFS node url from settings
            url = f'http://localhost:8080/ipfs/{commit_files_hash}'
            if not self.quiet: print(f'Opening {url}')
            webbrowser.open(url)
        else:
            ret = self.ipfs.ls(f'/ipfs/{commit_files_hash}')
            obj = ret['Objects'][0]
            if len(obj['Links']) == 0:
                # It's a file, so cat it
                cat = self.ipfs.cat(f'/ipfs/{commit_files_hash}').decode('utf-8')
                if not self.quiet:
                    print(cat)
                return cat
            else:
                # It's a folder
                ls = '\n'.join([ln['Name'] for ln in obj['Links']])
                if not self.quiet:
                    print(ls)
                return ls

    @atomic
    def ls(self):
        """ List branches """
        if not self.quiet:
            print('\n'.join(self.branches))
        return self.branches

    @atomic
    def rm(self):
        self._branches = None

    @atomic
    def mv(self):
        self._branches = None


