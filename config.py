"""Configuration parameters and constants"""
import hashlib
import datetime, random, string, time

__author__ = 'minocha'

# TODO: Replace the following lines with client IDs obtained from the APIs
# Console or Cloud Console.
#WEB_CLIENT_ID = '259129283998-r3poiejjr77keanli7b0l7g4m0uqbdi9.apps.googleusercontent.com'
#ANDROID_CLIENT_ID = '259129283998-5ibnhdbjjj4qeageqfnmgru3tilekrmc.apps.googleusercontent.com'
#IOS_CLIENT_ID = '259129283998-5ibnhdbjjj4qeageqfnmgru3tilekrmc.apps.googleusercontent.com'
#ANDROID_AUDIENCE = WEB_CLIENT_ID

DEFAULT_PAGE_LEN = 50

def get_random_id(length=10):
    '''returns a 10 character random string containing numbers lowercase upper case'''
    '''http://stackoverflow.com/questions/2257441/random-string-generation-with-upper-case-letters-and-digits-in-python'''

    key_str = ("%.15f" % time.time())+"-" + ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits+string.ascii_lowercase) for _ in range(length))
    key_str = hashlib.md5(key_str).hexdigest()
    return key_str
