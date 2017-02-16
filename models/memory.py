import logging
import os
from config import get_random_id
from models.base import LocationEntity
from google.appengine.ext import ndb
from google.appengine.api import search
from models.enum import MemoryTypes
from storage import files
import datetime
from storage.files import unicode_to_string

MEMORY_LOCATION_INDEX = "memory_location_index_v1"

class MemoryEntity(LocationEntity):

    description  = ndb.TextProperty()
    type_of_memory = ndb.TextProperty()
    url = ndb.TextProperty()
    address = ndb.TextProperty()

    @classmethod
    def insert_memory(cls, lat, lng, type_of_memory, description, memory_file):
        memory = cls()
        memory.description = str(description)
        memory.lat = float(lat)
        memory.lng = float(lng)
        memory.type_of_memory = str(type_of_memory)

        # insert blob in cloud storage
        memory.memory_url = "http://www.404notfound.fr/assets/images/pages/img/lego.jpg"
        if(memory_file != None and memory_file != ''):

            image_contents = memory_file
            file_extension = ".jpg"
            id = get_random_id(15)
            file_name = "/foss4gasia-challenge.appspot.com/poster/uploaded_files/" +id + file_extension
            image_contents = unicode_to_string(image_contents)
            if image_contents == '':
                memory.memory_url = "http://www.404notfound.fr/assets/images/pages/img/lego.jpg"
                memory.put()
                return
            files.store_image_file(file_name, image_contents)
            memory_url = "http://storage.googleapis.com" + file_name

        memory.put()
        logging.log(logging.DEBUG, "Succesfully inserted into memory entity")

        memory.insert_memory_in_search_index_by_key(memory.key)

        return memory


    @classmethod
    def get_search_index(cls):
        return MEMORY_LOCATION_INDEX

    @classmethod
    def insert_memory_in_search_index_by_key(cls, memory_key):
        memory = memory_key.get()

        memory_location = search.GeoPoint(memory.lat, memory.lng)
        fields = [search.TextField(name='key', value=str(memory_key.id())),
                  search.TextField(name='description', value=memory.description),
                  search.GeoField(name="location", value=memory_location),
                  search.DateField(name='created', value=datetime.datetime.utcnow().date())]

        search_doc = search.Document(doc_id=str(memory_key.id()), fields=fields)

        try:
            search.Index(name=cls.get_search_index()).put(search_doc)
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

