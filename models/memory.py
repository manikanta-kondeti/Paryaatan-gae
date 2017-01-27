import logging
import os
from config import get_random_id
from models.base import LocationEntity
from google.appengine.ext import ndb
from google.appengine.api import search
from models.enum import MemoryTypes
from storage import files
import datetime
from taskhandlers.app import create_location_index_for_memory
from google.appengine.ext.deferred import deferred

MEMORY_LOCATION_INDEX = "memory_location_index_v1"

class MemoryEntity(LocationEntity):

    description  = ndb.TextProperty()
    type_of_memory = ndb.TextProperty()
    url = ndb.TextProperty()
    address = ndb.TextProperty()

    @classmethod
    def insert_memory(cls, lat, lng, type_of_memory, description, memory_file):
        memory = cls()
        memory.description = description
        memory.lat = lat
        memory.lng = lng
        memory.type_of_memory = type_of_memory

        # insert blob in cloud storage
        memory.memory_url = "http://www.404notfound.fr/assets/images/pages/img/lego.jpg"
        if(memory_file != None and memory_file != ''):
            logging.log(logging.DEBUG, "memory_file = %s"%(memory_file))
            uploaded_file_name, ext = os.path.splitext(memory_file.filename.replace(' ',''))
            file_name = get_random_id(15) + ext
            path , mime_type = files.put_file("uploads/" + file_name, memory_file.file.read())
            memory_url = "http://storage.googleapis.com"+ path
            memory.memory_url = memory_url

        memory.put()
        logging.log(logging.DEBUG, "Succesfully inserted into memory entity")

        # Task handler to create location index
        try:
            deferred.defer(create_location_index_for_memory, memory_key=memory.key,
                                   _queue='MemorySearchIndexing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not search index for location:  task for %s' % memory.key.id())

        return memory


    @classmethod
    def get_search_index(cls):
        return MEMORY_LOCATION_INDEX

    @classmethod
    def insert_memory_in_search_index_by_key(cls, memory_key):
        memory = memory_key.get()

        memory_location = search.GeoPoint(memory.lat, memory.lng)
        fields = [search.TextField(name='key', value=memory_key.id()),
                  search.TextField(name='description', value=memory.description),
                  search.GeoField(name="location", value=memory.location),
                  search.DateField(name='created', value=datetime.datetime.utcnow().date())]

        search_doc = search.Document(doc_id=memory_key.id(), fields=fields)

        try:
            search_result = search.Index(name=cls.get_search_index()).put(search_doc)
        except search.Error:
            logging.log(logging.DEBUG, "Nothing to panic, Search Error")
            return False

        return True

    @classmethod
    def get_memories_by_extent(cls, lat, lng):
        # create extent and retrieve memory entities based on extent
        return

    @classmethod
    def get_memory_by_key(cls, memory_key):
        memory_entity = MemoryEntity.get_by_id(memory_key.id())
        return memory_entity

