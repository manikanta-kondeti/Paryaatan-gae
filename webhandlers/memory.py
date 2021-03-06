import datetime
import webapp2
import jinja2
import os, json
import logging
from models.memory import MemoryEntity
import lib.cloudstorage as gcs
from google.appengine.api import app_identity

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

    def get(self):
        logging.log(logging.DEBUG, "HIT - GetUserMemoriesByKey")
        id = self.request.get('memory_id', None)
        logging.log(logging.DEBUG, self.request)
        memory_entity = MemoryEntity.get_by_id(id)
        if not id :
            return self.response.write("Failure: Please check the memory id you requested %s"%(id))

        memory_object = json.dumps({
            'memory_object':  dict(memory_entity.to_dict(),
                        **dict(key=memory_entity.key.id(),
                               created_at = DateTimeJSONEncoder().encode(memory_entity.created_at),
                               updated_at = DateTimeJSONEncoder().encode(memory_entity.updated_at)))
        })
        self.response.write(memory_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



class GetUserMemoriesByExtent(webapp2.RequestHandler):

    '''
        @param : {top_left_lat, top_left_lng, bottom_right_lat, bottom_right_lng, id}
    '''
    def get(self):
        '''
            logic:

        :return:
        '''
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

        memory_entity = MemoryEntity.insert_memory(
                    lat=self.request.POST.get('lat'),
                    lng = self.request.POST.get('lng'),
                    type_of_memory=self.request.POST.get('type_of_memory'),
                    description=self.request.POST.get('description'),
                    memory_file=self.request.POST.get('memory_file')
                )

        self.response.write(json.dumps({
                            "status" : "Succesfully Uploaded.. Keep adding!",
                            "memory_url" :  memory_entity.urlb
        }))
        logging.log(logging.DEBUG, 'Succesfully added memory into paryaatan..')
        return


class Hello(webapp2.RequestHandler):

    def get(self):
        self.response.write("Hello from paryaatan... backend started working!")

        bucket_name = os.environ.get('BUCKET_NAME',
                               app_identity.get_default_gcs_bucket_name())

        self.response.headers['Content-Type'] = 'text/plain'
        self.response.write('Demo GCS Application running from Version: '
                      + os.environ['CURRENT_VERSION_ID'] + '\n')
        self.response.write('Using bucket name: ' + bucket_name + '\n\n')

        """Create a file.

          The retry_params specified in the open call will override the default
          retry params for this particular file handle.

          Args:
            filename: filename.
        """
        filename = "/foss4gasia-challenge.appspot.com/poster/uploaded_files/testing.txt"
        self.response.write('Creating file %s\n' % filename)

        write_retry_params = gcs.RetryParams(backoff_factor=1.1)
        gcs_file = gcs.open(filename,
                          'w',
                          content_type='text/plain',
                          options={'x-goog-meta-foo': 'foo',
                                   'x-goog-meta-bar': 'bar'},
                          retry_params=write_retry_params)
        gcs_file.write('abcde\n')
        gcs_file.write('f'*1024*4 + '\n')
        gcs_file.close()


    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return

app = webapp2.WSGIApplication(
    [
        ('/hello', Hello),
        ('/get_user_memories_by_key', GetUserMemoriesByKey),
        ('/get_user_memories_by_extent', GetUserMemoriesByExtent),
        ('/post_upload_memory', UploadMemory)

    ],
    debug=True)
