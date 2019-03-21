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
        self.common()
        self.print(self.active_branch)
        return self.active_branch

    @atomic
    def create(self, name, from_commit="@head", no_checkout=False):
        self.common()
        if not name.replace('_', '').isalnum():
            self.print_err('Branch name has to be alpha numeric with underscores')
            raise RuntimeError()
        elif name in ['head', 'workspace', 'stage']:
            self.print_err(f'"{name}" is a reserved keyword, please pick a different branch name')
            raise RuntimeError()


        try:
            self.ipfs.files_stat(self.get_mfs_path(self.fs_cwd, name))
            self.print_err('Branch name already exists')
            raise RuntimeError()
        except ipfsapi.exceptions.StatusError:
            pass

        if from_commit == "@head":
            # Simply copy the current branch to the new branch
            self.ipfs.files_cp(
                self.get_mfs_path(self.fs_cwd, self.active_branch),
                self.get_mfs_path(self.fs_cwd, name))
            self.invalidate_cache(['branches'])
        else:
            # Create the branch directory along with an empty stage and workspace
            for ref in ['stage', 'workspace']:
                mfs_ref = self.get_mfs_path(self.fs_cwd, name, branch_info=ref)
                self.ipfs.files_mkdir(mfs_ref, parents=True)
            self.invalidate_cache(['branches'])

            # Copy the commit to the new branch's head
            _, commit_path = expand_ref(from_commit)
            mfs_commit_path = self.get_mfs_path(
                self.fs_cwd, self.active_branch, branch_info=commit_path)
            mfs_head_path = self.get_mfs_path(
                self.fs_cwd, name, branch_info='head')

            try:
                self.ipfs.files_stat(mfs_commit_path)
            except ipfsapi.exceptions.StatusError:
                self.print_err('No such commit')
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
        self.common()

        try:
            self.ipfs.files_stat(self.get_mfs_path(self.fs_cwd, name))
        except ipfsapi.exceptions.StatusError:
            self.print_err('No branch by that name exists')
            raise RuntimeError()

        # Write the new branch name to active_branch_name
        # NOTE: truncate here is needed to clear the file before writing
        self.ipfs.files_write(
            self.get_mfs_path(self.fs_cwd, repo_info='active_branch_name'),
            io.BytesIO(bytes(name, 'utf-8')),
            create=True, truncate=True)
        self.invalidate_cache(['active_branch'])

        self._load_ref_into_repo(
            self.fs_repo_root, name, 'workspace', without_timestamps)

    def _get_commit_parents(self, commit_hash):
        """ Returns hash and metadata of parent commit and merge parent (if present) """
        try:
            parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/parent')['Hash']
            parent_metadata = self.get_commit_metadata(parent_hash)
        except ipfsapi.exceptions.StatusError:
            # Reached the root of the graph
            return None, None, None, None

        try:
            merge_parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/merge_parent')['Hash']
            merge_parent_metadata = self.get_commit_metadata(merge_parent_hash)
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
        the linear history on the first parents side
        Returns list of commits in order from last to first, as a tuple
        of commit hash, parent hash and merge parent hash
        """
        self.common()

        # Traverse the commits backwards by via the {commit}/parent/ link
        mfs_commit_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=Path('head'))
        commit_hash = self.ipfs.files_stat(
            mfs_commit_path)['Hash']
        commit_metadata = self.get_commit_metadata(commit_hash)

        commits = []
        while True:
            h, ts, msg = commit_hash[:6], commit_metadata['timestamp'], commit_metadata['message']
            auth = make_len(commit_metadata['author'] or '', 30)
            if show_hash:
                self.print(f'* {commit_hash} {ts} {auth}   {msg}')
            else:
                self.print(f'* {ts} {auth}   {msg}')

            parent_hash, parent_metadata, merge_parent_hash, _ = self._get_commit_parents(commit_hash)
            commits.append((commit_hash, parent_hash, merge_parent_hash))
            if parent_hash is None:
                # Reached the root
                break

            commit_hash, commit_metadata = parent_hash, parent_metadata

        return commits

    def _find_LCA(self, our_commit_hash, their_commit_hash):
        """
        Finds the Lowest Common Ancestor to `our_commit_hash` and `their_commit_hash`.
        Returns the LCA commit hash, and the list of our commits and their commits
        on the path back to (and including) the LCA.

        Implementation details:
        Do breadth first search from our and their commits simultaneously
        to reduce number of requests to IPFS
        """
        our_commits = [our_commit_hash]
        their_commits = [their_commit_hash]
        our_queue, their_queue = [our_commit_hash], [their_commit_hash]
        while len(set(our_commits) & set(their_commits)) == 0:
            our_hash, their_hash = our_queue.pop(), their_queue.pop()
            our_parent, _, our_merge_parent, _ = self._get_commit_parents(our_hash)
            their_parent, _, their_merge_parent, _ = self._get_commit_parents(their_hash)
            for h in [our_parent, our_merge_parent]:
                if h is not None:
                    our_commits.append(h)
                    our_queue.append(h)
            for h in [their_parent, their_merge_parent]:
                if h is not None:
                    their_commits.append(h)
                    their_queue.append(h)
            if our_hash is None or their_hash is None:
                # Reached the root in one of the branches
                break

        # Take the intersection and pop (should only have one hash)
        lca = (set(our_commits) & set(their_commits)).pop()
        return lca, our_commits, their_commits

    def _get_file_changes(self, from_hash, to_hash):
        changes = self.ipfs.object_diff(from_hash, to_hash)['Changes']
        return {change['Path']: change for change in changes}

    def _merge(self, our_file_changes, their_file_changes, their_files_hash):
        """
        Takes changes from `their_file_changes` and merges them with `our_file_changes`,
        and writes the merged files to disk, with conflict markers if there are conflicts,
        and then stage changes that are conflict free.
        Assumes that current fs repo has 'our_file_changes' in it already.
        """
        def _fdiff(change):
            # NOTE: remove the last lines because text files always end with
            # a newline, so it would introduce a new empty line at the end
            from_lines = (self.ipfs.cat(change['Before']['/']).decode('utf-8').split('\n')[:-1]
                          if change['Before'] is not None else [])
            to_lines = (self.ipfs.cat(change['After']['/']).decode('utf-8').split('\n')[:-1]
                        if change['After'] is not None else [])
            return difflib.ndiff(from_lines, to_lines)

        merged_files, conflict_files, pulled_files = set(), set(), set()
        for filename, their_change in their_file_changes.items():
            has_merge_conflict, has_merges = False, False
            if filename not in our_file_changes:
                # Write the file from their change
                with open(self.fs_repo_root / filename, 'wb') as f:
                    f.write(self.ipfs.cat(f'/ipfs/{their_files_hash}/{filename}'))
            else:
                our_change = our_file_changes[filename]
                our_diff = list(_fdiff(our_change))
                their_diff = list(_fdiff(their_change))
                diff_diff = list(difflib.ndiff(our_diff, their_diff))
                diff_diff = [l for l in diff_diff if not l.startswith('?')]
                their_lines, our_lines, both_lines = [], [], []
                f = open(self.fs_repo_root / filename, 'w')

                # Add a sentinel value so that we spit out any conflicts that
                # are left
                diff_diff = diff_diff + ['    ']

                # Lines start with two signs, each of which can be +, - or space
                # Let's enumerate the 9 possibilities:
                # * First sign is
                #   1. space: both diffs has this diff-line
                #       * The second sign is:
                #           1. space: line was unmodified in *both* commits
                #           2. +: line was added in *both* commits
                #           3. -: line was removed in *both* commits
                #   2. +: this diff-line appears only in *their* commit
                #           1. space: line was unmodified in *their* commit
                #           2. +: line was added in *their* commits
                #           3. -: line was removed in *their* commits
                #   3. -: this diff-line appears only in *our* commit
                #           1. space: line was unmodified in *our* commits
                #           2. +: line was added in *our* commits
                #           3. -: line was removed in *our* commits
                # We keep track of lines that are added by either commit or
                # lines that stay the same in both, then output conflicts between
                # "stable" lines where there are different lines coming from both commits

                for line in diff_diff:
                    if line.startswith('    '):
                        if  len(our_lines) > 0 and len(their_lines) > 0:
                            has_merge_conflict = True
                            f.write('>>>>>>> ours\n')
                            f.write('\n'.join(our_lines) + '\n')
                            f.write('======= theirs\n')
                            f.write('\n'.join(their_lines) + '\n')
                            f.write('<<<<<<<\n')
                        else:
                            for l in their_lines + our_lines + both_lines:
                                f.write(l + '\n')
                            has_merges = True
                        their_lines, our_lines, both_lines = [], [], []

                        if line == '    ':
                            # It's the sentinel value
                            break
                        else:
                            f.write(line[4:] + '\n')
                    else:
                        if line.startswith('+ + ') or line.startswith('+   '):
                            # Difflines that start with + come in from their commit,
                            # use only the ones starting with + or space, meaning they
                            # were added or unmodified
                            their_lines.append(line[4:])
                        elif line.startswith('- + ') or line.startswith('-   '):
                            # Similarly, the lines coming from our commit are the
                            # ones removed in the diff (leading minus), but present
                            # in the original diff (+ or space)
                            our_lines.append(line[4:])
                        elif line.startswith('  + '):
                            # These are lines that both ours and theirs added
                            both_lines.append(line[4:])
                        elif line.startswith('  - '):
                            # These are lines that were removed in both ours and theirs,
                            # so do nothing (don't keep them)
                            pass

                f.close()

            if not has_merge_conflict:
                # Add the file to workspace, and then to stage
                self.add_fs_to_mfs(self.fs_repo_root / filename, 'workspace')
                self.add_ref_changes_to_ref('workspace', 'stage', filename)

            if has_merge_conflict:
                self.print(f'Merge conflict in {filename}')
                conflict_files.add(filename)
            elif has_merges:
                self.print(f'Successfully merged {filename}')
                merged_files.add(filename)
            else:
                pulled_files.add(filename)

        return merged_files, conflict_files, pulled_files

    @atomic
    def pull(self, their_branch=None, replay=False, no_fast_forward=False,
             abort=False, resume=False):
        """ Pulls changes from `their_branch` since the last common parent
        By default, tries to merge the two branches and create a merge commit.
        If replay is True, then try to "replay" the commits from our branch
        onto their branch without creating a merge commit.

        For replay, the reason we apply our commits on top of their branch is because then
        "they" can simply do a fast-forward merge with our branch, but if we do it
        the other way around they have to erase their branch and checkout ours completely.

        For a merge, this is the general procedure:
        1. Get the commits hashes for our branch and `their_branch`
        2. Find the lowest common ancestor of the two commits
        3. Find the diff between LCA and both commits
        4. If diffs don't conflict, apply, otherwise give user option to either:
            1. Keep "ours", "theirs", or "manual editing"

        For re-applying commits, the procedure is:
        1. Find LCA as with merge
        2. Now instead of finding the diff for all the changes in both commits,
           we first find the diff for the whole their branch, but then we find
           the diff for one commit at a time in our branch.
        3. For each such commit, if it can be applied without conflict, then apply it,
           otherwise, ask user same as in step 4 of merge
        4. If manual editing is picked, we pause the replay until user has edited
           files and resumed
        """
        self.common()

        branch = self.active_branch

        # Get some paths for later
        all_refs = ['head', 'stage', 'workspace']
        mfs_paths = {ref: self.get_mfs_path(self.fs_repo_root, branch, branch_info=ref)
                     for ref in all_refs}
        mfs_merge_paths = {ref: self.get_mfs_path(
                           self.fs_repo_root, branch, branch_info=f'merge_{ref}')
                           for ref in ['parent', 'replay_offset', *all_refs]}

        # Here's a tricky part: if we're resuming a replay, then the current head
        # is modified with their commits and our replayed commits. In order to resume
        # the replay however, we need to recalculate changesets and other variables
        # as if the head is still the original head. So set the head path to
        # the merge backup head path
        if resume:
            mfs_paths['head'] = mfs_merge_paths['head']

        if abort:
            # Could be abort after regular merge, or during replay merge
            is_merge = False
            try:
                # Check that merge_parent is there, otherwise it will raise
                self.ipfs.files_rm(mfs_merge_paths['parent'], recursive=True)
                is_merge = True
            except:
                pass

            is_replay = False
            try:
                # Do the same for replay
                self.ipfs.files_rm(mfs_merge_paths['replay_offset'], recursive=True)
                is_merge = True
            except:
                pass

            if not is_merge and not is_replay:
                self.print_err('There is no pull merge or replay in progress')
                raise RuntimeError()

            # Reset all refs
            for ref in all_refs:
                self.ipfs.files_rm(mfs_paths[ref], recursive=True)
                self.ipfs.files_cp(mfs_merge_paths[ref], mfs_paths[ref])

            # Restore the fs repo workspace
            self._load_ref_into_repo(self.fs_repo_root, branch, 'workspace')

            # Remove backups
            for ref in all_refs:
                self.ipfs.files_rm(mfs_merge_paths[ref], recursive=True)
            return

        if resume:
            #check that we have a replay merge conflict
            pass
        else:
            our_hashes = {ref: self.get_branch_info_hash(branch, ref) for ref in all_refs}
            their_hashes = {ref: self.get_branch_info_hash(their_branch, ref) for ref in all_refs}

            # Find the Lowest Common Ancestor
            lca_commit_hash, our_lca_path, their_lca_path = self._find_LCA(
                our_hashes['head'], their_hashes['head'])

            def _ref_files_hash(h):
                return self.ipfs.files_stat(f'/ipfs/{h}/bundle/files')['Hash']

            lca_files_hash = _ref_files_hash(lca_commit_hash)
            their_files_hash = _ref_files_hash(their_hashes['head'])
            our_file_hashes = {ref: _ref_files_hash(our_hashes[ref]) for ref in all_refs}
            # Check collisions with stage and workspace changes
            # NOTE: Check staged changes first since workspace contains changes based
            # on the staged changes
            our_file_changes = {ref: self._get_file_changes(
                our_file_hashes['head'], our_file_hashes[ref]) for ref in ['stage', 'workspace']}

            their_file_changes = self._get_file_changes(lca_files_hash, their_files_hash)
            stage_conflict_set = our_file_changes['stage'].keys() & their_file_changes.keys()
            if len(stage_conflict_set) > 0:
                self.print_err('Pull conflicts with local staged changes in:')
                self.print_err('\n'.join(list(stage_conflict_set)))
                raise RuntimeError()
            workspace_conflict_set = our_file_changes['workspace'].keys() & their_file_changes.keys()
            if len(workspace_conflict_set) > 0:
                self.print_err('Pull conflicts with local workspace changes in:')
                self.print_err('\n'.join(list(workspace_conflict_set)))
                raise RuntimeError()

        if replay:
            # Get our commits since LCA, and changesets for each
            our_lca_path = our_lca_path[::-1] # reverse so that lca comes first

            if not resume: # will have already been done during replay command
                # Copy their head to all our refs (head, stage, workspace)
                # Backup our refs in case there's a merge conflict
                for ref in all_refs:
                    self.ipfs.files_cp(f'/ipfs/{our_hashes[ref]}', mfs_merge_paths[ref])
                    self.ipfs.files_rm(mfs_paths[ref], recursive=True)
                    self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}', mfs_paths[ref])
                    if ref is not 'head':
                        # Need to remove the parent link if the ref is stage or workspace
                        self.ipfs.files_rm(f'{mfs_paths[ref]}/parent', recursive=True)

                # Check out the workspace to the filesystem
                self._load_ref_into_repo(self.fs_repo_root, branch, 'workspace')

            curr_lca_to_head_changes = their_file_changes
            curr_head_files_hash = their_files_hash

            o = 0 # offset applied to our commits (if replay is resuming somewhere)
            if resume:
                o = int(self.ipfs.files_read(mfs_merge_paths['replay_offset']))

            our_lca_files_hashes = [_ref_files_hash(h) for h in our_lca_path]
            our_changes = [self._get_file_changes(h1, h2) for h1, h2
                           in zip(our_lca_files_hashes[:-1], our_lca_files_hashes[1:])]

            # For each of our changeset, merge with the current head
            # We skip the first commit in the path (being the LCA), and then
            # use the replay offset 'o' if we are resuming a replay
            all_merged, all_pulled = set(), set()
            for i, (h, fh, changes) in enumerate(zip(
                    our_lca_path[1+o:], our_lca_files_hashes[1+o:], our_changes[o:])):
                # Write the current offset so we can resume from here if there
                # is a conflict
                self.ipfs.files_write(
                    mfs_merge_paths['replay_offset'],
                    io.BytesIO(bytes(str(i), 'utf-8')),
                    create=True, truncate=True)

                merged_files, conflict_files, pulled_files = self._merge(
                    curr_lca_to_head_changes, changes, fh)
                all_merged = all_merged | merged_files
                all_pulled = all_pulled | pulled_files
                if len(conflict_files) > 0:
                    self.print(('There are merge conflicts, please resolve and '
                                'the run `ipvc branch pull --resume`'))
                    return all_pulled, all_merged, conflict_files

                # No conflicts, so re-commit the changes with the same metadata as before
                # but with an additional 'is_replay' flag
                meta = self.get_commit_metadata(h)
                meta['is_replay'] = True
                new_commit_hash = self.ipvc.stage.commit(commit_metadata=meta)
                curr_head_files_hash = _ref_files_hash(new_commit_hash)

                # Update the changes between lca and head
                curr_lca_to_head_changes = self._get_file_changes(
                    lca_files_hash, curr_head_files_hash)

            # We are done with all replay commits, so remove the backups and replay_offset
            for ref in ['head', 'stage', 'workspace', 'replay_offset']:
                self.ipfs.files_rm(mfs_merge_paths[ref], recursive=True)

            return all_pulled, all_merged, set()
        else:
            our_lca_changes = self._get_file_changes(lca_files_hash, our_file_hashes['head'])
            merged_files, conflict_files, pulled_files = self._merge(
                our_lca_changes, their_file_changes, their_files_hash)

            if lca_commit_hash == our_hashes['head'] and not no_fast_forward:
                # This is a fast-forward merge, just update the head
                # The changes from their commit have already been added to workspace and stage
                # so all that is left to do is to update the head
                self.ipfs.files_rm(mfs_paths['head'], recursive=True)
                self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}', mfs_paths['head'])
                self.print('Performed a fast-forward merge')
            else:
                if len(conflict_files) > 0:
                    self.print(('Pull produced merge conflicts. Edit the conflicts and '
                                'commit, or run `ipvc branch pull --abort` to abort'))
                else:
                    self.print(('Pull merge successful. Commit with a merge message or '
                                'run `ipvc branch pull --abort` to abort'))

                # Save their head as the merge_parent
                self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}', mfs_merge_paths['parent'])

                # Save backup of previous refs
                for ref in all_refs:
                    self.ipfs.files_cp(f'/ipfs/{our_hashes[ref]}', mfs_merge_paths[ref])

            return pulled_files, merged_files, conflict_files

    @atomic
    def show(self, refpath, browser=False):
        """ Opens a ref in the ipfs file browser """
        commit_files_hash = self.get_refpath_files_hash(Path(refpath))
        if browser:
            # TODO: read IPFS node url from settings
            url = f'http://localhost:8080/ipfs/{commit_files_hash}'
            self.print(f'Opening {url}')
            webbrowser.open(url)
        else:
            ret = self.ipfs.ls(f'/ipfs/{commit_files_hash}')
            obj = ret['Objects'][0]
            if len(obj['Links']) == 0:
                # It's a file, so cat it
                cat = self.ipfs.cat(f'/ipfs/{commit_files_hash}').decode('utf-8')
                self.print(cat)
                return cat
            else:
                # It's a folder
                ls = '\n'.join([ln['Name'] for ln in obj['Links']])
                self.print(ls)
                return ls

    @atomic
    def ls(self):
        """ List branches """
        self.print('\n'.join(self.branches))
        return self.branches

    @atomic
    def rm(self):
        self.invalidate_cache(['branches', 'active_branch'])

    @atomic
    def mv(self):
        self.invalidate_cache(['branches', 'active_branch'])


