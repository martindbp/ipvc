from ipvc.common import CommonAPI

class ParamAPI(CommonAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def param(self, author):
        """ Sets a global parameter value """
        params = self.read_global_params()
        if author is not None:
            params['author'] = author

        self.write_global_params(params)
