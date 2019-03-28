import os
import io
import json
import sys
from pathlib import Path
from datetime import datetime

from Crypto.PublicKey import RSA
from Crypto import Cipher

import ipfsapi
from ipvc.common import CommonAPI, atomic

import crypto_pb2
import base64

def deserialize_pk_protobuf(byte_message, proto_type):
    """
    This is a function to decode the PrivKey in the IPFS config, since it is
    in a protobuf format
    (see https://stackoverflow.com/questions/54270908/how-to-decode-ipfs-private-and-public-key-in-der-pem-format/54271911#54271911)
    """
    module_, class_ = proto_type.rsplit('.', 1)
    class_ = getattr(crypto_pb2, class_) # crypto_pb2 is a name of module we recently created and imported
    rv = class_()
    rv.ParseFromString(byte_message) # use .SerializeToString() to reverse operation
    return rv


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
                self.print_err(f'Path outside workspace {fs_path}')
                raise

    def _notify_conflict(self, fs_repo_root, branch):
        mfs_merge_parent = self.get_mfs_path(fs_repo_root, branch, branch_info='merge_parent')
        try:
            self.ipfs.files_stat(mfs_merge_parent)
            self.print(('You are in the merge conflict state. To resolve '
                        'first edit conflict, then run `ipvc branch pull --resolve`\n'
                        'To abort merge, run `ipvc branch pull --abort`'))
            return True
        except:
            return False

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

        if len(changes) == 0:
            self.print('No changes')
        else:
            self.print('Changes:')
            self.print_changes(changes)
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

        if len(changes) == 0:
            self.print('No changes')
        else:
            self.print('Changes:')
            self.print_changes(changes)
        return changes

    @atomic
    def status(self):
        """ Show diff between workspace and stage, and between stage and head """
        self.common()
        self._notify_conflict(self.fs_repo_root, self.active_branch)

        head_stage_changes, *_ = self.get_mfs_changes(
            'head/data/bundle/files', 'stage/data/bundle/files')
        if len(head_stage_changes) == 0:
            self.print('No staged changes')
        else:
            self.print('Staged:')
            self.print_changes(head_stage_changes)
            self.print('-'*80)

        stage_workspace_changes, *_ = self.get_mfs_changes(
            'stage/data/bundle/files', 'workspace/data/bundle/files')
        if len(stage_workspace_changes) == 0:
            self.print('No unstaged changes')
        else:
            self.print('Unstaged:')
            self.print_changes(stage_workspace_changes)

        return head_stage_changes, stage_workspace_changes

    @atomic
    def commit(self, message=None, commit_metadata=None, merge_parent=None):
        """ Creates a new commit with the staged changes and returns new commit hash

        If commit_metadata is provided instead of message, then it will be used instead
        of generating new metadata
        """
        self.common()
        programmatic_commit = (commit_metadata or merge_parent) is not None
        if (not programmatic_commit and
                self._notify_conflict(self.fs_repo_root, self.active_branch)):
            raise RuntimeError


        changes = self._diff_changes(Path('@stage'), Path('@head'))
        if not programmatic_commit and len(changes) == 0:
            self.print_err('Nothing to commit')
            raise RuntimeError

        # Retrieve public/private encryption keys for commit signing and author
        # commit entry
        mfs_ipfs_repo_path = self.get_mfs_path(self.fs_cwd, repo_info='ipfs_repo_path')
        ipfs_repo_path = self.ipfs.files_read(mfs_ipfs_repo_path).decode('utf-8')
        private_key, public_key = None, None
        rsa_priv_key, rsa_pub_key = None, None
        crypter, decrypter = None, None
        with open(Path(ipfs_repo_path) / 'config') as f:
            config = json.loads(f.read())
            identity = config['Identity']
            peer_id, private_key = identity ['PeerID'], identity['PrivKey']
            decoded_private_key = base64.b64decode(private_key)
            private_key = deserialize_pk_protobuf(
                decoded_private_key, 'crypto.pb.PrivateKey').Data
            rsa_priv_key = RSA.importKey(private_key)
            rsa_pub_key = rsa_priv_key.publickey()
            public_key_pem = rsa_pub_key.exportKey('PEM').decode('utf-8')

        # Create commit_metadata if not provided
        if commit_metadata is None:
            if message is None:
                message = self._get_editor_commit_message()

            if len(message) == 0:
                self.print_err('Aborting: Commit message is empty')
                raise RuntimeError

            params = self.read_global_params()
            commit_metadata = {
                'message': message,
                'author': {
                    'peer_id': peer_id,
                    'public_key': public_key_pem
                },
                'timestamp': datetime.utcnow().isoformat(),
            }

            if merge_parent is not None:
                # Could be useful, so we don't have to check for 'merge_parent'
                # in mfs when printing history etc
                commit_metadata['is_merge'] = True

        mfs_head = self.get_mfs_path(self.fs_repo_root, self.active_branch, branch_info='head')
        mfs_stage = self.get_mfs_path(self.fs_repo_root, self.active_branch, branch_info='stage')
        head_hash = self.ipfs.files_stat(mfs_head)['Hash']
        stage_hash = self.ipfs.files_stat(mfs_stage)['Hash']
        if head_hash == stage_hash:
            self.print_err('Nothing to commit')
            raise RuntimeError

        # Set head to stage
        try:
            self.ipfs.files_rm(mfs_head, recursive=True)
        except ipfsapi.exceptions.StatusError:
            pass

        self.ipfs.files_cp(mfs_stage, mfs_head)

        # Add parent pointer to previous head
        self.ipfs.files_cp(f'/ipfs/{head_hash}', f'{mfs_head}/data/parent')

        if merge_parent is not None:
            # Add merge_parent to merged head if this was a merge commit
            self.ipfs.files_cp(merge_parent, f'{mfs_head}/data/merge_parent')

        # Sign the commit bundle and data hash
        bundle_hash = self.ipfs.files_stat(f'{mfs_head}/data/bundle')['Hash'].encode('utf-8')
        data_hash = self.ipfs.files_stat(f'{mfs_head}/data/')['Hash'].encode('utf-8')
        data_signature = rsa_priv_key.sign(data_hash, K='wtf?')[0]
        assert rsa_pub_key.verify(data_hash, (data_signature,))
        bundle_signature = rsa_priv_key.sign(bundle_hash, K='wtf?')[0]
        assert rsa_pub_key.verify(bundle_hash, (bundle_signature,))

        # Write signed hashes to commit 
        self.ipfs.files_write(
            f'{mfs_head}/bundle_signature',
            io.BytesIO(str(bundle_signature).encode('utf-8')),
            create=True, truncate=True)
        self.ipfs.files_write(
            f'{mfs_head}/data_signature',
            io.BytesIO(str(data_signature).encode('utf-8')),
            create=True, truncate=True)

        # Add commit metadata
        metadata_bytes = io.BytesIO(json.dumps(commit_metadata).encode('utf-8'))
        self.ipfs.files_write(
            f'{mfs_head}/data/commit_metadata', metadata_bytes, create=True, truncate=True)

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
        self._notify_conflict(self.fs_repo_root, self.active_branch)
        changes = self._diff_changes(Path('@stage'), Path('@head'))
        self.print(self._format_changes(changes, files=False))
        return changes
