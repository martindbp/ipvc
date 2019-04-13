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
            self.ipfs.files_stat(self.get_mfs_path(self.fs_repo_root, name))
            self.print_err('Branch name already exists')
            raise RuntimeError()
        except ipfsapi.exceptions.StatusError:
            pass

        if from_commit == "@head":
            # Simply copy the current branch to the new branch
            self.ipfs.files_cp(
                self.get_mfs_path(self.fs_repo_root, self.active_branch),
                self.get_mfs_path(self.fs_repo_root, name))
            self.invalidate_cache(['branches'])
        else:
            # Create the branch directory along with an empty stage and workspace
            for ref in ['stage', 'workspace']:
                mfs_ref = self.get_mfs_path(self.fs_repo_root, name, branch_info=f'{ref}/data/')
                self.ipfs.files_mkdir(mfs_ref, parents=True)
            self.invalidate_cache(['branches'])

            # Copy the commit to the new branch's head
            _, commit_path = expand_ref(from_commit)
            mfs_commit_path = self.get_mfs_path(
                self.fs_repo_root, self.active_branch, branch_info=commit_path)
            mfs_head_path = self.get_mfs_path(
                self.fs_repo_root, name, branch_info='head')

            try:
                self.ipfs.files_stat(mfs_commit_path)
            except ipfsapi.exceptions.StatusError:
                self.print_err('No such commit')
                raise RuntimeError()

            self.ipfs.files_cp(mfs_commit_path, mfs_head_path)

            # Copy commit bundle to workspace and stage
            mfs_commit_bundle_path = f'{mfs_commit_path}/data/bundle'
            mfs_workspace_path = self.get_mfs_path(
                self.fs_repo_root, name, branch_info='workspace/data/bundle')
            mfs_stage_path = self.get_mfs_path(
                self.fs_repo_root, name, branch_info='stage/data/bundle')
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_workspace_path)
            self.ipfs.files_cp(mfs_commit_bundle_path, mfs_stage_path)

        if not no_checkout:
            self.checkout(name)

    @atomic
    def checkout(self, name, without_timestamps=False):
        """ Checks out a branch"""
        self.common()

        try:
            self.ipfs.files_stat(self.get_mfs_path(self.fs_repo_root, name))
        except ipfsapi.exceptions.StatusError:
            self.print_err('No branch by that name exists')
            raise RuntimeError()

        self.set_active_branch(self.fs_repo_root, name)
        self._load_ref_into_repo(
            self.fs_repo_root, name, 'workspace', without_timestamps)

    def _get_commit_parents(self, commit_hash):
        """ Returns hash and metadata of parent commit and merge parent (if present) """
        try:
            parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/data/parent')['Hash']
            parent_metadata = self.get_commit_metadata(parent_hash)
        except ipfsapi.exceptions.StatusError:
            # Reached the root of the graph
            return None, None, None, None

        try:
            merge_parent_hash = self.ipfs.files_stat(f'/ipfs/{commit_hash}/data/merge_parent')['Hash']
            merge_parent_metadata = self.get_commit_metadata(merge_parent_hash)
            return parent_hash, parent_metadata, merge_parent_hash, merge_parent_metadata
        except:
            return parent_hash, parent_metadata, None, None

    def get_commit_metadata(self, commit_hash):
        # NOTE: the root commit doesn't have a commit_metadata file, so this
        # might fail
        return json.loads(self.ipfs.cat(f'/ipfs/{commit_hash}/data/commit_metadata').decode('utf-8'))

    @atomic
    def history(self, show_hash=False, show_peer=False):
        """ Shows the commit history for the current branch. Currently only
        shows the linear history on the first parents side Returns list of
        commits in order from last to first, as a tuple of commit hash, parent
        hash and merge parent hash """
        self.common()

        # Traverse the commits backwards by via the {commit}/data/parent/ link
        mfs_commit_path = self.get_mfs_path(
            self.fs_repo_root, self.active_branch, branch_info=Path('head'))
        commit_hash = self.ipfs.files_stat(
            mfs_commit_path)['Hash']
        commit_metadata = self.get_commit_metadata(commit_hash)

        commits = []
        while True:
            h, ts, msg = commit_hash[:6], commit_metadata['timestamp'], commit_metadata['message']
            short_desc, long_desc = self._split_commit_message(msg)
            peer = make_len('', 30)
            if show_peer:
                peer = make_len('peer: Qm...' + commit_metadata['author']['peer_id'][-5:], 30)
            if show_hash:
                self.print(f'* {commit_hash} {ts} {peer}   {short_desc}')
            else:
                self.print(f'* {ts} {peer}   {short_desc}')

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

    def _merge(self, our_file_changes, our_branch,
               their_file_changes, their_files_hash, their_branch):
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
                            f.write(f'>>>>>>> {our_branch} (ours)\n')
                            f.write('\n'.join(our_lines) + '\n')
                            f.write(f'======= {their_branch} (theirs)\n')
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

    def _resolve_conflicts(self, conflict_files_path, our_branch, their_branch,
                           merge_type):
            # Make sure the conflicts are resolved, and stage the changes
            conflict_files = self.ipfs.files_read(
                conflict_files_path).decode('utf-8')
            for filename in conflict_files.split('\n'):
                full_path = self.fs_repo_root / filename
                start_idx, middle_idx, end_idx = -1, -1, -1
                with open(full_path, 'r') as f:
                    for i, line in enumerate(f.readlines()):
                        if line == f'>>>>>>> {our_branch} (ours)\n':
                            start_idx = i
                        elif line == f'======= {their_branch} (theirs)\n':
                            middle_idx = i
                        elif line == '<<<<<<<\n':
                            end_idx = i

                # Make sure markers are in the right order
                has_markers = start_idx < middle_idx < end_idx
                if has_markers:
                    self.print_err(f'Conflicts in {filename} have not been resolved')
                    self.print_err(f'Please resolved them, or abort by `ipvc branch {merge_type} --abort`')
                    raise RuntimeError

                # Stage the changes
                self.add_fs_to_mfs(full_path, 'workspace')
                self.add_ref_changes_to_ref('workspace', 'stage', filename)


    def _ref_files_hash(self, h):
        return self.ipfs.files_stat(f'/ipfs/{h}/data/bundle/files')['Hash']

    @atomic
    def merge(self, their_branch=None, no_ff=False, abort=False,
              resolve=None):
        """
        Merges our branch with their branch and creates a new merge commit
        with two parents (parent and merge_parent).

        The general procedure is:
        1. Get the commits hashes for our branch and `their_branch`
        2. Find the lowest common ancestor of the two commits
        3. Find the diff between LCA and both commits
        4. If diffs don't conflict, apply, then ask for commit message via editor
           or take the message coming from the --resolve argument
        5. If there are conflicts, exit and let the user edit the conflicts, then
           run the merge command again with the --resolve [<message>] argument.
        6. If the user instead wants to cancel, then she can run with --abort
        7. If one of the branches are the LCA, then by default we don't create a 
           merge (since tree was not split) but just update the head pointer, unless
           the --no-ff (no fast-forward) option is supplied

        TODO: implement --use [ours/theirs] for resolving conflicts
        """
        message = resolve if resolve is not True else None
        resolve = resolve is not None

        self.common()

        branch = self.active_branch

        # Get some paths for later
        base_refs = ['head', 'stage', 'workspace']
        mfs_paths = {ref: self.get_mfs_path(self.fs_repo_root, branch, branch_info=ref)
                     for ref in base_refs}
        merge_refs = ['merge_parent', 'their_branch', 'conflict_files']
        mfs_merge_paths = {ref: self.get_mfs_path(
                           self.fs_repo_root, branch, branch_info=ref)
                           for ref in merge_refs}
        for ref in base_refs:
            mfs_merge_paths[ref] = self.get_mfs_path(
                self.fs_repo_root, branch, branch_info=f'merge_{ref}')

        if resolve or abort:
            try:
                # Check that merge_parent is there, otherwise it will raise
                self.ipfs.files_stat(mfs_merge_paths['merge_parent'])
            except:
                self.print_err('There is no merge in progress')
                raise RuntimeError

        if abort:
            # Reset all base refs
            for ref in base_refs:
                self.ipfs.files_rm(mfs_paths[ref], recursive=True)
                self.ipfs.files_cp(mfs_merge_paths[ref], mfs_paths[ref])

            # Restore the fs repo workspace
            self._load_ref_into_repo(self.fs_repo_root, branch, 'workspace')

            for ref in mfs_merge_paths.keys():
                self.ipfs.files_rm(mfs_merge_paths[ref], recursive=True)
            return

        if resolve:
            their_branch = self.ipfs.files_read(
                mfs_merge_paths['their_branch']).decode('utf-8')
            self._resolve_conflicts(
                mfs_merge_paths['conflict_files'], branch, their_branch, 'merge')

            if message is None:
                while message is None:
                    message = self._get_editor_commit_message('Merge')
                    if len(message) == 0:
                        answer = input('Commit message was empty, try again? (y/n): ')
                        if answer.lower() == 'n':
                            self.print('Aborting merge --resolve')
                            raise RuntimeError

            self.ipvc.stage.commit(message, merge_parent=mfs_merge_paths['merge_parent'])

            # Clean up
            for ref in mfs_merge_paths.keys():
                self.ipfs.files_rm(mfs_merge_paths[ref], recursive=True)
            return

        their_hashes = {ref: self.get_branch_info_hash(their_branch, ref) for ref in base_refs}
        our_hashes = {ref: self.get_branch_info_hash(branch, ref) for ref in base_refs}

        # Find the Lowest Common Ancestor
        lca_commit_hash, our_lca_path, their_lca_path = self._find_LCA(
            our_hashes['head'], their_hashes['head'])

        lca_files_hash = self._ref_files_hash(lca_commit_hash)
        their_files_hash = self._ref_files_hash(their_hashes['head'])
        our_file_hashes = {ref: self._ref_files_hash(our_hashes[ref]) for ref in base_refs}
        # Check collisions with stage and workspace changes
        # NOTE: Check staged changes first since workspace contains changes based
        # on the staged changes
        our_file_changes = {ref: self._get_file_changes(
            our_file_hashes['head'], our_file_hashes[ref]) for ref in ['stage', 'workspace']}

        their_file_changes = self._get_file_changes(lca_files_hash, their_files_hash)
        if not resolve:
            stage_conflict_set = our_file_changes['stage'].keys() & their_file_changes.keys()
            if len(stage_conflict_set) > 0:
                self.print_err('Merge conflicts with local staged changes in:')
                self.print_err('\n'.join(list(stage_conflict_set)))
                raise RuntimeError()
            workspace_conflict_set = our_file_changes['workspace'].keys() & their_file_changes.keys()
            if len(workspace_conflict_set) > 0:
                self.print_err('Merge conflicts with local workspace changes in:')
                self.print_err('\n'.join(list(workspace_conflict_set)))
                raise RuntimeError()

        our_lca_changes = self._get_file_changes(lca_files_hash, our_file_hashes['head'])
        merged_files, conflict_files, pulled_files = self._merge(
            our_lca_changes, branch, their_file_changes, their_files_hash, their_branch)

        if lca_commit_hash == our_hashes['head'] and not no_ff:
            # This is a fast-forward merge, just update the head
            # The changes from their commit have already been added to workspace and stage
            # so all that is left to do is to update the head
            self.ipfs.files_rm(mfs_paths['head'], recursive=True)
            self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}', mfs_paths['head'])
            self.print('Performed a fast-forward merge')
        else:
            if len(conflict_files) > 0:
                # Save backup of previous refs
                for ref in base_refs:
                    self.ipfs.files_cp(f'/ipfs/{our_hashes[ref]}', mfs_merge_paths[ref])

                # Save their branch name, so we can resolve
                self.ipfs.files_write(
                    mfs_merge_paths['their_branch'],
                    io.BytesIO(their_branch.encode('utf-8')),
                    create=True, truncate=True)

                # Save conflict files
                self.ipfs.files_write(
                    mfs_merge_paths['conflict_files'],
                    io.BytesIO(bytes('\n'.join(list(conflict_files)), 'utf-8')),
                    create=True, truncate=True)

                # Save merge parent
                self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}',
                                   mfs_merge_paths['merge_parent'])

                self.print((
                    'Merge produced conflicts.\n'
                    'Edit the conflicts and run `ipvc branch merge --resolve [--message <msg>]`\n'
                    'Or run `ipvc branch merge --resolve` to bring up your editor of choice\n'
                    'To abort, run `ipvc branch merge --abort`'))
            else:
                if message is None:
                    input('Pull merge successful, please enter commit message [ENTER]')
                    while message is None:
                        message = self._get_editor_commit_message('Merge')
                        if len(message) == 0:
                            answer = input('Commit message was empty, try again? (y/n): ')
                            if answer.lower() == 'n':
                                self.print('Aborting merge')
                                raise RuntimeError
                else:
                    self.print('Merge successful')

                # NOTE: changes will have been staged by self._merge
                new_commit_hash = self.ipvc.stage.commit(
                    message, merge_parent=f'/ipfs/{their_hashes["head"]}')

        return pulled_files, merged_files, conflict_files


    @atomic
    def replay(self, their_branch=None, abort=False, resume=False):
        """
        Replays commits from our branch on top of their head, and sets the result
        as our branch. 

        The reason we apply our commits on top of their head is because then
        "they" can simply do a fast-forward merge with our branch, but if we do
        it the other way around they have to erase their branch and checkout
        ours completely. Plus, we are more familiar with our own commits, and
        can better understand what the commit is supposed to do in case of a merge
        conflict with their branch.

        The procedure is:
        1. Find LCA (Lowest Common Ancestor)
        2. First find the diff for their whole branch, and then find the diff
           for one commit at a time in our branch.
        3. For each such commit, if it can be applied without conflict, then apply it,
           otherwise we enter the merge conflict state and exit
        4. After the user has resolved the conflict by editing the conflicting file(s)
           then the user runs `ipvc branch replay --resume`, and we resume applying
           the commits where we left off. We use the edited changes as the new
           content for the commit that had the conflict
        5. If the user wants to abort instead, they can use the --abort flag

        TODO: implement --use [ours/theirs] for resolving conflicts
        """
        self.common()

        branch = self.active_branch

        # Get some paths for later
        base_refs = ['head', 'stage', 'workspace']
        mfs_paths = {ref: self.get_mfs_path(self.fs_repo_root, branch, branch_info=ref)
                     for ref in base_refs}
        replay_refs = ['conflict_commit', 'their_branch', 'conflict_files']
        mfs_replay_paths = {ref: self.get_mfs_path(
                            self.fs_repo_root, branch, branch_info=ref)
                            for ref in replay_refs}
        for ref in base_refs:
            mfs_replay_paths[ref] = self.get_mfs_path(
                self.fs_repo_root, branch, branch_info=f'replay_{ref}')

        if resume or abort:
            try:
                # Check that conflict_commit is there, otherwise it will raise
                self.ipfs.files_stat(mfs_replay_paths['conflict_commit'])
            except:
                self.print_err('There is no replay in progress')
                raise RuntimeError

        if abort:
            # Reset all base refs
            for ref in base_refs:
                self.ipfs.files_rm(mfs_paths[ref], recursive=True)
                self.ipfs.files_cp(mfs_replay_paths[ref], mfs_paths[ref])

            # Restore the fs repo workspace
            self._load_ref_into_repo(self.fs_repo_root, branch, 'workspace')

            for ref in mfs_replay_paths.keys():
                self.ipfs.files_rm(mfs_replay_paths[ref], recursive=True)
            return

        conflict_commit = None
        if resume:
            # Here's a tricky part: if we're resuming a replay, then the
            # current head is modified with their commits and our replayed
            # commits so far. In order to resume the replay however, we need to
            # recalculate changesets and other variables as if the head is
            # still the original head. So set the head path to the merge backup
            # head path
            mfs_paths['head'] = mfs_replay_paths['head']

            # Read 'their_branch', i.e. the branch that was pulled from
            their_branch = self.ipfs.files_read(
                mfs_replay_paths['their_branch']).decode('utf-8')

            self._resolve_conflicts(
                mfs_replay_paths['conflict_files'], branch, their_branch, 'replay')

            # Get the hash of the conflicting commit
            conflict_commit = self.ipfs.files_stat(
                mfs_replay_paths['conflict_commit'])['Hash']

            # Commit the changes with the metadata of the old commit
            meta = self.get_commit_metadata(conflict_commit)
            meta['is_replay'] = True
            self.ipvc.stage.commit(commit_metadata=meta)

        their_hashes = {ref: self.get_branch_info_hash(their_branch, ref) for ref in base_refs}
        our_hashes = {ref: self.get_branch_info_hash(branch, ref) for ref in base_refs}

        # Find the Lowest Common Ancestor
        lca_commit_hash, our_lca_path, their_lca_path = self._find_LCA(
            our_hashes['head'], their_hashes['head'])

        lca_files_hash = self._ref_files_hash(lca_commit_hash)
        their_files_hash = self._ref_files_hash(their_hashes['head'])
        our_file_hashes = {ref: self._ref_files_hash(our_hashes[ref]) for ref in base_refs}
        # Check collisions with stage and workspace changes
        # NOTE: Check staged changes first since workspace contains changes based
        # on the staged changes
        our_file_changes = {ref: self._get_file_changes(
            our_file_hashes['head'], our_file_hashes[ref]) for ref in ['stage', 'workspace']}

        their_file_changes = self._get_file_changes(lca_files_hash, their_files_hash)
        if not resume:
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

        # Get our commits since LCA, and changesets for each
        our_lca_path = our_lca_path[::-1] # reverse so that lca comes first

        if not resume: # will have already been done during replay command
            # Copy their head to all our refs (head, stage, workspace)
            # Backup our refs in case there's a merge conflict
            for ref in base_refs:
                self.ipfs.files_cp(f'/ipfs/{our_hashes[ref]}', mfs_replay_paths[ref])
                self.ipfs.files_rm(mfs_paths[ref], recursive=True)
                self.ipfs.files_cp(f'/ipfs/{their_hashes["head"]}', mfs_paths[ref])
                if ref is not 'head':
                    # Need to remove the parent link if the ref is stage or workspace
                    self.ipfs.files_rm(f'{mfs_paths[ref]}/data/parent', recursive=True)

            # Check out the workspace to the filesystem
            self._load_ref_into_repo(self.fs_repo_root, branch, 'workspace')

        curr_lca_to_head_changes = their_file_changes
        curr_head_files_hash = their_files_hash

        our_lca_files_hashes = [self._ref_files_hash(h) for h in our_lca_path]
        our_changes = [self._get_file_changes(h1, h2) for h1, h2
                       in zip(our_lca_files_hashes[:-1], our_lca_files_hashes[1:])]

        # For each of our changeset, merge with the current head
        # We skip the first commit in the path (being the LCA)
        found_replay_conflict = True if conflict_commit is None else False
        all_merged, all_pulled = set(), set()
        for i, (h, fh, changes) in enumerate(zip(
                our_lca_path[1:], our_lca_files_hashes[1:], our_changes)):
            if h == conflict_commit:
                found_replay_conflict = True
                continue

            if not found_replay_conflict:
                continue

            merged_files, conflict_files, pulled_files = self._merge(
                curr_lca_to_head_changes, branch, changes, fh, their_branch)
            all_merged = all_merged | merged_files
            all_pulled = all_pulled | pulled_files
            if len(conflict_files) > 0:
                # Save their branch name, so we can resume in --resolve
                self.ipfs.files_write(
                    mfs_replay_paths['their_branch'],
                    io.BytesIO(their_branch.encode('utf-8')),
                    create=True, truncate=True)

                # Save conflict files
                self.ipfs.files_write(
                    mfs_replay_paths['conflict_files'],
                    io.BytesIO(bytes('\n'.join(list(conflict_files)), 'utf-8')),
                    create=True, truncate=True)

                # Write the current commit so we can resume from here when we resolve
                self.ipfs.files_cp(f'/ipfs/{h}',
                                   mfs_replay_paths['conflict_commit'])

                self.print(('There are merge conflicts, please resolve and '
                            'the run `ipvc branch replay --resume`\n'
                            'or abort by running `ipvc branch replay --abort'))
                return all_pulled, all_merged, conflict_files

            # No conflicts, so re-commit the changes with the same metadata as before
            # but with an additional 'is_replay' flag (could be uselful?)
            meta = self.get_commit_metadata(h)
            meta['is_replay'] = True
            new_commit_hash = self.ipvc.stage.commit(commit_metadata=meta)
            curr_head_files_hash = self._ref_files_hash(new_commit_hash)

            # Update the changes between lca and head
            curr_lca_to_head_changes = self._get_file_changes(
                lca_files_hash, curr_head_files_hash)

        # We are done with all replay commits, so remove the replay data
        for ref in replay_refs:
            try:
                self.ipfs.files_rm(mfs_replay_paths[ref], recursive=True)
            except:
                pass

        return all_pulled, all_merged, set()

    @atomic
    def show(self, refpath, browser=False):
        """ Opens a ref in the ipfs file browser or cat's it """
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

    @atomic
    def publish(self, branch=None, lifetime='8760h'):
        """ Publish repo with a name to IPNS """
        self.common()
        branch = branch or self.active_branch

        if self.repo_name is None:
            self.print_err(('This repo has no name, set one with '
                           '`ipvc repo name <name>` and publish again'))
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'].get(self.repo_id, {})

        changed = self.prepare_publish_branch(self.repo_id, branch, self.repo_name)
        if not changed:
            self.print("The branch hasn't changed since last published")
            return

        self.print((f'Publishing {self.repo_name}/{branch} to {peer_id} '
                    f'with lifetime {lifetime}'))
        self.publish_ipns(self.repo_id, lifetime)

    @atomic
    def unpublish(self, branch=None, lifetime='8760h'):
        self.common()
        branch = branch or self.active_branch

        if self.repo_name is None:
            self.print_err('This branch/repo has not been published')
            raise RuntimeError()

        peer_id = self.id_peer_keys(self.repo_id)['peer_id']
        data = self.ids['local'].get(self.repo_id, {})
        mfs_pub_branch = self.get_mfs_path(
            ipvc_info=f'published/{self.repo_id}/repos/{self.repo_name}/{branch}')
        try:
            self.ipfs.files_rm(mfs_pub_branch, recursive=True)
        except ipfsapi.exceptions.StatusError:
            self.print_err('This branch/repo has not been published')
            raise RuntimeError()

        self.print(f'Updating IPNS entry for {peer_id} with lifetime {lifetime}')
        self.publish_ipns(self.repo_id, lifetime)
