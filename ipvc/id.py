import io
import sys
import json
import shutil

import ipfsapi

from ipvc.common import CommonAPI, atomic

class IdAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def ls(self, unused=False):
        """
        List all local and remote ids
        """
        if unused:
            unused_keys = set(self.all_ipfs_ids()) - set(self.ids['local'])
            if len(unused_keys) > 0:
                self.print('\n'.join(unused_keys))
                self.print(('\nNOTE: to create a new IPFS key and id, run '
                            '`ipvc create <key_name>`\n'))
            return
        
        for key_name, data in self.ids['local'].items():
            peer_id = self.id_peer_keys(key_name)['peer_id']
            self.print(f'Local: {key_name}')
            self.print_id(peer_id, data, '  ')

        for peer_id, data in self.ids['remote'].items():
            self.print('Remote:')
            self.print_id(peer_id, data, '  ')

    @atomic
    def create(self, key, use=False):
        """
        Creates new IPFS key for a IPVC id
        """
        fs_repo_root, _ = self.common()
        self.print(f'Generating key with name "{key}"')
        all_ids = self.all_ipfs_ids()
        if key in all_ids:
            self.print_err('Key by that name already exists')
            if use:
                self.print('Using the id for this repo')
                self.ipvc.repo.id(key)
            return

        try:
            ret = self.ipfs.key_gen(key, 'rsa', 2048)
            self.print(f'Generated id with PeerID {ret["Id"]}')
            self.print((f'To set parameters for the id, run '
                        '`ipvc set [--name ...] [--email ...] [--desc ...] '
                        '[--img ...] [--link ...]`'))
            if use:
                self.print('Using the id for this repo')
                self.ipvc.repo.id(key)
            else:
                self.print(f'To set this id for a repo, use `ipvc repo id {key}`')
        except:
            self.print_err('Failed')
            raise RuntimeError()

    @atomic
    def get(self, key=None):
        """ Get info for an ID """
        self.common()

        if key is None: key = self.repo_id
        peer_id = self.id_peer_keys(key)['peer_id']
        data = self.ids['local'].get(key, {})
        self.print(f'Key: {key}')
        self.print_id(peer_id, data)

    @atomic
    def set(self, key=None, **kwargs):
        """ Set info for an ID """
        self.common()

        if key is None: key = self.repo_id
        if key not in self.all_ipfs_ids():
            self.print_err('There is no such key')
            raise RuntimeError()

        ids = self.ids
        if key not in ids['local']:
            ids['local'][key] = {}

        ids['local'][key].update(kwargs.items())
        empty_params = []
        for param, val in ids['local'][key].items():
            if val is None:
                empty_params.append(param)
        for param in empty_params:
            del ids['local'][key][param]

        ids_path = self.get_mfs_path(ipvc_info='ids')
        ids_bytes = io.BytesIO(json.dumps(ids).encode('utf-8'))
        self.ipfs.files_write(ids_path, ids_bytes, create=True, truncate=True)

        self.invalidate_cache(['id', 'ids'])

    @atomic
    def publish(self, key=None, lifetime='8760h'):
        self.common()

        if key is None: key = self.repo_id
        peer_id = self.id_peer_keys(key)['peer_id']
        data = self.ids['local'][key]
        self.print(f'Publishing identity to IPNS:')
        self.print_id(peer_id, data, '  ')
        self.print('')

        # Delete the old identity if there
        pub_path = self.get_mfs_path(ipvc_info=f'published/{key}')
        try:
            self.ipfs.files_mkdir(pub_path, parents=True)
        except ipfsapi.exceptions.StatusError:
            pass
        id_path = f'{pub_path}/identity'
        try:
            self.ipfs.files_rm(id_path)
        except ipfsapi.exceptions.StatusError:
            pass

        id_bytes = io.BytesIO(json.dumps(data).encode('utf-8'))
        self.ipfs.files_write(id_path, id_bytes, create=True, truncate=True)
        self.publish_ipns(key, lifetime)


    @atomic
    def resolve(self, peer_id=None):
        """ Resolve info for remote ids that we've seen in commits """
        pass
