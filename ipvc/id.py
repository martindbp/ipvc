import io
import sys
import json
import shutil

from ipvc.common import CommonAPI, atomic

class IdAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def ls(self):
        """
        List all local and remote ids
        """
        unused = set(self.all_ipfs_ids()) - set(self.ids['local'])
        if len(unused) > 0:
            self.print('Unused IPFS keys:')
            self.print('\n'.join(unused))
            self.print(('\nNOTE: to create a new IPFS key and id, run '
                       '`ipvc create <key_name>`\n'))
        
        for key_name, data in self.ids['local'].items():
            peer_id = self.id_info(key_name)['peer_id']
            self.print(f'Local: {key_name}')
            self.print_id(peer_id, data, '  ')

        for peer_id, data in self.ids['remote'].items():
            self.print('Remote:')
            self.print_id(peer_id, data, '  ')

    @atomic
    def create(self, key=None):
        """
        Creates new IPFS key for a IPVC id
        """
        self.print(f'Generating key with name "{key}"')
        all_ids = self.all_ipfs_ids()
        if key in all_ids:
            self.print_err('Key by that name already exists')
            raise RuntimeError()

        try:
            ret = self.ipfs.key_gen(key, 'rsa', 2048)
            self.print(f'Generated key with PeerID {ret["Id"]}')
            self.print('To set parameters for the key, use ')
            self.print((f'`ipvc set [--name <...>] [--email <...>] [--desc <...>] '
                        '[--img <...>] [--link <...>] [--key_name <...>] [<path>]`'))
            self.print('To set an ID for a repo, use `ipvc repo id <key_name>`')
        except:
            self.print_err('Failed')
            raise RuntimeError()

    @atomic
    def get(self, path, key=None):
        if key is None:
            fs_repo_root = self.get_repo_root(path)
            if fs_repo_root is None:
                self.print_err('There is no repo here') 
                raise RuntimeError()
            key = self.repo_path_id(fs_repo_root)

        peer_id = self.id_info(key)['peer_id']
        data = self.ids['local'][key]
        self.print_id(peer_id, data)

    @atomic
    def set(self, path, key=None, **kwargs):
        if key is None:
            fs_repo_root = self.get_repo_root(path)
            if fs_repo_root is None:
                self.print_err('There is no repo here') 
                raise RuntimeError()
            key = self.repo_path_id(fs_repo_root)

        if key not in self.all_ipfs_ids():
            self.print_err('There is no such key')
            raise RuntimeError()

        ids = self.ids
        if key not in ids['local']:
            ids['local'][key] = {}

        ids['local'][key].update(kwargs.items())
        ids_path = self.get_mfs_path(ipvc_info='ids')
        ids_bytes = io.BytesIO(json.dumps(ids).encode('utf-8'))
        self.ipfs.files_write(ids_path, ids_bytes, create=True, truncate=True)

        self.invalidate_cache(['repo_id', 'ids'])

    @atomic
    def publish(self, path, key=None):
        pass

    @atomic
    def resolve(self, peer_id=None, name=None):
        pass
