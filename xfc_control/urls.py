
from django.urls import re_path
from xfc_control.views import *

urlpatterns = (
    re_path(r'^api/v1/disk$', CacheDiskView.as_view()),
    re_path(r'^api/v1/user$', UserView.as_view()),
)
