from ipvc.common import CommonAPI, atomic

class ParamAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @atomic
    def param(self, author):
        """ Sets a global parameter value """
        params = self.read_global_params()
        if author is not None:
            params['author'] = author

        self.write_global_params(params)
