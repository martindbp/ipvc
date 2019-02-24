from pathlib import Path
from ipvc.common import CommonAPI

class DiffAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def run(self, to_refpath=Path("@workspace"), from_refpath=Path("@stage"), files=False):
        self.common()
        return self._diff(to_refpath, from_refpath, files)
