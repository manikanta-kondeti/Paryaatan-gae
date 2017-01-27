from collections import defaultdict
import hashlib
import collections
from google.appengine.api import memcache
from google.appengine.api.taskqueue import taskqueue
from google.appengine.ext.deferred import deferred
import operator
from google.appengine.ext.ndb import get_multi
import jinja2
import webapp2
import re
import config
from exchanges.channels import ChannelInfoResponse
from exchanges.expressions import ExpressionListResponse, ExpressionEntityCounterLogResponse, ExpressionResponse
from models.enums import PushNotificationTypes, Push_Notification_Channel_Types, Push_Notification_Social_Types, \
    Push_Notification_User_Upload_Types
from models.expressions import UnApprovedExpressionEntity, ExpressionEntity, ALL_LANGUAGES, ExpressionEntityCounter, ExpressionEntityRank, \
    ExpressionType, ALL_LANGUAGES_WITH_GLOBAL, ExpressionEntityCounterLog
from models.search import SearchTags
from google.appengine.datastore.datastore_query import Cursor
from google.appengine.api import users
import logging
from google.appengine.ext import ndb
import json
import datetime
from models.push_notification import PushNotificationEntity
from models.users import InstallationEntity, UserEntity, TrackedType, UserType
from models.user_profile import UserNotificationEntity, Notification
from utils.add_new_semantic_relation import add_movie_to_expression, add_actor_to_expression
from utils.channel_notifications import add_task_for_new_content_to_channel
from utils.default_channels import make_new_actor_channel, make_new_movie_channel
from utils.memcache_channels_data import clear_channel_memcache_data
from utils.metrics import CHANNEL_METRICS_MEMCACHE_KEY, calculate_channel_metrics
from utils.ndb_utils import fetch_all_entities
from utils.notifications import send_notifications_by_user_keys
from utils.dashboard_utils import adding_actor_movie_to_expression
from models.search import SearchTags,UserQueryNoResults,SearchQueryFrequency
from models.semantic_tags import ActorEntity, MovieEntity, ActorMovieRelationshipEntity
from models.counters import CounterEntity
from mapreducer.map import create_actor_search, create_movie_search
from models.counters import CounterEntity
import os
from config import get_random_id
from storage import files
from models.analytics import UserLogEntity
from models.channels import ChannelEntity, BroadcastEntity, ChannelType
from utils.image_processing import process_unapproved_expression_entity_image
from utils.auth import webhandler_auth
from protorpc import protojson
from utils.processing_utils import batch


JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)
"""
  Dashboard:
    To approve content uploaded by users.
    To see the trend change for every 30 minutes

"""


"""
class DateTimeJSONEncoder(json.JSONEncoder)

    To serialize response object: ( to_dict() is not working for datetime.datetime )
    The instance method takes datetime.datetime and just converts into .isoformat(), a string.

"""

class DateTimeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime) or isinstance(obj, datetime.date):
            return obj.isoformat()
        else:
            return super(DateTimeJSONEncoder, self).default(obj)




"""
Access:
    Only for admins(who have access to Cloud Platform)

Advantages:
    We don't have to write an endpoint for doing this.
    Also it is part of admin's work, so we shouldn't expose this data and fetching via an endpoint.

Flow:
    Request handler has a method get() which has request params passed.
    unapproved_content_request_from_client() : It is a method that queries UnApprovedExpressionEntity and serialize the
            response into json. That response_object is sent as a response to the request

"""


