import os
from xfc_control.models import User, CacheDisk
from xfc_control.views import User
import logging
from pathlib import Path

# current_dir = Path(__file__).resolve().parent
# project_root = current_dir.parent

# this base_path was just for testing, in reality it should be `pathto/work/xfc`
base_path = '/app/xfc_control/test_xfc/work/xfc'

# can be run via runscript
def run(*args):
    logging.info('Start')

    vols = os.listdir(base_path)
    for vol in vols:

        # per /vol# you know there is only /use_cache below it.
        logging.info(vol)
        path = os.path.join(base_path, vol)
        mountpoint = os.path.join(path, os.listdir(path)[0]) # so create path /pathto/work/xfc/vol#/user_cache/
        userdirs = os.listdir(mountpoint)

        cache_disk = CacheDisk()
        cache_disk.mountpoint = os.path.join('/work/xfc/', vol)
        cache_disk.allocated_bytes = 40*1024*1024*1024*1024 #40TB allocated
        # need to save cache_disk before saving user
        cache_disk.save()

        for userdir in userdirs:

            logging.info(userdir)
            user = User()
            user.name = userdir
            # user.email # TODO where is email specified?
            user.notify = True
            user.quota_size = user.get_quota_size()
            user.hard_limit_size = user.get_hard_limit_size()

            user.cache_path = os.path.join('user_cache', userdir)
            user.cache_disk = cache_disk

            user.save()
            
