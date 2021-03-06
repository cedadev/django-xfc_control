
from django.conf.urls import url, include
from xfc_control.views import *

urlpatterns = (
    url(r'^api/v1/disk$', CacheDiskView.as_view()),
    url(r'^api/v1/user$', UserView.as_view()),
    url(r'^api/v1/file$', CachedFileView.as_view()),
    url(r'^api/v1/scheduled_deletions$', ScheduledDeletionView.as_view()),
    url(r'^api/v1/predict_deletions$', predict, name='predict')
)
