"""Nobody's going to like this, but this is the world we live in"""
from collections import namedtuple
from types import ClassType, ModuleType

from google.appengine.ext import ndb
from protorpc import messages, message_types

from util import ClassProperty


class SimpleTypes(object):
    """
    Our simplified type definitions for easier message property descriptions
    and model-message bridging
    """
    BOOL = 'bool'
    DATETIME = 'datetime'
    ENUM = 'enum'
    FLOAT = 'float'
    INT = 'int'
    MESSAGE = 'message'
    STRING = 'string'

# Defining our own types for messages - We'll also use this to map Models directly to messages
MESSAGE_TYPE_MAP = {
    SimpleTypes.BOOL: messages.BooleanField,
    SimpleTypes.DATETIME: message_types.DateTimeField,
    SimpleTypes.ENUM: messages.EnumField,
    SimpleTypes.FLOAT: messages.FloatField,
    SimpleTypes.INT: messages.IntegerField,
    SimpleTypes.MESSAGE: messages.MessageField,
    SimpleTypes.STRING: messages.StringField,
}

# NDB Property types to our own types mapping
_EQUIVALENT_TYPES = {
    SimpleTypes.BOOL: [ndb.BooleanProperty],
    SimpleTypes.DATETIME: [ndb.DateProperty, ndb.DateTimeProperty],
    SimpleTypes.FLOAT: [ndb.FloatProperty],
    SimpleTypes.INT: [ndb.IntegerProperty],
    SimpleTypes.STRING: [ndb.StringProperty, ndb.TextProperty, ndb.JsonProperty]
}
NDB_PROPERTY_TYPE_MAP = {
    prop.__name__: stype for stype, props in _EQUIVALENT_TYPES.iteritems() for prop in props
}


class UnsupportedMessageClassError(Exception):
    pass


class InvalidMessageFieldError(Exception):
    pass


class MessageField(namedtuple(
    'NTMessageField', ['name', 'type', 'default', 'repeated', 'enum_type', 'message_type', 'required'])):
    """
    Our own message field descriptor
    name is the name of the field - property name if we were to go the real message way
    type is the the simplified string representation of the type
    default is the default value to be returned when field is not present in the message - defaults to None
    repeated tells whether or not the field repeats - defaults to False
    enum_type is a subclass of Enum - should be set for 'enum' type, will default to None if not set
    message_type is a subclass of Message - should be set for 'message' type, will default to None if not set
    """
    def __new__(cls, name, type, default=None, repeated=False, enum_type=None, message_type=None, required=False):
        """Overriding the named tuple new so that we can pass default values and do some validations"""
        if type not in MESSAGE_TYPE_MAP:
            raise InvalidMessageFieldError('Unknown type <%s> for the field <%s>' % (type, name))

        if type == 'enum' and enum_type is None:
            raise InvalidMessageFieldError('Enum field <%s> declared without specifying the type' % name)

        if type == 'message' and message_type is None:
            raise InvalidMessageFieldError('Message field <%s> declared without specifying the type' % name)

        if required and repeated:
            raise InvalidMessageFieldError('Field cannot be both required and repeated')

        if default and type in ('message', 'datetime'):
            raise InvalidMessageFieldError('Field of type <%s> cannot have a default' % type)

        return super(MessageField, cls).__new__(cls, name, type, default, repeated, enum_type, message_type, required)


# Messages
class BaseMessage(object):
    """Base class that all of our messages inherit from"""

    # Sub classes should just specify this, aside from any custom behavior
    FIELDS = []

    @classmethod
    def _all_fields(cls):
        """Returns list of all fields of this message and everything else inherited"""
        fields = []
        for ancestor in cls.mro():
            if hasattr(ancestor, '_all_fields'):
                fields.extend(ancestor.FIELDS)
        return fields

    @classmethod
    def _as_message(cls):
        """Returns the real Message class"""
        return messagify(cls)

    @ClassProperty
    def Message(cls):
        """Message class for this class"""
        if not hasattr(cls, '_message'):
            cls._message = cls._as_message()
        return cls._message


# The real stuff - Turns our pseudo message classes (children of BaseMessage) into real Messages
def messagify(kls):
    """
    Decorator/Method for our own message classes that injects our custom fields as real fields
    Example:
    @messagify
    class FooMessage(BaseMessage):
        FIELDS = [
            MessageField('user_id', 'string'),
            MessageField('platform', )
        ]
    """
    if not issubclass(kls, BaseMessage):
        raise UnsupportedMessageClassError("Cannot messagify the given class: %s" % kls)

    # All children of BaseMessage will/should have _all_fields method
    sorted_fields = sorted(kls._all_fields())
    generated_properties = {}
    for i, field in enumerate(sorted_fields, start=1):
        args = [i]
        kwargs = {'default': field.default, 'repeated': field.repeated}
        if field.type == 'enum':
            args = [field.enum_type, i]
        if field.type == 'message':
            args = [field.message_type, i]
            del kwargs['default']
        if field.type == 'datetime':
            del kwargs['default']

        generated_properties[field.name] = MESSAGE_TYPE_MAP[field.type](*args, **kwargs)

    return type(kls.__name__, (messages.Message,), generated_properties)


# No longer used beyond this, leaving it in here anyway. Might come in handy

# Helper for following factory class
def is_valid_message_class(kls):
    """Returns whether or not the argument is a class at all and a subclass of our BaseMessage"""
    return isinstance(kls, (type, ClassType)) and issubclass(kls, BaseMessage)


class MessageFactory(object):
    """Factory to spit out Message classes that aren't otherwise real classes"""

    def __init__(self, contexts):
        """
        Contexts should be modules we want to generate Messages out of - used for namespacing in ProtoMessage
        """
        self.contexts = contexts
        self.classes = {}

        for context in contexts:
            if not isinstance(context, ModuleType):
                # Freak out
                raise Exception("Provided context <%s> is not a module")

            for prop_name in dir(context):
                prop = getattr(context, prop_name, None)
                if is_valid_message_class(prop):
                    if prop.__name__ in self.classes:
                        raise Exception("You have conflicting message classes defined in %s" % self.contexts)
                    self.classes[prop.__name__] = prop

    def __getattr__(self, item):
        """Overriding to return the real Messages as opposed to our pseudo messages"""
        if item not in self.classes:
            raise AttributeError("Class <%s> not found in %s" % (item, self.contexts))

        return self.classes[item].Message
