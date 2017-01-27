import json
import logging
import random
import re
import urllib2
from google.appengine.ext import ndb
#from models.user import PhonenumberEntity
__author__ = 'mani'

"""
def fetch_phone_number(access_token, user_id):
    '''

    :param user_id:
    :return:  Update user entity with phone number, national number and country code.
    '''
    phonenumber_details = json.loads(urllib2.urlopen("https://graph.accountkit.com/v1.0/me/?access_token=%s"%(access_token)).read())

    user_entity = UserEntity.get_by_id(user_id)
    if not user_entity:
        return
    user_entity.phonenumber = phonenumber_details['phone']['number']
    user_entity.country_code = phonenumber_details['phone']['country_prefix']
    user_entity.national_number = phonenumber_details['phone']['national_number']

    user_entity.put()

    return

def extract_address_from_latlon(key, latitude, longitude):
    '''

    :param key: key of the entity
    :param latitude: latitude of the product
    :param longitude: longitude of the product
    :return:
     url for geocoding : http://maps.google.com/maps/api/geocode/json?latlng=<lat><lon>&sensor=false
    '''

    logging.log(logging.DEBUG, " for product posted with id = %s"%(key.id()))
    product_entity = key.get()

    if not product_entity:
        return

    if latitude != 0.0 and longitude != 0.0:
        lat_lon = str(latitude) + "," + str(longitude)
        address = json.loads(urllib2.urlopen("http://maps.google.com/maps/api/geocode/json?latlng=%s"%(lat_lon)).read())
        new_address = ''
        if len(address["results"]) != 0:
            for i in range(0, len(address["results"][0]["address_components"])):
                if 'sublocality' in address["results"][0]["address_components"][i]['types']:
                    new_address = new_address + ", " + address["results"][0]["address_components"][i]['short_name']

        if not new_address:
            return

        product_entity.location = new_address
        product_entity.put()

    return




def create_location_index_for_memory(memory_key):
    '''

    :param product_key_id: key of the product posted
    :param product_location: location of the product posted
    :return:
    '''

    logging.log(logging.DEBUG, "Creating index for memory posted with id = %s"%(memory_key.id()))
    MemoryEntity.insert_product_in_search_index_by_key(memory_key)

    return
"""



