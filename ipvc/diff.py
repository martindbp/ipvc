import difflib
from pathlib import Path
from ipvc.common import CommonAPI, refpath_to_mfs, print_changes

class DiffAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _resolve_refs(self, to_refpath=None, from_refpath=None,
                      to_default="@workspace", from_default='@stage'):
        to_refpath, from_refpath  = Path(to_refpath), Path(from_refpath)
        if from_refpath is None and to_refpath is None:
            to_refpath = '@workspace'
            from_refpath = '@stage'
            mfs_to_refpath, _ = refpath_to_mfs(to_refpath)
            mfs_from_refpath, _ = refpath_to_mfs(from_refpath)
        elif from_refpath is None:
            mfs_to_refpath, files_part = refpath_to_mfs(to_refpath)
            mfs_from_refpath, _ = refpath_to_mfs(from_default / files_part)
        else:
            mfs_to_refpath, _ = refpath_to_mfs(to_refpath)
            mfs_from_refpath, _ = refpath_to_mfs(from_refpath)

        return mfs_to_refpath, mfs_from_refpath

    def run(self, to_refpath="@stage", from_refpath="@head", files=False):
        if files:
            fs_workspace_root, branch = self.common()
            to_refpath, from_refpath = self._resolve_refs(to_refpath, from_refpath)

            changes, *_ = self.get_mfs_changes(
                from_refpath, to_refpath)
            if not self.quiet:
                print_changes(changes)

            return changes
        else:
            fs_workspace_root, branch = self.common()
            to_refpath, from_refpath = self._resolve_refs(to_refpath, from_refpath)

            changes, *_ = self.get_mfs_changes(from_refpath, to_refpath)
            for change in changes:
                if change['Type'] != 2:
                    continue # only show modifications
                file1 = self.ipfs.cat(change['Before']['/']).decode('utf-8').split('\n')
                file2 = self.ipfs.cat(change['After']['/']).decode('utf-8').split('\n')
                diff = difflib.unified_diff(file1, file2, lineterm='')
                if not self.quiet:
                    print('\n'.join(list(diff)[:-1]))

            return changes
