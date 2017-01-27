import datetime
import webapp2
import jinja2
import os, json
import logging
from models.memory import MemoryEntity

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)

"""
  Paryaatan : paryaatan android application

"""

"""
class DateTimeJSONEncoder(json.JSONEncoder)

    To serialize response object: ( to_dict() is not working for datetime.datetime )
    The instance method takes datetime.datetime and just converts into .isoformat(), a string.

"""

class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        else:
            return super(DateTimeJSONEncoder, self).default(obj)



class GetUserMemoriesByKey(webapp2.RequestHandler):

    def get_(self):
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



class GetUserMemoriesByExtent(webapp2.RequestHandler):

    def get(self):
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



class UploadMemory(webapp2.RequestHandler):

    '''
        @:param : lat, lng, type_of_memory, description, memory_file
    '''
    def post(self):

        MemoryEntity.insert_memory(
                    lat=self.request.lat,
                    lng = self.request.lng,
                    type_of_memory=self.request.type_of_memory,
                    description=self.request.description,
                    memory_file=self.request.memory_file
                )
        self.response.write("Succesfully Uploaded.. Keep adding!")

        return


class Hello(webapp2.RequestHandler):

    def get(self):
        self.response.write("Hello from paryaatan... backend started working!");
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return

app = webapp2.WSGIApplication(
    [
        ('/hello', Hello),
        ('/get_user_memories_by_key', GetUserMemoriesByKey),
        ('get_user_memory_by_key', GetUserMemoriesByExtent),
        ('/post_upload_memory', UploadMemory)

    ],
    debug=True)
