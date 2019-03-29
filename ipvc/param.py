from ipvc.common import CommonAPI, atomic

class ParamAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def param(self, author):
        """ Sets a global parameter value """
        self._param(author, write_global=True)
