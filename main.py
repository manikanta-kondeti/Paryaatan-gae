"""Main file where we define the application"""
import endpoints

from v1 import paryaatan as paryaatan_v1


app = endpoints.api_server([paryaatan_v1.ParyaatanApi])
