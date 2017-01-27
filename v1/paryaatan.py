__author__ = 'manikanta'

import endpoints
import config
from v1.asana import Asana
sauron_api = endpoints.api(
    name='foss4gasia-challenge',
    version='v1',
    allowed_client_ids = [],
    audiences=[]
)

@sauron_api.api_class(resource_name='api')
class ParyaatanApi(Asana):
    pass
