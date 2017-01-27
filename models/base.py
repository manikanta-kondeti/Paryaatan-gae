from google.appengine.ext import ndb


class TimeTrackedModel(ndb.Model):
    created_at = ndb.DateTimeProperty(auto_now_add=True, indexed=True)
    updated_at = ndb.DateTimeProperty(auto_now=True, indexed=True)

    @classmethod
    def recently_created_query(cls):
        return cls.query().order(-cls.created_at)

    @classmethod
    def recently_updated_query(cls):
        return cls.query().order(-cls.updated_at)


class LocationEntity(TimeTrackedModel):
    lat = ndb.FloatProperty()
    lng = ndb.FloatProperty()