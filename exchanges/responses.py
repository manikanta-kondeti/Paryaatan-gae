"""Message classes to be used for the REST endpoint responses"""
from base import BaseMessage, MessageField, NDB_PROPERTY_TYPE_MAP
from util import ClassProperty

from google.appengine.ext import ndb

from util import identity


class BaseResponse(BaseMessage):
    """Base class for all response messages"""
    FIELDS = []


class BooleanResponse(BaseResponse):
    """
    Response message for when client requests a
    YES or NO question (eg. whether a voice is hearted etc.)
    """
    FIELDS = [
        MessageField('value', 'bool')  # Value will be the answer to client's question
    ]


class BatchedListResponse(BaseResponse):
    """
    Response to client's requests for batched objects
    """
    FIELDS = [
        MessageField('cursor', 'string'),  # Web safe ndb query cursor for pagination
        MessageField('more', 'bool')  # Flag indicating whether or not more results are available
    ]


class ModelBasedResponse(BaseResponse):
    """
    Base class to define Messages that are client-facing representations of Models

    'model' property should be overriden to return the desired model class

    FIELDS property gets overriden in child classes - specify extra non-model fields in additional_fields method
    FIELDS from ancestors however is preserved.
    """
    # To skip over this while accumulating fields
    __abstract__ = True

    @ClassProperty
    def model(cls):
        """Returns the Model class this message represents"""
        raise NotImplementedError

    @ClassProperty
    def omitted_properties(cls):
        """Returns list of names of the properties on the model that we want to omit from sending to client"""
        return []

    @ClassProperty
    def additional_fields(cls):
        """Returns list of MessageFields we want to send in addition to the non-omitted properties on the model"""
        return []

    @classmethod
    def _applicable_properties(cls):
        """Caches and returns list of properties that we care about on the model"""
        if not hasattr(cls, '_model_properties'):
            props = {}
            skip_properties = set(cls.omitted_properties)
            for name, prop in cls.model._properties.items():
                if name in skip_properties:
                    continue
                props[name] = prop
            cls._model_properties = props

        return cls._model_properties

    @classmethod
    def _all_fields(cls):
        """
        Overriding because otherwise the chain accumulation breaks at the NotImplemented methods in this class
        """
        fields = super(ModelBasedResponse, cls)._all_fields()

        def property_to_field(n, p):
            """n is the name and p is the actual property object"""
            field_type = NDB_PROPERTY_TYPE_MAP.get(p.__class__.__name__)
            if not field_type:
                raise Exception('Do not know how to interpret %s in a message directly' % p.__class__.__name__)

            attr = lambda x: getattr(p, x, None)
            return MessageField(n, field_type, default=attr('_default'),
                                repeated=attr('_repeated'), required=attr('_required'))

        fields.extend([property_to_field(name, prop) for name, prop in cls._applicable_properties().iteritems()])
        fields.extend(cls.additional_fields)
        return fields

    @classmethod
    def from_entity(cls, entity, **kwargs):
        """
        Returns the message object that can be sent back to client

        kwargs should correspond to the additional fields if additional fields specified
        """
        if not isinstance(entity, cls.model):
            raise Exception('Passed instance of <%s>, but <%s> is expected' % (entity.__class__.__name__,
                                                                               cls.model.__name__))
        values = {}
        for name in cls._applicable_properties().keys():
            val = getattr(entity, name, None)
            transform = cls.custom_transforms.get(name, identity)
            values[name] = transform(val)

        return cls.Message(**dict(values, **kwargs))

    @classmethod
    def for_id(cls, id_, **kwargs):
        """Returns the message form of the entity with given id"""
        cls.from_entity(cls.model.get_by_id(id_), **kwargs)

    @ClassProperty
    def custom_transforms(cls):
        """
        Returns a dict mapping NDB Model property to a transform function

        Value of that property on the entity will be passed through corresponding transform
        and return value of the function is passed as the value to the message constructor
        """
        return {}


class ModelBasedCollectionResponse(BatchedListResponse):
    """
    Base class for batched response of Model based messages

    Has only three fields
    'error' - inherited from BaseResponse
    'cursor' - inherited from BatchedListResponse
    '<cls.collection_name>' - specified by sub classes, viz. the name that represents the list of objects
    """
    @ClassProperty
    def message_class(cls):
        """
        Returns the message class that this message carries a list of
        Eg. VoiceMessage
        """
        raise NotImplementedError

    @ClassProperty
    def collection_name(cls):
        """
        Returns the name of the field that represents the list of model based messages
        Eg. 'voices'
        """
        raise NotImplementedError

    @classmethod
    def _all_fields(cls):
        """Overriding to turn it into the Message with three fields"""
        fields = super(ModelBasedCollectionResponse, cls)._all_fields()
        return fields + [
            MessageField(cls.collection_name, 'message', default=[], repeated=True,
                         message_type=cls.message_class.Message)
        ]

    @classmethod
    def message_list_from_entities(cls, entities):
        """Returns the list of model based messages for given entities"""
        return map(lambda e: cls.message_class.from_entity(e), entities)

    @classmethod
    def for_query(cls, query, page_size, cursor=None):
        """Returns the fully formed response message for the given query, page size and cursor"""
        if isinstance(cursor, basestring):
            cursor = ndb.Cursor.from_websafe_string(cursor)
        entities, next_cursor, more = query.fetch_page(page_size, start_cursor=cursor)

        kwargs = {
            cls.collection_name: cls.message_list_from_entities(entities),
            'cursor': next_cursor.to_websafe_string() if next_cursor else None,
            'more': more
        }
        return cls.Message(**kwargs)
