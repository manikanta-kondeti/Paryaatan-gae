"""Message classes to be used by the REST endpoint requests"""
from base import BaseMessage, MessageField


class ClientRequest(BaseMessage):
    """Base class for all messages to be received from the client"""
    FIELDS = [
        MessageField('device_id', 'string'),  # UUID of the device from which the request is made
        MessageField('user_id', 'string')  # User ID of the currently logged in user or None
    ]


class BatchedListRequest(ClientRequest):
    """Base class for all requests that want batched entities as the response"""
    FIELDS = [
        MessageField('cursor', 'string')  # Cursor for the batches that are being fetched for this client
    ]
