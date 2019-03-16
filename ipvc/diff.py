from pathlib import Path
from ipvc.common import CommonAPI

class DiffAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, to_refpath=Path("@workspace"), from_refpath=Path("@stage"), files=False):
        self.common()
        changes = self._diff_changes(to_refpath, from_refpath)
        self.print(self._format_changes(changes, files=files))
        return changes
