from flask_rest_jsonapi import ResourceDetail, ResourceList, ResourceRelationship
from flask_rest_jsonapi.exceptions import ObjectNotFound
from flask_jwt import current_identity as current_user

from app.api.bootstrap import api
from app.api.helpers.db import safe_query
from app.api.helpers.exceptions import UnprocessableEntity, ForbiddenException
from app.api.helpers.feedback import delete_feedback
from app.api.helpers.permission_manager import has_access
from app.api.helpers.permissions import jwt_required
from app.api.helpers.query import event_query
from app.api.helpers.utilities import require_relationship
from app.api.schema.feedbacks import FeedbackSchema
from app.models import db
from app.models.feedback import Feedback
from app.models.event import Event
from app.models.session import Session
from app.models.user import User


class FeedbackListPost(ResourceList):
    """
    Create and List Feedbacks
    """

    def before_post(self, args, kwargs, data):
        """
        method to check for required relationship with event
        :param args:
        :param kwargs:
        :param data:
        :return:
        """
        require_relationship(['user'], data)
        if not has_access('is_user_itself', user_id=int(data['user'])):
            raise ObjectNotFound({'parameter': 'user_id'},
                                 "User: {} doesn't match auth key".format(data['user']))
        if 'event' in data and 'session' in data:
            raise UnprocessableEntity({'pointer': ''},
                                      "Only one relationship between event and session is allowed")
        if 'event' not in data and 'session' not in data:
            raise UnprocessableEntity({'pointer': ''},
                                      "A valid relationship with event and session is required")

    def before_create_object(self, data, view_kwargs):
        """
        before create object method for FeedbackListPost Class
        :param data:
        :param view_kwargs:
        :return:
        """
        if data.get('session', None):
            session = Session.query.filter_by(id=data['session']).first()
            if session and not has_access('is_coorganizer', event_id=session.event_id):
                raise ForbiddenException({'source': ''},
                                         "Event co-organizer access required")

    schema = FeedbackSchema
    methods = ['POST', ]
    data_layer = {'session': db.session,
                  'model': Feedback,
                  'methods': {'before_create_object': before_create_object}}


class FeedbackList(ResourceList):
    """
    Show List of Feedback
    """

    def query(self, view_kwargs):
        """
        query method for different view_kwargs
        :param view_kwargs:
        :return:
        """
        query_ = self.session.query(Feedback)
        if view_kwargs.get('user_id'):
            # feedbacks under an user
            user = safe_query(self, User, 'id', view_kwargs['user_id'], 'user_id')
            query_ = query_.join(User, User.id == Feedback.user_id).filter(User.id == user.id)
        elif view_kwargs.get('session_id'):
            # feedbacks under a session
            session = safe_query(self, Session, 'id', view_kwargs['session_id'], 'session_id')
            query_ = query_.join(Session, Session.id == Feedback.session_id).filter(Session.id == session.id)
        else:
            # feedbacks under an event
            query_ = event_query(self, query_, view_kwargs)
        return query_

    view_kwargs = True
    methods = ['GET', ]
    schema = FeedbackSchema
    data_layer = {'session': db.session,
                  'model': Feedback,
                  'methods': {
                      'query': query
                  }}


class FeedbackDetail(ResourceDetail):
    """
    Feedback Resource
    """

    def before_get_object(self, view_kwargs):
        """
        before get method
        :param view_kwargs:
        :return:
        """
        event = None
        if view_kwargs.get('event_id'):
            event = safe_query(self, Event, 'id', view_kwargs['event_id'], 'event_id')
        elif view_kwargs.get('event_identifier'):
            event = safe_query(self, Event, 'identifier', view_kwargs['event_identifier'], 'event_identifier')

        if event:
            feedback = safe_query(self, Feedback, 'event_id', event.id, 'event_id')
            view_kwargs['id'] = feedback.id

    def before_update_object(self, feedback, data, view_kwargs):
        """
        before update object method of feedback details
        :param feedback:
        :param data:
        :param view_kwargs:
        :return:
        """
        if feedback and feedback.session_id:
            session = Session.query.filter_by(id=feedback.session_id).first()
            if session and not current_user.id == feedback.user_id:
                raise ForbiddenException({'source': ''},
                                         "Feedback can be updated only by user himself")
            if session and not has_access('is_coorganizer', event_id=session.event_id):
                raise ForbiddenException({'source': ''},
                                         "Event co-organizer access required")
        if feedback and data.get('deleted_at'):
            if has_access('is_user_itself', user_id=feedback.user_id):
                delete_feedback(feedback)
            else:
                raise ForbiddenException({'source': ''},
                                         "Feedback can be deleted only by user himself")

    decorators = (api.has_permission('is_user_itself', fetch='user_id',
                                     fetch_as="user_id", model=Feedback, methods="PATCH,DELETE"),)
    schema = FeedbackSchema
    data_layer = {'session': db.session,
                  'model': Feedback,
                  'methods': {'before_update_object': before_update_object}}


class FeedbackRelationship(ResourceRelationship):
    """
    Feedback Relationship
    """
    decorators = (api.has_permission('is_user_itself', fetch='user_id',
                                     fetch_as="user_id", model=Feedback, methods="PATCH"),)
    methods = ['GET', 'PATCH']
    schema = FeedbackSchema
    data_layer = {'session': db.session,
                  'model': Feedback}