class DashboardGet(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.unapproved_content_request_from_client(user)
        return


    def unapproved_content_request_from_client(self, user):

        """
        This method's request will have the cursor parameter(optional). It fetches UnApprovedExpressionEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                1. UnApprovedExpressionEntities
                2. cursor_response
                3. more
        """
        cursor_request = Cursor(urlsafe=self.request.get('cursor',None))
        # These below two params are filters on approval dashboard
        language = self.request.get('language', None)
        expression_type = self.request.get('type', None)
        logging.log(logging.DEBUG, "language = %s"%(language))
        logging.log(logging.DEBUG, "type = %s"%(expression_type))
        if language == "All":
            language = None
        if expression_type == "All":
            expression_type = None

        cursor_response = Cursor()
        more = True
        entities = []

        if language != None and expression_type == None:
            entities, cursor_response, more = UnApprovedExpressionEntity.\
                                                query(UnApprovedExpressionEntity.approval_status == 0, UnApprovedExpressionEntity.language == language).\
                                                order(-UnApprovedExpressionEntity.created_at).\
                                                fetch_page(100,start_cursor=cursor_request)

        elif expression_type != None and language == None:
            entities, cursor_response, more = UnApprovedExpressionEntity.\
                                                query(UnApprovedExpressionEntity.approval_status == 0, UnApprovedExpressionEntity.type == int(expression_type) ).\
                                                order(-UnApprovedExpressionEntity.created_at).\
                                                fetch_page(100,start_cursor=cursor_request)

        elif language == None and expression_type == None:
            entities, cursor_response, more = UnApprovedExpressionEntity.\
                                                query(UnApprovedExpressionEntity.approval_status == 0).\
                                                order(-UnApprovedExpressionEntity.created_at).\
                                                fetch_page(100,start_cursor=cursor_request)
        elif language != None and expression_type != None:
            entities, cursor_response, more = UnApprovedExpressionEntity.\
                                                query(UnApprovedExpressionEntity.approval_status == 0, UnApprovedExpressionEntity.language == language, UnApprovedExpressionEntity.type == int(expression_type) ).\
                                                order(-UnApprovedExpressionEntity.created_at).\
                                                fetch_page(100,start_cursor=cursor_request)
        if not cursor_response:
            cursor_response = Cursor()
        # Creates a json object for transmission and to avoid Origin Access Control

        response_object = json.dumps({
            'cursor': cursor_response.urlsafe(),
            'more': more,
            'voices':  [dict(p.to_dict(),
                        **dict(key=p.key.id(), user_key=p.user_key.id(),
                               actor_key=p.actor_key.id() if p.actor_key else None,
                               movie_key=p.movie_key.id() if p.movie_key else None,
                               approved_expression_key=p.approved_expression_key.id() if p.approved_expression_key else None,
                               created_at=DateTimeJSONEncoder().encode(p.created_at),
                               updated_at=DateTimeJSONEncoder().encode(p.updated_at)))
                    for p in entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'



class DashboardRejected(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.rejected_content_request_from_client(user)
        return


    def rejected_content_request_from_client(self, user):

        """
        This method's request will have the cursor parameter(optional). It fetches UnApprovedExpressionEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                1. UnApprovedExpressionEntities
                2. cursor_response
                3. more
        """
        cursor_request = Cursor(urlsafe=self.request.get('cursor',None))
        entities, cursor_response, more = UnApprovedExpressionEntity.\
                                          query(UnApprovedExpressionEntity.approval_status == 2).\
                                          order(-UnApprovedExpressionEntity.created_at).\
                                          fetch_page(500,start_cursor=cursor_request)

        # Creates a json object for transmission and to avoid Origin Access Control

        response_object = json.dumps({
            'cursor': cursor_response.urlsafe(),
            'more': more,
            'voices':  [dict(p.to_dict(),
                        **dict(key=p.key.id(), user_key=p.user_key.id(),
                               actor_key=p.actor_key.id() if p.actor_key else None,
                               movie_key=p.movie_key.id() if p.movie_key else None,
                               approved_expression_key=p.approved_expression_key.id() if p.approved_expression_key else None,
                               created_at=DateTimeJSONEncoder().encode(p.created_at),
                               updated_at=DateTimeJSONEncoder().encode(p.updated_at)))
                    for p in entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


class DashboardGetUnapprovedClip(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.unapproved_clip_content_request_from_client(user)
        return


    def unapproved_clip_content_request_from_client(self, user=None):

        """
        This method's request will have the expression key parameter(optional). It fetches UnApprovedExpressionEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                1. UnApprovedExpressionEntity
        """
        expression_key = self.request.get('expression_key')
        entity = UnApprovedExpressionEntity.get_by_id(expression_key)

        if not entity:
            self.response.write(json.dumps({
                "status" : "Not a valid expression key..!"
            }))
            logging.log(logging.DEBUG, "Fetching unapproved expression entity. Not a valid key passed")
            return

        # Creates a json object for transmission and to avoid Origin Access Control

        response_object = json.dumps({
            'voices':  dict(entity.to_dict(),
                        **dict(key=entity.key.id(), user_key=entity.user_key.id(),
                               actor_key=entity.actor_key.id() if entity.actor_key else None,
                               movie_key=entity.movie_key.id() if entity.movie_key else None,
                               created_at=DateTimeJSONEncoder().encode(entity.created_at),
                               updated_at=DateTimeJSONEncoder().encode(entity.updated_at)))
        })
        logging.log(logging.DEBUG, "Successfully fetched unapproved entity based on key.")
        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


class DashboardPostEditedUnapprovedClip(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def post(self, user):
        """ post """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.unapproved_clip_edited_content_from_client(user)
        return

    def unapproved_clip_edited_content_from_client(self):

        """
        This method's request will have the expression key parameter(optional). It fetches UnApprovedExpressionEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                'status'
        """
        expression_key = self.request.get('expression_key')
        tags_before_split = self.request.get_all('tags[]')
        tags = tags_before_split[0].split(',')
        transcript = self.request.get('transcript')
        caption = transcript.replace(' ','-')
        language = self.request.get('language')
        # TODO: poster url
        image_file = self.request.POST.get('file')
        actor = self.request.get('actor')
        movie = self.request.get('movie')

        # Fetching actor and movie keys
        if actor:
            actor_entity = ActorEntity.get_by_id(actor)
            if not actor_entity:
                self.response.write(json.dumps({
                    "status": "Check the actor key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "No Check the actor key again and create a new relation")
                return

        if movie:
            movie_entity = MovieEntity.get_by_id(movie)
            if not movie_entity:
                self.response.write(json.dumps({
                    "status": "Check the movie key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "Check the actor key again and create a new relation")
                return

        if language not in ALL_LANGUAGES and language != 'global':
            # send an error saying language is not correct
            self.response.write(json.dumps({
                "status" : "language is not correct"
            }))
            logging.log(logging.DEBUG, "In dashboard.py, PostEditUnapprovedExpression: Not a valid language")
            return


        unapproved_entity = UnApprovedExpressionEntity.get_by_id(expression_key)
        # To ensure that this clip is not reviewed two times
        if unapproved_entity.approval_status != 0:
            self.response.write({
                "status" : "This clip is already reviewed.. Please reload the page"
            })
            logging.log(logging.DEBUG, "This clip is already reviewed, please reload the page")
            return

        if not unapproved_entity:
            self.response.write(json.dumps({
                "status": "Not a valid key"
            }))
            logging.log(logging.DEBUG, "Not a valid key, please check the key")
            return

        if(image_file != None and image_file != ''):
            logging.log(logging.DEBUG, "image_file = %s"%(image_file))
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ',''))
            file_name = get_random_id(15) + ext
            path , mime_type = files.put_file("uploads/" + file_name, image_file.file.read())
            image_url = "http://storage.googleapis.com"+ path
            unapproved_entity.poster_url = image_url

        #  Adding actor and movie keys to expression entity from dashboard utils in utils.py
        unapproved_entity = adding_actor_movie_to_expression(actor, movie, unapproved_entity.key.id(), kind="unapproved_expression")
        unapproved_entity.tags = tags
        unapproved_entity.transcript = transcript
        unapproved_entity.language = language
        unapproved_entity.caption = caption

        unapproved_entity.put()

        # ImageProcessing: Create thumbnail for this unapproved expression
        try:
            deferred.defer(process_unapproved_expression_entity_image, unapproved_entity.key.id(),
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % unapproved_entity.key.id())

        # response
        response_object = json.dumps({
            "status" : "Successfully updated this unapproved expression..You can Approve it now!"
        })
        logging.log(logging.DEBUG, "Successfully edited an Unapproved Expression")
        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'




class DashboardPost(webapp2.RequestHandler):
    """
        To handle post request, when the entity is approved or rejected
    """
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'

        self.unapproved_response_from_client(user)
        return

    def unapproved_response_from_client(self, user):
        """
        This method gets a request from client having a key of the UnApprovedExpressionEntity and status field(integer)
            0 - UnApproved
            1 - Approved
            2 - Rejected
        :return: response_object will have a status field of Success, Failed.
        """


        #Reject Reasons have been defined in the frontend.
        reject_reason = self.request.POST.get('reject_reason')
        expression_key = self.request.POST.get('expression_key')
        expression_approval_status = int(self.request.POST.get('approval_status'))

        # Defining counter_value_set dictionary
        counter_value_set = {}

        """ Cases based on approval status :: Approved-1, Rejected-2 """

        if expression_approval_status == 1:

            # Approved:  Change UnApproved.approval_status=1, insert it into ExpressionEntity
            unapproved_entity = UnApprovedExpressionEntity.get_by_id(expression_key)
            # Validation of both opus_url and mp3_url
            if not unapproved_entity.opus_url or not unapproved_entity.mp3_url:
                self.response.write(json.dumps({
                    "status": "Opus_URL or mp3_URL is missing for this expression. Please contact admin immediately and ignore this for now"
                }))
                return

            # 1 ExpressionEntity insert
            try:
                unapproved_entity_approved = UnApprovedExpressionEntity.insert_or_update_unapproved_entity(None,
                                                        unapproved_entity.caption,
                                                        unapproved_entity.duration, unapproved_entity.hearts,
                                                        unapproved_entity.is_published_by_user,
                                                        unapproved_entity.is_tag_review_complete,
                                                        unapproved_entity.language, unapproved_entity.listens,
                                                        unapproved_entity.mp3md5, unapproved_entity.shares,
                                                        unapproved_entity.tags, unapproved_entity.transcript,
                                                        unapproved_entity.audio_name,
                                                        unapproved_entity.opus_url, unapproved_entity.mp3_url,
                                                        unapproved_entity.poster_url, unapproved_entity.thumbnail_url,
                                                        unapproved_entity.user_key, unapproved_entity.quote_src,
                                                        unapproved_entity.search_doc_id,
                                                        unapproved_entity.speaker_audience_relation, unapproved_entity.actor_key,
                                                        unapproved_entity.movie_key,
                                                        save_in_ds=False)
                unapproved_entity.approval_status = 1
                ExpressionEntity.add_default_image(unapproved_entity)
                unapproved_entity.approved_expression_key = unapproved_entity_approved.key
                #storing approved entity key here
                unapproved_entity.put()
                unapproved_entity_approved.type = unapproved_entity.type
                unapproved_entity_approved.put()

            # 2 Insert expression entity into search tag
                SearchTags.insert_search(unapproved_entity_approved)

            # 3 Create new push notification
                push_notification = PushNotificationEntity.create_notification_after_approval_to_single_user(unapproved_entity_approved.key.id())

            # 4 Get user's installation keys
                installation_keys = InstallationEntity.query(InstallationEntity.\
                                    user==unapproved_entity_approved.user_key).\
                                    fetch(keys_only=True)

            # 5 Send push notification to the above fetched installation keys
                user_keys = [unapproved_entity_approved.user_key]
                #send_notifications_by_user_keys(push_notification.key.id(), user_keys=user_keys, force=True)
                deferred.defer(send_notifications_by_user_keys, push_notification_id=push_notification.key.id(), user_keys=user_keys,
                               force=True, _queue='Notifications')

            # 6 Add notification to the user on his notification feed
                UserNotificationEntity.add_notification(unapproved_entity_approved.user_key, unapproved_entity_approved.key, Notification.APPROVAL, None)

            # 7 Updating counts
                user = unapproved_entity_approved.user_key.get()
                user.num_posts = user.num_posts + 1 if user.num_posts else 1
                user.num_unapproved_posts = user.num_unapproved_posts - 1 if user.num_unapproved_posts and user.num_unapproved_posts > 0 else 0
                user.put()

             # 8 Adding counters
                counter_value_set['uploads_approved'] = 1
                DashboardPost.update_counters(counter_value_set,
                                                                    language=unapproved_entity_approved.language,
                                                                    type=unapproved_entity_approved.type,
                                                                    status="approved")

                self.response.write(json.dumps({
                   "status": "Successfully added this upload to the feed(ExpressionEntity)..!!"
                }))

            except Exception as e:
                logging.error(e.message)

        elif expression_approval_status == 2:
            # 1. Rejected: Change UnApproved.approval_status=2
            unapproved_entity = UnApprovedExpressionEntity.get_by_id(expression_key)
            unapproved_entity.approval_status=2
            unapproved_entity.tags = [reject_reason]
            unapproved_entity.put()
            # 2. Send push notification
            push_notification = PushNotificationEntity.create_notification_after_rejection_to_single_user(unapproved_entity.key.id(), reject_reason)
            # 3. Fetch installation keys
            installation_keys = InstallationEntity.query(InstallationEntity.\
                                    user==unapproved_entity.user_key).\
                                    fetch(keys_only=True)
            # 4. Send push notification to the above fetched installation keys
            user_keys = [unapproved_entity.user_key]
            logging.log(logging.DEBUG,"User keys in dashboard %s"%user_keys)
            deferred.defer(send_notifications_by_user_keys, push_notification_id=push_notification.key.id(),
                           user_keys=user_keys, force=True, _queue='Notifications')
            #send_notifications_by_user_keys(push_notification.key.id(), user_keys=user_keys, force=True)

            # 5. Updating counters
            language = unapproved_entity.language
            if language not in ALL_LANGUAGES:
                language = None

            counter_value_set['uploads_rejected'] = 1
            DashboardPost.update_counters(counter_value_set,
                                                                language=language,
                                                                type=unapproved_entity.type,
                                                                status="rejected")
            
            self.response.write(json.dumps({
                "status": "Expression Rejected.. !"
            }))

        # Increment counters and return
        CounterEntity.incr_multi(counter_value_set)

        return

    @classmethod
    def update_counters(cls,counter_values,language,type,status):
        '''
        :param counter_values: Dictionary which has the values for updating counters
        :param language: language of the approved expression
        :param type: type of the approved expression
        :param status: whether approved or rejected
        :return:
        '''

        if type == 0 : #audio
            counter_values['uploads_%s_%s_audio'%(status,language)] = 1
        if type == 1 : #quote
            counter_values['uploads_%s_%s_quote'%(status,language)] = 1
        if type == 2 : #photo
            counter_values['uploads_%s_%s_photo'%(status,language)] = 1

        return counter_values

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


"""
    This dashboard handler is used to map actor, movie keys to expressions.
"""
class DashboardPostActorMovie(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ Post request """
        self.insert_actor_movie_to_expressions(user)

    def insert_actor_movie_to_expressions(self, user):
        """
        :return: status = success or failed
        """
        expression_id_list = self.request.get_all('expression_keys[]')
        actor = self.request.get('actor')
        movie = self.request.get('movie')
        movie_entity = None
        actor_entity = None

        # If we receive a empty list of expressions
        if not expression_id_list:
            self.response.write(json.dumps({
                "status": "failed due to empty expression list",
                "actor":actor,
                "movie":movie
            }))
            logging.log(logging.DEBUG, "Expression id'sare not passed - Dashboard handler for inserting actor, movie")
            return

        # If actor and movie is not present in the request
        if not actor and not movie:
            self.response.write(json.dumps({
                "status": "failed due to actor and movie is None"
            }))
            logging.log(logging.DEBUG, "failed due to actor and movie is None")
            return

        # Fetching actor and movie keys
        if actor:
            actor_entity = ActorEntity.get_by_id(actor)
            if not actor_entity:
                self.response.write(json.dumps({
                    "status": "Check the actor key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "No Check the actor key again and create a new relation")
                return

        if movie:
            movie_entity = MovieEntity.get_by_id(movie)
            if not movie_entity:
                self.response.write(json.dumps({
                    "status": "Check the movie key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "Check the actor key again and create a new relation")
                return

        expressions = ndb.get_multi(map(lambda x: ndb.Key('ExpressionEntity', str(x)), expression_id_list))
        if expression_id_list:
            """ Insert into ds, update expressions """
            for entity in expressions:
                if movie_entity:
                    entity = add_movie_to_expression(entity, movie_entity.key)
                if actor_entity:
                    entity = add_actor_to_expression(entity, actor_entity.key)
                if entity.movie_key and entity.actor_key:
                    put_relation = ActorMovieRelationshipEntity.add_movie_to_actor_relation(entity.actor_key, entity.movie_key)
                entity = ExpressionEntity.add_default_image(entity)
            ndb.put_multi(expressions)
            try:
                deferred.defer(SearchTags.update_search_from_expression_list, map(lambda x: x.key.id(), expressions)
                               , _queue='ExpressionUpdates')
            except Exception as e:
                logging.error('successfully caught error while adding Expression indexing task.' + str(e))
            self.response.write(json.dumps({"status": "Successfully added movie = %s and actor = %s"%(movie,actor), "actor":actor, "movie":movie}))

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


"""
 This class handles adding new actors in ActorEntity.
 Request is a post request and response is just a status
"""
class AddNewActorEntity(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ Post request """
        self.insert_actor_entity(user)
        return

    def insert_actor_entity(self, user):
        """
        These are params passed for a new actor entity
        :return: status: Which has the message
        """
        actor = ActorEntity()
        movie_id = self.request.get('movie_unique_id')
        # Movie
        if not movie_id:
            self.response.write(json.dumps({
                "status": "Movie id is not passed"
            }))
            return
        movie_entity = MovieEntity.get_by_id(movie_id)
        image_file = self.request.POST.get("actor_image_file")
        image_url = None
        actor_id = str(self.request.get('actor_unique_id'))

        # Validation checks

        # Duplicate actor
        if ActorEntity.get_by_id(actor_id):
            self.response.write(json.dumps({
                "status": "Actor id already exists, Please enter a new unique id for actor",
                "actor_id": actor_id
            }))
            return

        # if no movie is passed
        if not movie_entity:
            self.response.write(json.dumps({
                "status": "Failed: There is no movie with the given id. Please check the movie id and retry",
                "movie_id": self.request.get('movie_id')
            }))
            return
        # If actor_id is not passed
        if not actor_id:
            self.response.write(json.dumps({
                "status": "No actor id is passed. Please check the fields once again"
            }))
            return
        # if image_file is not passed
        if image_file == None:
            self.response.write(json.dumps({
                "status": "Poster is compulsory for an actor, please add a valid image of that respective actor"
            }))
            return

        # Poster url
        if (image_file != None):
            logging.debug("actual image file name : %s" % image_file.filename)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = get_random_id(15) + ext
            path, mime_type = files.put_file("uploads/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path

        actor.movies = [movie_entity.key] # add atleast 1 movie
        actor.display_name = self.request.get('display_name')
        actor.gender = self.request.get('gender')  # male or female
        actor.primary_language = self.request.get('primary_language')
        actor.languages = self.request.get_all('languages[]')
        actor.poster_url = image_url
        actor.key = ndb.Key('ActorEntity', str(self.request.get('actor_unique_id')))
        logging.log(logging.DEBUG,  "Successful in creating actor with key %s"%(actor_id))
        actor.put()

        # ImageProcessing: Create thumbnail for this actor entity
        try:
            deferred.defer(process_unapproved_expression_entity_image, actor.key.id(),entity_kind="actor",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % actor.key.id())

        #channel = make_new_actor_channel(actor.key)
        #if channel:
        #    SearchTags.insert_search_channel(ndb.Key("ChannelEntity", "actor_"+actor.key.id()))
        logging.log(logging.DEBUG, "A new actor is created")
        # Search index
        create_actor_search(actor)

        self.response.write(json.dumps({
            "status": "Success.. A new actor is created"
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


"""
 This class handles adding new movies in MovieEntity.
 Request is a post request and response is just a status
"""
class AddNewMovieEntity(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ Post Request """
        self.insert_movie_entity(user)

    def insert_movie_entity(self, user):
        """
        These are the params passed for a new movie entity
        :return: status: Which has the message
        """
        movie = MovieEntity()
        movie_id = str(self.request.get('movie_unique_id'))
        # Movie
        if not movie_id:
            self.response.write(json.dumps({
                "status": "Movie id is not passed"
            }))
            return
        image_file = self.request.POST.get("movie_image_file")

        movie_entity = MovieEntity.get_by_id(movie_id)

        # Validations:

        # If movie_id is not passed
        if not movie_id:
            self.response.write(json.dumps({
                "status": "No movie id is passed. Please check the fields once again"
            }))
            return

        # To avoid duplicate
        if movie_entity:
            self.response.write(json.dumps({
                "status": "There is already a movie with this id"
            }))
            return

        # If movie poster is missing
        if image_file is None:
            self.response.write(json.dumps({
                "status": "Poster is compulsory for an actor, please add a valid image of that respective actor"
            }))
            return

        # Poster url
        image_url = None
        if image_file is not None:
            logging.debug("actual image file name : %s" % image_file.filename)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = get_random_id(15) + ext
            path, mime_type = files.put_file("uploads/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path

        movie.full_name = self.request.get('full_name')
        movie.display_name = self.request.get('display_name')
        movie.year = int(self.request.get('year'))
        movie.languages = self.request.get_all('languages[]')
        movie.poster_url = image_url
        movie.key = ndb.Key('MovieEntity', movie_id)
        movie.put()

        # ImageProcessing: Create thumbnail for this unapproved expression
        try:
            deferred.defer(process_unapproved_expression_entity_image, movie.key.id(), entity_kind="movie",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % movie.key.id())

        #channel = make_new_movie_channel(movie.key)
        #if channel:
        #    SearchTags.insert_search_channel(ndb.Key("ChannelEntity", "movie_"+movie.key.id()))
        logging.log(logging.DEBUG, "A new movie is created")
        # Search index
        create_movie_search(movie)

        self.response.write(json.dumps({
            "status": "Success.. A new movie is created"
        }))
        return
    
    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


"""
 This class handles get count from CounterEntity.
 Request is a get request and response is just a status
"""


class GetCounterEntity(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_counter_entity(user)

    def get_counter_entity(self, user):
       
        counterEntity = CounterEntity()
        
        start_date = str(self.request.get('start_date'))
        end_date = str(self.request.get('end_date'))
        tags = self.request.get('tags')

        start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
        end_date = datetime.datetime.strptime(end_date, "%Y-%m-%d").date()

        query = CounterEntity.query(CounterEntity.date >= start_date, CounterEntity.date <= end_date).order(CounterEntity.date, CounterEntity.name)

        cursor = None
        counter_entities = []
        more = True
        while 1:
            entities, cursor, more = query.fetch_page(1000, start_cursor=cursor, produce_cursors=True)
            if entities:
                counter_entities.extend(entities)
            if not more or not entities:
                break


        response_object = json.dumps({
            'counts':  [dict(counter_entity.to_dict(),
                        **dict(key=counter_entity.key.id(),
                               date = DateTimeJSONEncoder().encode(counter_entity.date),
                               created_at = DateTimeJSONEncoder().encode(counter_entity.created_at),
                               updated_at = DateTimeJSONEncoder().encode(counter_entity.updated_at)))
                    for counter_entity in counter_entities
                ]
        })

        self.response.write(response_object)

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



"""
 This class handles fetches the user queries which have no results.
 Request is a get request and response is json with results and a status.
"""
class GetSearchQueryFrequencyResults(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_userquery_no_results(user)
        return

    def get_userquery_no_results(self, user):
        cursor_request = Cursor(urlsafe=self.request.get('cursor', None))
        query_type = self.request.get('query_type')
        search_value = self.request.get('search_value', None)

        if query_type not in ["0","1","2","3","4","5"]:
            self.response.write({"status": "Query type not passed%s"%(query_type)})
            return
        entities = []
        cursor = None
        more = True
        # Defining queries(we have 5 query types)
        if query_type == "0":
            #  Recent searched queries based on created at desc
            entities, cursor, more = SearchQueryFrequency.query().\
                                        order(-SearchQueryFrequency.created_at).\
                                        fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)

        elif (query_type == "1"):
            # Most searched queries based on value desc
            entities, cursor, more = SearchQueryFrequency.query().\
                                        order(-SearchQueryFrequency.value).\
                                        fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)
        elif (query_type == "2"):
            # Most searched type==2,value desc
            entities, cursor, more = SearchQueryFrequency.\
                                        query(SearchQueryFrequency.type == 2).\
                                        order(-SearchQueryFrequency.value).\
                                        fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)
        elif (query_type == "3"):
            # most search queries with spell corrected  results , type==1,value desc
            entities, cursor, more = SearchQueryFrequency.\
                                        query(SearchQueryFrequency.type == 1).\
                                        order(-SearchQueryFrequency.value).\
                                        fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)
        elif (query_type == "4"):
            # most queries search terms ( based on search value passed from client)
            entities, cursor, more = SearchQueryFrequency.query(SearchQueryFrequency.search_tags == search_value).\
                                        order(-SearchQueryFrequency.value).\
                                        fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)

        response_object = json.dumps({
            "cursor" : cursor.urlsafe() if cursor else None,
            "more" : more,
            'results':  [dict(entity.to_dict(),
                        **dict(key = entity.key.id(),
                               created_at = DateTimeJSONEncoder().encode(entity.created_at) if entity.created_at else None,
                               updated_at = DateTimeJSONEncoder().encode(entity.updated_at))) if entity.updated_at else None
                    for entity in entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



"""
 This class handles fetches the user queries which have no results.
 Request is a get request and response is json with results and a status.
"""
class GetUserQueryNoResults(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_search_query_frequency_results(user)
        return

    def get_search_query_frequency_results(self, user):
        cursor_request = Cursor(urlsafe=self.request.get('cursor', None))
        entities, cursor, more =  UserQueryNoResults.query().order(-UserQueryNoResults.created_at).fetch_page(1000, start_cursor=cursor_request, produce_cursors=True)
        response_object = json.dumps({
            "cursor" : cursor.urlsafe(),
            "more" : more,
            'results':  [dict(entity.to_dict(),
                        **dict(key = entity.key.id(),
                               installation = entity.installation.id() if entity.installation else None,
                               user = entity.user.id() if entity.user else None,
                               created_at = DateTimeJSONEncoder().encode(entity.created_at) if entity.created_at else None,
                               updated_at = DateTimeJSONEncoder().encode(entity.updated_at) if entity.updated_at else None
                               )
                            )
                    for entity in entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class GetUserLogEntity(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_user_log_entity(user)
        return

    def get_user_log_entity(self, user):
        user_id = self.request.get('user_id')
        cursor_request = Cursor(urlsafe=self.request.get('cursor', None))
        user = UserEntity.get_by_id(user_id)
        installation = InstallationEntity.get_by_id(user_id)


        if not user and not installation:
            self.response.write(json.dumps({"status" : "Not a valid user id"}))
            return

        if installation:
            query = UserLogEntity.query(UserLogEntity.installation_key == installation.key).order(-UserLogEntity.created_at)
        elif user:
            query = UserLogEntity.query(UserLogEntity.user_key == user.key).order(-UserLogEntity.created_at)

        user_log_entities, cursor, more = query.fetch_page(500, start_cursor=cursor_request, produce_cursors=True)
        response_object = json.dumps({
            "cursor" : cursor.urlsafe() if cursor else None,
            "more" : more,
            'results':  [dict(entity.to_dict(),
                        **dict(key = entity.key.id(),
                               installation_key = entity.installation_key.id() if entity.installation_key else None,
                               created_at = DateTimeJSONEncoder().encode(entity.created_at) if entity.created_at else None,
                               updated_at = DateTimeJSONEncoder().encode(entity.updated_at) if entity.updated_at else None,
                               user_key = entity.user_key.id() if entity.user_key else None
                               )
                              )
                    for entity in user_log_entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class GetTrackedUsers(webapp2.RequestHandler):
    '''
        This will return the list of users that are tracked
    '''
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_tracked_users(user)
        return

    def get_tracked_users(self, user):
        entities = UserEntity.query(UserEntity.is_user_tracked == True).fetch()
        response_object = json.dumps({
            'users':  [dict(entity.to_dict(),
                        **dict(key = entity.key.id(),
                               last_notification_time = DateTimeJSONEncoder().encode(entity.last_notification_time) if entity.last_notification_time else None,
                               created_at = DateTimeJSONEncoder().encode(entity.created_at) if entity.created_at else None,
                               updated_at = DateTimeJSONEncoder().encode(entity.updated_at) if entity.updated_at else None
                               )
                            )
                    for entity in entities
                ]
        })

        self.response.write(response_object)


    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class UpdateExpression(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def post(self, user):
        """ post """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.update_expression_content_from_client(user)
        return

    def update_expression_content_from_client(self, user):

        """
        This method's request will have the expression key parameter(optional). It fetches UnApprovedExpressionEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                'status'
        """
        expression_key = self.request.get('expression_key')
        tags_before_split = self.request.get_all('tags[]')
        tags = tags_before_split[0].split(',')
        transcript = self.request.get('transcript')
        caption = transcript.replace(' ','-')
        languages = self.request.get('language')
        actor = self.request.get('actor')
        movie = self.request.get('movie')

        # Fetching actor and movie keys
        if actor:
            actor_entity = ActorEntity.get_by_id(actor)
            if not actor_entity:
                self.response.write(json.dumps({
                    "status": "Check the actor key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "No Check the actor key again and create a new relation")
                return

        if movie:
            movie_entity = MovieEntity.get_by_id(movie)
            if not movie_entity:
                self.response.write(json.dumps({
                    "status": "Check the movie key again and create a new relation."
                }))
                logging.log(logging.DEBUG, "Check the actor key again and create a new relation")
                return

        if languages not in ALL_LANGUAGES and languages != 'global':
            # send an error saying language is not correct
            self.response.write(json.dumps({
                "status" : "language is not correct"
            }))
            logging.log(logging.DEBUG, "In dashboard.py, UpdateExpression: Not a valid language")
            return

        expression_entity = ExpressionEntity.get_by_id(expression_key)
        if not expression_entity:
            self.response.write(json.dumps({
                "status": "Not a valid key"
            }))
            logging.log(logging.DEBUG, "Not a valid key, please check the key")
            return
        image_file = self.request.POST.get('file')
        if image_file is not None and image_file != '':
            logging.log(logging.DEBUG, "image_file = %s"%(image_file))
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ',''))
            file_name = get_random_id(15) + ext
            path , mime_type = files.put_file("uploads/" + file_name, image_file.file.read())
            image_url = "http://storage.googleapis.com"+ path
            expression_entity.poster_url = image_url

        expression_entity.tags = tags
        expression_entity.transcript = transcript
        expression_entity.language = languages
        expression_entity.caption = caption
        #  Adding actor and movie keys to expression entity from dashboard utils in utils.py
        expression_entity = adding_actor_movie_to_expression(actor, movie, expression_entity.key.id())
        if not expression_entity:
            self.response.write(json.dumps({
                "status" : "Either actor or movie is wrong, please pass valid keys"
            }))

        # Partner and Admin permissions are handled here
        if expression_entity.user_key != user.key and user.type != UserType.ADMIN:
            self.response.write(json.dumps({
                "status" : "You doesn't own this expression. Please check the expression you edited"
            }))
            return
        expression_entity.put()

        if expression_entity.type != ExpressionType.AUTO_APPROVED_AUDIO:
            # Insert in Search tags
            SearchTags.insert_search(expression_entity)
        # Update CounterEntity
        expression_entity_counter = ExpressionEntityCounter.get_by_id(expression_key)
        if expression_entity_counter:
            expression_entity_counter.language = languages
            expression_entity_counter.put()
        # Update Rank Entity
        expression_entity_rank = ExpressionEntityRank.get_by_id(expression_key)
        if expression_entity_rank:
            expression_entity_rank.language = languages
            expression_entity_rank.tags = tags
            expression_entity_rank.put()

        # ImageProcessing: Create thumbnail for this expression
        try:
            deferred.defer(process_unapproved_expression_entity_image, expression_entity.key.id(), entity_kind = "expression",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % expression_entity.key.id())

        # response
        response_object = json.dumps({
            "status" : "Successfully updated expression..!"
        })
        logging.log(logging.DEBUG, "Successfully edited an approved Expression")
        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

class GetUnTaggedExpressionsInfo(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_untagged_expressions_info()
        return

    def get_untagged_expressions_info(self, user):
        # expressions with no actor or movie
        query = ExpressionEntity.query(ndb.OR(ExpressionEntity.actor_key==None,
                                              ExpressionEntity.movie_key==None)).order(ExpressionEntity._key)
        entities = fetch_all_entities(query)
        tags_count_dict = {}

        for expression in entities:
            if expression.tags:
                for tag in expression.tags:
                    tags_count_dict[tag] = tags_count_dict.get(tag, 0) + 1

        sorted_tags_count = sorted(tags_count_dict.items(), key=operator.itemgetter(1),reverse = True)

        self.response.headers['Content-Type'] = 'text/plain'
        for tag_count in sorted_tags_count:
            self.response.write('%s  --- %s \n' % tag_count)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class GetUserEntity(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ GET Request """
        self.get_user_entity(user)
        return

    def get_user_entity(self, user):
        user_id = self.request.get('user_id')
        user_entity = UserEntity.get_by_id(user_id)
        if not user_entity:
            self.response.write(json.dumps({
                "status" : "Not a valid user key"
            }))
            return
        response_object = json.dumps({
            'results':  [dict(entity.to_dict(),
                        **dict(key = entity.key.id(),
                               last_notification_time = DateTimeJSONEncoder().encode(entity.last_notification_time) if entity.last_notification_time else None,
                               created_at = DateTimeJSONEncoder().encode(entity.created_at) if entity.created_at else None,
                               updated_at = DateTimeJSONEncoder().encode(entity.updated_at) if entity.updated_at else None
                               )
                              )
                    for entity in [user_entity]
                ]
        })
        self.response.write(response_object)
        return
    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


"""

Flow:
    Request handler has a method get() which has request params passed.
    getActorEntity() : It is a method that queries Actor Entities and serialize the
            response into json. That response_object is sent as a response to the request
    getMovieEntity() : It is a method that queries Actor Entities and serialize the
            response into json. That response_object is sent as a response to the request

"""


class GetActorMovieEntities(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        # Get Entity Type
        entity_type = self.request.get('type', None)
        if entity_type == "actor":
            self.get_actor_entity(user)
        elif entity_type == "movie":
            self.get_movie_entity(user)
        return


    def get_actor_entity(self, user):

        """
        This method's request will have the cursor parameter(optional). It fetches ActorEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                1. ActorEntities
                2. cursor_response
                3. more
        """
        cursor_request = Cursor(urlsafe=self.request.get('cursor',None))
        # These below two params are filters on approval dashboard
        language = self.request.get('language', None)
        logging.log(logging.DEBUG, "language = %s"%(language))
        if language == "All":
            language = None

        cursor_response = Cursor()
        more = True
        entities = []

        if language is not None:
            entities, cursor_response, more = ActorEntity.\
                                                query(ActorEntity.primary_languages == language, ActorEntity.is_associated_with_an_expression == True).\
                                                fetch_page(200,start_cursor=cursor_request)

        else:
            entities, cursor_response, more = ActorEntity.\
                                                query(ActorEntity.is_associated_with_an_expression == True).\
                                                fetch_page(200,start_cursor=cursor_request)
        if not cursor_response:
            cursor_response = Cursor()
        # Creates a json object for transmission and to avoid Origin Access Control
        for actor in entities:
            del actor.movies

        response_object = json.dumps({
            'cursor': cursor_response.urlsafe(),
            'more': more,
            'voices':  [dict(p.to_dict(),
                        **dict(key=p.key.id(),
                               created_at=DateTimeJSONEncoder().encode(p.created_at),
                               updated_at=DateTimeJSONEncoder().encode(p.updated_at)))
                    for p in entities
                ]
        })

        self.response.write(response_object)
        return

    def get_movie_entity(self, user):

        """
        This method's request will have the cursor parameter(optional). It fetches MovieEntity and
                send it back to the client.

        :return: A json response object. We have to return three params.
                1. MovieEntities
                2. cursor_response
                3. more
        """
        cursor_request = Cursor(urlsafe=self.request.get('cursor',None))
        # These below two params are filters on approval dashboard
        language = self.request.get('language', None)
        logging.log(logging.DEBUG, "language = %s"%(language))
        if language == "All":
            language = None

        cursor_response = Cursor()
        more = True
        entities = []

        if language is not None:
            entities, cursor_response, more = MovieEntity.\
                                                query(MovieEntity.primary_languages == language, MovieEntity.is_associated_with_an_expression == True).\
                                                fetch_page(200,start_cursor=cursor_request)

        else:
            entities, cursor_response, more = MovieEntity.\
                                                query(MovieEntity.is_associated_with_an_expression == True).\
                                                fetch_page(200,start_cursor=cursor_request)
        if not cursor_response:
            cursor_response = Cursor()
        # Creates a json object for transmission and to avoid Origin Access Control

        response_object = json.dumps({
            'cursor': cursor_response.urlsafe(),
            'more': more,
            'voices':  [dict(p.to_dict(),
                        **dict(key=p.key.id(),
                               created_at=DateTimeJSONEncoder().encode(p.created_at),
                               updated_at=DateTimeJSONEncoder().encode(p.updated_at)))
                    for p in entities
                ]
        })

        self.response.write(response_object)
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


class GetActorMovieEntity(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        # Check if it is actor entity
        key = self.request.get('key', None)
        if not key:
            logging.log(logging.DEBUG, "Empty actor key")
            self.response.write(json.dumps({
                "status": "Empty key, please check the actor key sent"
            }))
            return
        actor_entity = ActorEntity.get_by_id(key)
        movie_entity = MovieEntity.get_by_id(key)
        if not actor_entity and not movie_entity:
            logging.log(logging.DEBUG, "Not a valid key")
            self.response.write(json.dumps({
                "status": "Not a valid key, please check the actor/movie key sent"
            }))
            return

        if actor_entity:
            self.get_actor_entity(actor_entity, user)
        elif movie_entity:
            self.get_movie_entity(movie_entity, user)

        return


    def get_actor_entity(self, actor_entity, user):

        """
        This method's request will have the cursor parameter(optional). It fetches ActorEntity and
                send it back to the client.

        :return: A json response object. We have to return one param.
                1. ActorEntity
        """
        # Movies property has a set of keys which are unimportant analyzing actors data, hence deleted
        del actor_entity.movies

        response_object = json.dumps({
            'entity_type' : "actor",
            'results':  dict(actor_entity.to_dict(),
                        **dict(key=actor_entity.key.id(),
                               created_at=DateTimeJSONEncoder().encode(actor_entity.created_at),
                               updated_at=DateTimeJSONEncoder().encode(actor_entity.updated_at)))
        })
        self.response.write(response_object)
        return


    def get_movie_entity(self, movie_entity, user):

        """
        This method's request will have the cursor parameter(optional). It fetches MovieEntity and
                send it back to the client.

        :return: A json response object. We have to return one param.
                1. MovieEntity
        """
        response_object = json.dumps({
            'entity_type': "movie",
            'results':  dict(movie_entity.to_dict(),
                        **dict(key=movie_entity.key.id(),
                               created_at=DateTimeJSONEncoder().encode(movie_entity.created_at),
                               updated_at=DateTimeJSONEncoder().encode(movie_entity.updated_at)))

        })
        self.response.write(response_object)
        return

class UpdateActorMovieEntity(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def post(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        # Check if it is actor entity
        key = self.request.POST.get('key', None)
        if not key:
            logging.log(logging.DEBUG, "Empty actor key")
            self.response.write(json.dumps({
                "status": "Empty key, please check the actor key sent"
            }))
            return

        actor_entity = ActorEntity.get_by_id(key)
        movie_entity = MovieEntity.get_by_id(key)
        if not actor_entity and not movie_entity:
            logging.log(logging.DEBUG, "Not a valid key")
            self.response.write(json.dumps({
                "status": "Not a valid key, please check the actor/movie key sent"
            }))
            return

        if actor_entity:
            self.update_actor_entity(actor_entity, user)
        if movie_entity:
            self.update_movie_entity(movie_entity, user)

        return


    def update_actor_entity(self, actor_entity, user):

        """
        This method will update the actor entity with 5 fields passed from client.
            * key
            * display_name
            * primary_languages
            * image_file

        :return: A json response object. We have to return one param.
                Status: Successfully updated
        """
        # To use pulti: entities that needs to be updated is a list of all the entities that needs a put()
        entities_need_to_updated = []

        actor_entity.display_name = self.request.get('display_name') or actor_entity.display_name
        logging.log(logging.DEBUG, "Display name passed: %s "%actor_entity.display_name)
        languages_before_split = self.request.get_all('primary_languages[]', None)
        languages = languages_before_split[0].split(',')
        tags_before_split = self.request.get_all('tags[]', None)
        tags = tags_before_split[0].split(',')
        logging.log(logging.DEBUG, "Languages passed: %s "%languages)
        logging.log(logging.DEBUG, "Tags: %s "%tags)
        if 'global' in languages:
            # send an error saying language is not correct
            self.response.write(json.dumps({
                "status" : "language is not correct"
            }))
            logging.log(logging.DEBUG, "In dashboard.py, UpdateActorEntity: Not a valid language")
            return
        actor_entity.primary_languages = list(set(languages) & set(ALL_LANGUAGES))
        actor_entity.tags = tags
        image_file = self.request.POST.get('image_file')

        image_url = None
        # Add Poster url
        if (image_file is not None and image_file != ''):
            logging.debug("actual image file name : %s" % image_file)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = get_random_id(15) + ext
            path, mime_type = files.put_file("uploads/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path

        if image_url:
            actor_entity.poster_url = image_url
            actor_entity.thumbnail_url = image_url
        entities_need_to_updated.append(actor_entity)

        # Updating channel entity
        channel_entity = ChannelEntity.get_by_id("actor_"+actor_entity.key.id())
        if channel_entity:
            logging.log(logging.DEBUG, "Updating channel entity for actor " + actor_entity.key.id())
            channel_entity.display_name = actor_entity.display_name
            channel_entity.thumbnail_url = actor_entity.poster_url
            channel_entity.primary_languages = actor_entity.primary_languages
            channel_entity.gender = actor_entity.gender
            channel_entity.tags = actor_entity.tags
            channel_entity.put()
            # Insert into search channel
            SearchTags.insert_search_channel(channel_entity.key)
            ChannelEntity.add_rank_top_clip_duration_to_channel_by_type(channel_entity.key)
        if entities_need_to_updated:
            ndb.put_multi(entities_need_to_updated)
        # ImageProcessing: Create thumbnail for this actor entity
        try:
            deferred.defer(process_unapproved_expression_entity_image, actor_entity.key.id(),entity_kind="actor",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % actor_entity.key.id())


        response_object = json.dumps({
            "status": "Successfully updated both actor and channel entities"
        })
        self.response.write(response_object)
        return


    def update_movie_entity(self, movie_entity, user):

        """
        This method will update the actor entity with 5 fields passed from client.
            * key
            * display_name  
            * primary_languages
            * image_file

        :return: A json response object. We have to return one param.
                Status: Successfully updated
        """
        # Entities that needs to be updated in datastore, we use put_multi
        entities_needs_to_be_updated = []

        movie_entity.display_name = self.request.get('display_name')
        logging.log(logging.DEBUG, "Display name passed: %s "%movie_entity.display_name)
        languages_before_split = self.request.get_all('primary_languages[]', None)
        languages = languages_before_split[0].split(',')
        tags_before_split = self.request.get_all('tags[]', None)
        tags = tags_before_split[0].split(',')
        logging.log(logging.DEBUG, "Languages passed: %s "%languages)
        if 'global' in languages:
            # send an error saying language is not correct
            self.response.write(json.dumps({
                "status" : "language is not correct"
            }))
            logging.log(logging.DEBUG, "In dashboard.py, Update MovieEntity: Not a valid language")
            return
        movie_entity.primary_languages = list(set(languages) & set(ALL_LANGUAGES))

        image_file = self.request.POST.get('image_file')

        image_url = None
        # Add Poster url
        if (image_file is not None and image_file != ''):
            logging.debug("actual image file name : %s" % image_file)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = get_random_id(15) + ext
            path, mime_type = files.put_file("uploads/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path

        if image_url:
            movie_entity.poster_url = image_url
        movie_entity.tags = tags
        entities_needs_to_be_updated.append(movie_entity)

        # Updating channel entity
        channel_entity = ChannelEntity.get_by_id("movie_" + movie_entity.key.id())
        if channel_entity:
            logging.log(logging.DEBUG, "Updating channel entity for actor "+ movie_entity.key.id())
            channel_entity.poster_url = movie_entity.poster_url
            channel_entity.primary_languages = movie_entity.primary_languages
            channel_entity.name = movie_entity.display_name
            channel_entity.tags = movie_entity.tags
            channel_entity.put()
            SearchTags.insert_search_channel(channel_entity.key)
            ChannelEntity.add_rank_top_clip_duration_to_channel_by_type(channel_entity.key)

        if entities_needs_to_be_updated:
            ndb.put_multi(entities_needs_to_be_updated)

        # ImageProcessing: Create thumbnail for this actor entity
        try:
            deferred.defer(process_unapproved_expression_entity_image, movie_entity.key.id(),entity_kind="movie",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % movie_entity.key.id())


        response_object = json.dumps({
            "status": "Successfully updated both actor and channel entities"
        })
        self.response.write(response_object)
        return

'''
 Adding expressions into channels
 @params:
    channel_id
    expression_list (array of expression key id's)
 @return:
    status

    $ Edge cases:
        1. Validation for channel id (must not be empty)
        2. Validation for expression list (must not be empty)
        3. Check if already expression in channel (dont create a broadcast entity)
'''

class AddExpressionsIntoChannel(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """
    @webhandler_auth
    def post(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.add_into_channel(user)
        return

    def add_into_channel(self, user):
        channel_id = self.request.POST.get('channel_id')
        expression_list = self.request.get_all('expression_list[]')
        channel_entity = ChannelEntity.get_by_id(channel_id)

        if not channel_id or not channel_entity:
            # status: channel id is not valid
            self.response.write(json.dumps({
                "status" : "Channel id is not valid or it is empty. Please write a valid key"
            }))
            return

        # Validation for expression list
        if not expression_list:
            # Expression list must not be empty
            self.response.write(json.dumps({
                "status" : "Expression list is empty"
            }))
            return

        # Validating for channel type
        if channel_entity.type != ChannelType.EDITORIAL:
            self.response.write(json.dumps({
                "status" : "CHANNEL TYPE IS NOT OF TYPE EDITORIAL"
            }))
            return
        if channel_entity.user_key and user.type != UserType.ADMIN:
            if channel_entity.user_key != user.key:
                self.response.write(json.dumps({
                    "status" : "You don't own this channel, please check the channel you are adding"
                }))
                return

        multiple_entities = []
        expressions = get_multi(map(lambda expression_id: ndb.Key('ExpressionEntity', expression_id), expression_list))
        expression_added = False
        for expression in expressions:
            # Check if expression is already present in that channel
            if expression:
                duplicate_broadcast_entity = BroadcastEntity.\
                        query(BroadcastEntity.expression == expression.key, BroadcastEntity.channel == channel_entity.key).\
                        get()
                if not duplicate_broadcast_entity:
                    expression_added = True
                    # Create a new broadcast entity
                    broadcast_entity = BroadcastEntity.broadcast_expression_to_channel(expression=expression, channel=channel_entity)
                    multiple_entities.append(broadcast_entity)

        if not expression_added:
            self.response.write(json.dumps({
                    "status" : "Content already on channel, can't post duplicates"
                }))
            return
        channel_entity.last_content_added = datetime.datetime.utcnow()

        multiple_entities.append(channel_entity)
        if multiple_entities:
            ndb.put_multi(multiple_entities)
        else:
            self.response.write(json.dumps({
                "status" : "No expressions were added, May be they're already present in the channel"
            }))
            return

        # Insert channel search
        SearchTags.insert_search_channel(channel_entity.key)
        #clear channel memcache data to reflect
        clear_channel_memcache_data(channel_entity)
        add_task_for_new_content_to_channel(channel_entity, countdown=3600)
        self.response.write(json.dumps({
            "status" : "Successfully added following expressions to %s channel"%(channel_entity.key.id())
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


'''
 Removing expressions from channels
 @params:
    channel_id
    expression_list (array of expression key id's)
 @return:
    status

    $ Edge cases:
        1. Validation for channel key sent by client
        2. Validation for expression_list sent by client
'''
class RemoveExpressionsFromChannel(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def post(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.remove_from_channel(user)
        return

    def remove_from_channel(self, user):
        channel_id = self.request.POST.get('channel_id')
        expression_list = self.request.get_all('expression_list[]')
        channel_entity = ChannelEntity.get_by_id(channel_id)
        if not channel_id or not channel_entity:
            # status: channel id is not valid
            self.response.write(json.dumps({
                "status" : "Channel id is not valid or it is empty. Please write a valid key"
            }))
            return

        # Validation for expression list
        if not expression_list:
            # Expression list must not be empty
            self.response.write(json.dumps({
                "status" : "Expression list is empty"
            }))
            return

        # Validating for channel type
        if channel_entity.type != ChannelType.EDITORIAL:
            self.response.write(json.dumps({
                "status" : "CHANNEL TYPE IS NOT OF TYPE EDITORIAL"
            }))
            return

        # Make sure partner is not removing from other channels which are not owned by him
        if user.type != UserType.ADMIN and channel_entity.user_key != user.key:
            self.response.write(json.dumps({
                "status" : "You can't modify this channel. Not Authorized"
            }))
            return

        expression_keys_list = [ ndb.Key('ExpressionEntity', expression) for expression in expression_list]
        # Keys of entities that needs to be deleted
        broadcast_entities_keys = BroadcastEntity.\
                        query(BroadcastEntity.expression.IN(expression_keys_list), BroadcastEntity.channel == channel_entity.key).\
                        fetch(keys_only = True)

        # Delete multiple entities
        ndb.delete_multi(broadcast_entities_keys)
        # Insert channel search
        SearchTags.insert_search_channel(channel_entity.key)
        clear_channel_memcache_data(channel_entity)
        self.response.write(json.dumps({
            "status" : "Successfully removed following expressions from %s channel"%(channel_entity.key.id())
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'



"""
 This class handles the creation of new channel and updation of old channel
"""
class ChannelsEditorial(webapp2.RequestHandler):
    '''
        Post request
    '''
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        """ Post request """

        # type_of_query
        query_type = self.request.POST.get('type_of_query')
        if query_type == "new_channel":
            self.create_new_channel_entity(user)
        elif query_type == "old_channel":
            self.update_channel_entity(user)
        else:
            self.response.write(json.dumps({
                "status" : "Type of query is wrong. Neither Creation nor Updation"
            }))
        return

    def update_channel_entity(self, user):
        """
        These are params passed for a new actor entity
        @:param:
            (Mandatory 6 fields)
            type_of_query
            channel_id
            display_name
            primary_language
            is_comments_enabled
            image_file
        :return: status: Which has the message
        """

        channel_id = self.request.POST.get('channel_id', None)
        display_name = self.request.POST.get('display_name', None)
        primary_language = self.request.POST.get('primary_language', None)
        is_comments_enabled = self.request.POST.get('is_comments_enabled', None)
        image_file = self.request.POST.get('image_file')
        tags_before_split = self.request.get_all('tags[]')
        tags = tags_before_split[0].split(',')

        # Validation checks
        if not channel_id:
            self.response.write(json.dumps({
                "status" : "Channel id is not passed"
            }))
            return
        channel_entity = ChannelEntity.get_by_id(channel_id)
        if not channel_entity:
            self.response.write(json.dumps({
                "status" : "Channel entity is not present with this id"
            }))
            return

        if not display_name:
            self.response.write(json.dumps({
                "status" : "Display name is not passed by client"
            }))
            return

        if not is_comments_enabled:
            self.response.write(json.dumps({
                "status" : "is_comments_enabled not passed from client"
            }))
            return

        if primary_language not in ALL_LANGUAGES:
            self.response.write(json.dumps({
                "status" : "primary language not passed from client"
            }))
            return

        image_url = None
        # Poster url
        if (image_file != None and image_file != ''):
            logging.debug("actual image file name : %s" % image_file.filename)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = get_random_id(15) + ext
            path, mime_type = files.put_file("channel_images/uploaded/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path

        old_channel = ChannelEntity.get_by_id(channel_id)
        old_channel.display_name = display_name
        old_channel.type = ChannelType.EDITORIAL
        old_channel.tags = tags
        old_channel.is_comments_enabled = True if is_comments_enabled == "true" else False
        old_channel.primary_languages = [primary_language]
        if image_url: # To make sure old image is still present if nothing is uploaded
            old_channel.poster_url = image_url

        if user.type != UserType.ADMIN and old_channel.owner != user.key:
            # Partners check
            self.response.write(json.dumps({
                "status" : "You can't edit this channel. Not Authorized"
            }))
            return
        old_channel.put()
        SearchTags.insert_search_channel(old_channel.key)

        # ImageProcessing: Create thumbnail for channel and if new image is uploaded
        if image_url:
            try:
                deferred.defer(process_unapproved_expression_entity_image, old_channel.key.id(),entity_kind="channel",
                           _queue='ImageProcessing')
            except Exception as e:
                logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
                logging.error('could not add image processing task for %s which is a entity_type=channel' % old_channel.key.id())

        logging.log(logging.DEBUG, "Channel = %s is updated " % (old_channel.key.id()))
        self.response.write(json.dumps({
            "status": "Success.. Channel = %s is successfully updated"%(channel_entity.name)
        }))
        return


    def create_new_channel_entity(self, user):
        """
        These are params passed for a new actor entity
        @:param:
            (Mandatory 6 fields)
            type_of_query
            channel_id
            display_name
            primary_language
            is_comments_enabled
            image_file
        :return: status: Which has the message
        """
        user = users.get_current_user()
        user_entity = UserEntity.query(UserEntity.email == user.email()).get()
        if not user_entity:
            self.response.write(json.dumps({"status": "User is not valid"}))
            return

        display_name = self.request.POST.get('display_name', None)
        tags = filter(None, map(lambda tag: re.sub("[^a-zA-Z0-9 ]", "", tag), display_name.split()))
        if not tags:
            self.response.write(json.dumps({
                "status": "Display name is missing"
            }))
            return
        cleaned_out_name = "_".join(tags)

        # /admin/dashboard: View will send a channel id instead of new random one
        admin_channel_id = self.request.POST.get('admin_channel_id', None)

        if not admin_channel_id:
            new_channel = ChannelEntity(id='user_%s_%s' % (user_entity.key.id(), cleaned_out_name.lower()))
        else:
            new_channel = ChannelEntity(id=admin_channel_id)

        primary_language = self.request.POST.get('primary_language', None)
        is_comments_enabled = self.request.POST.get('is_comments_enabled', None)
        image_file = self.request.POST.get('image_file')
        tags_before_split = self.request.get_all('tags[]')
        tags = tags_before_split[0].split(',')

        dup_channel_entity = ChannelEntity.get_by_id(new_channel.key.id())
        if dup_channel_entity:
            self.response.write(json.dumps({
                "status" : "Channel entity already present with this id. Please pass another valid id"
            }))
            return

        if not display_name:
            self.response.write(json.dumps({
                "status" : "Display name is not passed by client"
            }))
            return

        if not is_comments_enabled:
            self.response.write(json.dumps({
                "status" : "is_comments_enabled not passed from client"
            }))
            return

        image_url = None
        # Poster url
        if (image_file != None and image_file != ''):
            logging.debug("actual image file name : %s" % image_file.filename)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            file_name = new_channel.key.id() + ext
            path, mime_type = files.put_file("channel_images/uploaded/" + file_name, image_file_contents)
            image_url = "http://storage.googleapis.com" + path


        new_channel.name = display_name
        new_channel.type = ChannelType.EDITORIAL
        new_channel.is_comments_enabled = True if is_comments_enabled == "true" else False
        new_channel.primary_languages = [primary_language]
        new_channel.poster_url = image_url
        if not admin_channel_id:
            new_channel.user_key = user_entity.key
        new_channel.tags = tags
        new_channel.put()

        SearchTags.insert_search_channel(new_channel.key)
        # ImageProcessing: Create thumbnail for channel
        try:
            deferred.defer(process_unapproved_expression_entity_image, new_channel.key.id(),entity_kind="channel",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s which is a entity_type=channel' % (new_channel.key.id()))

        logging.log(logging.DEBUG, "A new channel is created")


        self.response.write(json.dumps({
            "status": "Success.. A new channel is created. Name: %s"%(new_channel.name)
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return



'''
Add new expression
'''
class AddNewExpression(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def post(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.upload_new_expression(user)
        return

    def upload_new_expression(self, user):
        '''
        params : transcript, tags, language, audio_file, image_file, http_link
        '''
        user = users.get_current_user()
        user_entity = UserEntity.query(UserEntity.email == user.email()).get()
        if not user_entity:
            self.response.write(json.dumps({"status": "User is not valid"}))
            return
        channel_id = self.request.POST.get('channel_id')
        channel_entity = ChannelEntity.get_by_id(channel_id)
        if not channel_entity:
            self.response.write(json.dumps({
                "status" : "Not a valid channel id"
            }))
            return
        transcript = self.request.POST.get('transcript')
        tags_before_split = self.request.get_all('tags[]')
        tags = tags_before_split[0].split(',')
        language = self.request.POST.get('language')
        http_link = self.request.POST.get('http_link', None)
        image_file = self.request.POST.get('image_file')
        audio_file = self.request.POST.get('audio_file')
        # Add new expression
        new_expression_id = get_random_id(15)
        new_expression = ExpressionEntity(id=new_expression_id)
        new_expression.transcript = transcript
        new_expression.caption = transcript
        new_expression.tags = tags
        new_expression.language = language
        new_expression.user_key = user_entity.key
        new_expression.type = ExpressionType.AUTO_APPROVED_AUDIO
        if http_link:
            new_expression.http_url = http_link
        # keys from blob store api
        audio_url = None
        image_url = None
        audio_mime_type = None
        original_mp3file_md5 = None

        if audio_file is not None:
            logging.debug("actual audio file name : %s" % audio_file.filename)
            uploaded_file_name, ext = os.path.splitext(audio_file.filename.replace(' ', ''))
            audio_file_contents = audio_file.file.read()
            original_mp3file_md5 = hashlib.md5(audio_file_contents).hexdigest()
            file_name = new_expression_id + ext
            path, audio_mime_type = files.put_file("uploads/" + file_name, audio_file_contents)
            audio_url = "http://storage.googleapis.com" + path

        if image_file is not None:
            logging.debug("actual image file name : %s" % image_file.filename)
            uploaded_file_name, ext = os.path.splitext(image_file.filename.replace(' ', ''))
            image_file_contents = image_file.file.read()
            #original_file_md5 = hashlib.md5(image_file_contents).hexdigest()
            file_name = new_expression_id + ext
            path, mime_type = files.put_file("uploads/" + file_name, image_file_contents)

            image_url = "http://storage.googleapis.com" + path

        new_expression.poster_url = image_url
        new_expression.original_audio_url = audio_url
        audio_name = new_expression.key.id()
        path, mime_type = files.get_file_path("uploads/" + audio_name + ".opus")
        new_expression.opus_url = "http://storage.googleapis.com" + path
        path, mime_type = files.get_file_path("uploads/" + audio_name + ".mp3")
        new_expression.mp3_url = "http://storage.googleapis.com" + path
        SearchTags.insert_search(new_expression, force=True)
        if audio_mime_type == 'audio/mpeg':
            new_expression.mp3_url = audio_url
        new_expression.mp3md5 = original_mp3file_md5

        broadcast_entity = BroadcastEntity.broadcast_expression_to_channel(new_expression, channel_entity)
        #clear channel memcache data to reflect
        clear_channel_memcache_data(channel_entity)
        ndb.put_multi([broadcast_entity, new_expression, channel_entity])
        # Add it in the pull queue and convert it into opus, if size is greater, send a rejection notification
        if audio_file is not None:

            queue = taskqueue.Queue('opus-conversion-vm')
            # extract audio_name


            # PAYLOAD must be a string
            payload_data = json.dumps({
                "audio_url": audio_url,
                "audio_name": audio_name,
                "expression_key": new_expression.key.id(),
                "type_of_expression": "expression"
            })
            try:
                queue.add(taskqueue.Task(payload=payload_data, method='PULL'))
            except Exception as e:
                logging.error(e)
        try:
            deferred.defer(process_unapproved_expression_entity_image, new_expression.key.id(),entity_kind="expression",
                           _queue='ImageProcessing')
        except Exception as e:
            logging.error('successfully caught error while adding tasks. Nothing to panic! ' + str(e))
            logging.error('could not add image processing task for %s' % new_expression.key.id())

        self.response.write(json.dumps({
            "status" : "Successfully added new expression, please check your channel"
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

'''
Get auth key
'''

class GetUserOwnedChannels(webapp2.RequestHandler):
    """ A handler to handle dashboard requests . """

    @webhandler_auth
    def get(self, user):
        """ get """
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.get_user_owned_expressions(user)
        return

    def get_user_owned_expressions(self, user):
        '''
        params : transcript, tags, language, audio_file, image_file, http_link
        '''
        # Query list of channels
        channels = ChannelEntity.query(ChannelEntity.user_key == user.key).fetch()
        if not channels:
            self.response.write(json.dumps({
                "channels" : [],
                "channels_length" : 0
            }))
            return
        channels_length = len(channels)
        # This request needs to be fast, hence sending only key and name
        response_channels = []
        for channel in channels:
            if channel.type == ChannelType.EDITORIAL:
                response_channels.append({'id': channel.key.id(), 'name': channel.name})

        self.response.write(json.dumps({
                "channels" : response_channels,
                "channels_length" : channels_length

        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'


class GetChannelInfo(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'

        # channel_id
        channel_id = self.request.get('channel_id', None)
        if not channel_id:
            self.response.write(json.dumps({
                "status" : "channel id is missing"
            }))
            return
        channel_entity = ChannelEntity.get_by_id(channel_id)

        if not channel_entity:
            self.response.write(json.dumps({
                "status" : "Not a valid channel id"
            }))
            return

        if (user.type == UserType.PARTNER and  user.key != channel_entity.user_key) or not users.is_current_user_admin():
            # User doesn't own this channel
            self.response.write(json.dumps({
                "status" : "User Doesn't own this channel"
            }))
            return

        encoded_channel_object = ChannelInfoResponse.from_entity(channel_entity)
        response_object = protojson.encode_message(encoded_channel_object)

        self.response.write(response_object)

        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

class GroupsEditorial(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        # Post request from client with params: accepted_channel_keys, removed_channel_keys, group_id
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        self.add_remove_from_groups(user)
        return

    def add_remove_from_groups(self, user):
        # Extract params:
        accepted_channel_ids = json.loads(self.request.POST.get('accepted_channels'))
        removed_channel_ids = json.loads(self.request.POST.get('removed_channels'))
        group_id = int(self.request.POST.get('group_id'))

        # Construct keys
        removed_channel_keys = []
        accepted_channel_keys = []
        for i in removed_channel_ids:
            removed_channel_keys.append(ndb.Key('ChannelEntity', i))
        for i in accepted_channel_ids:
            accepted_channel_keys.append(ndb.Key('ChannelEntity', i))

        removed_channel_entities = ndb.get_multi(removed_channel_keys)
        accepted_channel_entities = ndb.get_multi(accepted_channel_keys)

        # For using ndb.put_multi
        multi_channel_entities = []
        # Removing channels from a group

        for channel_entity in removed_channel_entities:
            # Remove only if that group id is present in channel_groups
            if channel_entity and group_id in channel_entity.channel_groups:
                channel_entity.channel_groups.remove(group_id)
                multi_channel_entities.append(channel_entity)

        # Adding channels into group
        for channel_entity in accepted_channel_entities:
            # Add this group id in channel.groups
            if channel_entity and group_id not in channel_entity.channel_groups:
                channel_entity.channel_groups.append(group_id)
                multi_channel_entities.append(channel_entity)
        if multi_channel_entities:
            ndb.put_multi(multi_channel_entities)

        self.response.write(json.dumps({
            "status" : "Successfully completed the request"
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

class AddPermissionToPartners(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'

        partner_email = str(self.request.POST.get('email_id'))
        permission = int(self.request.POST.get('permission_type'))

        # Validaton: if user is not a valid Samosa user
        partner_entity = UserEntity.query(UserEntity.email == partner_email).get()
        if not partner_entity:
            self.response.write(json.dumps({
                "status" : "Not a valid user. Please register a new user"
            }))
            return
        logging.log(logging.DEBUG, "Modifying permission to this user entity %s"%partner_entity.key.id())
        if permission == 1:
            partner_entity.type = UserType.PARTNER
        elif permission == 2:
            partner_entity.type = UserType.ADMIN

        partner_entity.put()
        self.response.write(json.dumps({
            "status" : "Successfully given permission to this partner"
        }))

        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

class RegisterNewPartner(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'

        email = self.request.POST.get('email')

        # Check if a user with this email  already exists
        user = UserEntity.query(UserEntity.email == email).get()
        if user:
            self.response.write(json.dumps({
                "status" : "A user exists with this email id"
            }))
            return
        user_name = self.request.POST.get('user_name')
        first_name = self.request.POST.get('first_name')
        last_name = self.request.POST.get('last_name')
        gender = self.request.POST.get('gender')
        logging.log(logging.DEBUG, "Created a new partner user with this email id %s"%(email))
        partner = UserEntity.create_partner_user(user_name, email, first_name, last_name, gender)
        partner.put()

        self.response.write(json.dumps({
            "status" : "Successfully added a new partner with this email id %s"%(email)
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'

class PopulateTestNotificationUtils(webapp2.RequestHandler):
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        self.response.headers['Content-Type'] = 'application/json'
        # 1. List of  admins to populate the dropdown on push notifs page
        admin_entities = UserEntity.query(UserEntity.type == UserType.ADMIN).fetch()
        admins = [ {'id':admin.key.id(), 'email':admin.email} for admin in admin_entities]
        # 2. List of push types to populate the dropdown on push types
        current_push_types = Push_Notification_Channel_Types + Push_Notification_Social_Types + \
                             Push_Notification_User_Upload_Types + [PushNotificationTypes.DEFAULT]
        all_push_types = PushNotificationTypes.__dict__
        all_push_type_names = []
        # 3. List of channel id's that needs to be tested
        channel_types = ["others_ringtones", "actor_pawan_kalyan", "movie_dilwale_2015", "editorial_news"]
        for current_value in current_push_types:
            for push_type, push_value in all_push_types.iteritems():
                if push_value == current_value:
                    all_push_type_names.append({'push_type' : push_type, 'push_value' : push_value})

        self.response.write(json.dumps({
            "push_types" : all_push_type_names,
            "admins" : admins,
            "channel_types" : channel_types
        }))

        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return

class SendTestNotification(webapp2.RequestHandler):
    @webhandler_auth
    def post(self, user):
        '''
        :params: push_type, channel_id,  user_key, force, push_id (optional)
        :return:
        '''
        user_id = self.request.POST.get('user_key')
        channel_id = self.request.POST.get('channel')
        push_type = int(self.request.POST.get('push_type', None))
        force = self.request.POST.get('force', None)  # force is either "on" or None
        if force:
            force = True

        push_id = self.request.POST.get('push_id', None) # optional
        device = self.request.POST.get('device', None)
        push_notification_id = None
        environment = None
        if device != "ANDROID":
            environment = device.split('+')[1]
            device = device.split('+')[0]
        if push_type == PushNotificationTypes.DEFAULT:
            push_notification_id = 'a9f4f2a918c36621e18a25a4c230be89'

        elif push_type == PushNotificationTypes.USER_UPLOAD:
            push_notification_id = '7268e58585459386db89b66ef5b67749'

        elif push_type == PushNotificationTypes.USER_UPLOAD_REJECTED:
            push_notification_id = 'ac9d46ebaf8d5cd0e0de145c7aa0c91c'

        elif push_type ==PushNotificationTypes.USER_NOTIFICATIONS_VIEW:
            push_notification_id = '23308abfdb210170e51a6e3a4d53228e'

        elif push_type == PushNotificationTypes.USER_PROFILE_VIEW:
            push_notification_id = '7bb29f7d2c6028e134e9df38930e4389'

        elif push_type == PushNotificationTypes.CHANNEL_LANDING_PAGE:
            push_notification_id = 'd40237f9b7e40242161f6adbf038fa54'


        elif push_type == PushNotificationTypes.ANSWER_ON_CHANNEL:
            push_notification_id = '6a5fcc1ca30ac09c3feae1a265732ba1'

        elif push_type == PushNotificationTypes.CONTENT_ADDED_ON_CHANNEL:
            push_notification_id = 'd165ad75a1c855cf272654ca6767c072'


        elif push_type == PushNotificationTypes.TODAY:
            push_notification_id = '1ea6ceb1bf3c1f926a206d5f2e78f55b'

        elif push_type == PushNotificationTypes.BROADCAST_PROMPT:
            push_notification_id  = '979a8f5be88fb957fabe3f1e7a609f10'

        elif push_type == PushNotificationTypes.RINGTONE:
            push_notification_id = '75ba552fc44f3e02e16341cd3cdcea36'

        elif push_type == PushNotificationTypes.CHANNEL_GROUP:
            push = PushNotificationEntity.create_greetings_push_notification()
            push_notification_id = push.key.id()
        elif push_type == PushNotificationTypes.MORE_CHANNELS:
            push = PushNotificationEntity.create_more_channels_push_notification()
            push_notification_id = push.key.id()
        elif push_type == PushNotificationTypes.OFFLINE:
            push = PushNotificationEntity.create_offline_push_notification()
            push_notification_id = push.key.id()
        elif push_type == PushNotificationTypes.SELECT_LANGUAGES:
            push = PushNotificationEntity.create_select_languages_notification()
            push_notification_id = push.key.id()
        logging.debug("force: %s, push_type:%s, user_id: %s, channel_id: %s, push_id= %s, environment: %s, device:%s"
                      %(force, push_type, user_id, channel_id, push_notification_id, environment, device))
        if not push_notification_id:
            self.response.write(json.dumps({
                "status" : "wrong push type selected !!!"
            }))
            return

        user_key = ndb.Key('UserEntity', user_id)

        push = PushNotificationEntity.get_by_id(push_notification_id)
        #send_notifications_by_user_keys(push_notification_id=push.key.id(), user_keys=[user_key], device_info=device,
        #                                environment=environment, force=force)
        if environment:
            deferred.defer(send_notifications_by_user_keys, push_notification_id=push.key.id(), user_keys=[user_key],
                       force=force, environment=environment, _queue='Notifications')
        else:
            deferred.defer(send_notifications_by_user_keys, push_notification_id=push.key.id(), user_keys=[user_key],
                       force=force, _queue='Notifications')
        logging.log(logging.DEBUG, "Successfully sent testing push notification to %s"%user_id)
        self.response.write(json.dumps({
            "status" : "success"
        }))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class GetChannelMetrics(webapp2.RequestHandler):
    """gets metrics of a channel"""
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        #self.response.headers['Content-Type'] = 'application/json'
        channel_id = self.request.GET.get('channel_id', None)  # force is either "on" or None
        logging.debug("channel_id: %s" % channel_id)
        if not channel_id:
            self.response.write(json.dumps({
                "status": "error: channel_id not supplied"
            }))
            return
        channel = ChannelEntity.get_by_id(channel_id)
        if not channel:
            self.response.write(json.dumps({
                "status": "error: channel not found from channel_id: %s" % channel_id
            }))
            return

        memcached_value = memcache.get(CHANNEL_METRICS_MEMCACHE_KEY % (channel.key.id(),datetime.datetime.utcnow().strftime("%Y-%m-%d")), {})
        template_values = {}
        if memcached_value:
            template_values = memcached_value
            template_values['channel'] = json.loads(protojson.encode_message(ChannelInfoResponse.from_entity(channel)))
            template_values['results_available'] = True
        else:
            template_values['results_available'] = False
            deferred.defer(calculate_channel_metrics, channel, _queue="Utility")
        template = JINJA_ENVIRONMENT.get_template('channel_metrics.html')
        self.response.write(template.render(template_values))
        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return


class GetExpressionCounterLogs(webapp2.RequestHandler):
    """gets metrics of a channel"""
    @webhandler_auth
    def get(self, user):
        self.response.headers.add_header('Access-Control-Allow-Origin', '*')
        #self.response.headers['Content-Type'] = 'application/json'
        expression_id = self.request.GET.get('expression_id', None)
        logging.debug("epxression_id: %s" % expression_id)
        if not expression_id:
            self.response.write(json.dumps({
                "status": "error: expression_id not supplied"
            }))
            return
        expression = ExpressionEntity.get_by_id(expression_id)
        if not expression:
            self.response.write(json.dumps({
                "status": "error: channel not found from channel_id: %s" % expression_id
            }))
            return

        query = ExpressionEntityCounterLog.query(ExpressionEntityCounterLog.expression==expression.key).\
            order(-ExpressionEntityCounterLog.date)
        entities = fetch_all_entities(query)
        rpcs = map(lambda entity: ExpressionEntityCounterLogResponse.from_entity(entity), entities)
        template_values = {}
        template_values['expression'] = json.loads(protojson.encode_message(ExpressionResponse.from_entity(expression)))

        expression_counter_logs = []
        for rpc in rpcs:
            encoded_rpc = json.loads(protojson.encode_message(rpc))
            encoded_rpc['date'] = rpc.date_str
            encoded_rpc.pop('date_str')
            expression_counter_logs.append(encoded_rpc)

        for i, e in enumerate(expression_counter_logs):
            if i < len(expression_counter_logs) - 1:
                e['delta_listens'] = e['listens'] - expression_counter_logs[i+1]['listens']
                e['delta_shares'] = e['shares'] - expression_counter_logs[i+1]['shares']
                e['delta_hearts'] = e['hearts'] - expression_counter_logs[i+1]['hearts']

        template = JINJA_ENVIRONMENT.get_template('expression_metrics.html')
        template_values['expression_counter_logs'] = expression_counter_logs
        self.response.write(template.render(template_values))

        #self.response.write(json.dumps(response))

        return

    def options(self):
        self.response.headers['Access-Control-Allow-Origin'] = '*'
        self.response.headers['Access-Control-Allow-Headers'] = 'Origin, X-Requested-With, Content-Type, Accept'
        self.response.headers['Access-Control-Allow-Methods'] = 'POST, GET, PUT, DELETE'
        return

app = webapp2.WSGIApplication(
    [
        ('/dashboard_get_unapproved', DashboardGet),
        ('/dashboard_get_rejected', DashboardRejected),
        ('/dashboard_post_unapproved', DashboardPost),
        ('/dashboard_get_unapproved_clip', DashboardGetUnapprovedClip),
        ('/dashboard_post_edited_unapproved_clip', DashboardPostEditedUnapprovedClip),
        ('/dashboard_post_actor_movie_relation', DashboardPostActorMovie),
        ('/dashboard_post_add_new_actor', AddNewActorEntity),
        ('/dashboard_post_add_new_movie', AddNewMovieEntity),
        ('/dashboard_get_counter_entity', GetCounterEntity),
        ('/dashboard_get_user_query_no_results', GetUserQueryNoResults),
        ('/dashboard_get_search_query_frequency', GetSearchQueryFrequencyResults),
        ('/dashboard_get_untagged_expressions_info', GetUnTaggedExpressionsInfo),
        ('/dashboard_get_user_log_entity', GetUserLogEntity),
        ('/dashboard_get_tracked_users', GetTrackedUsers),
        ('/dashboard_get_user_entity', GetUserEntity),
        ('/dashboard_get_actor_movie_entities', GetActorMovieEntities),
        ('/dashboard_get_actor_movie_entity', GetActorMovieEntity),
        ('/dashboard_post_actor_movie_entity', UpdateActorMovieEntity),
        ('/dashboard_post_groups_editorial', GroupsEditorial),
        ('/dashboard_post_change_permission', AddPermissionToPartners),
        ('/dashboard_post_create_new_partner', RegisterNewPartner),
        ('/dashboard_get_params_on_push_test_interface', PopulateTestNotificationUtils),
        ('/dashboard_post_send_test_notification', SendTestNotification),
        ('/dashboard_get_channel_metrics', GetChannelMetrics),
        ('/dashboard_get_expression_counter_logs', GetExpressionCounterLogs),
        # Partners
        ('/dashboard_post_channels_editorial', ChannelsEditorial),
        ('/dashboard_get_user_owned_channels', GetUserOwnedChannels),
        ('/dashboard_get_user_owned_channel', GetChannelInfo),
        ('/dashboard_post_remove_from_channels', RemoveExpressionsFromChannel),
        ('/dashboard_post_upload_expression', AddNewExpression),
        ('/dashboard_post_add_to_channel', AddExpressionsIntoChannel),
        ('/dashboard_post_update_expression', UpdateExpression),

    ],
    debug=True)
