import endpoints


paryaatan_api = endpoints.api(
    name='paryaatan',
    version='v1',
    allowed_client_ids = [
    ],
    audiences=[]
)


@paryaatan_api.api_class(resource_name='api')
class ParyaatanApi():
    pass
