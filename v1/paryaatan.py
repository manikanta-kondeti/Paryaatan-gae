import endpoints


marketplace_api = endpoints.api(
    name='paryaatan',
    version='v1',
    allowed_client_ids = [
    ],
    audiences=[]
)


@marketplace_api.api_class(resource_name='api')
class MarketPlaceApi():
    pass
