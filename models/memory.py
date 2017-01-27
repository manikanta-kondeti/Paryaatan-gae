import logging
import os
from config import get_random_id
from models.base import LocationEntity
from google.appengine.ext import ndb
from models.enum import MemoryTypes
from storage import files


class MemoryEntity(LocationEntity):

    description  = ndb.TextProperty()
    type_of_memory = ndb.IntegerProperty()
    url = ndb.TextProperty

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

        return

    @classmethod
    def get_memories_by_extent(cls, lat, lng):
        # create extent and retrieve memory entities based on extent
        return

    @classmethod
    def get_memory_by_key(cls, memory_key):
        memory_entity = MemoryEntity.get_by_id(memory_key.id())
        return memory_entity

