from exchanges.requests import ClientRequest

__author__ = 'abhimanyu'

import endpoints
from protorpc import remote, message_types

class Asana(remote.Service):

    @endpoints.method(ClientRequest.Message,
                      ClientRequest.Message,
                      path='/asana/get_tasks',
                      http_method='POST',
                      name='get_tasks')
    def get_tasks(self, request):
        return ClientRequest.Message()
