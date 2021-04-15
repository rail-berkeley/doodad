CODE_DIRS_TO_MOUNT = [
    '/path/to/code',
]
NON_CODE_DIRS_TO_MOUNT = [
    # for example
    dict(
        local_dir='/home/user/.mujoco/',
        mount_point='/root/.mujoco',
    ),
]
import os
try:
    AZ_SUB_ID=os.environ['AZURE_SUBSCRIPTION_ID']
    AZ_CLIENT_ID=os.environ['AZURE_CLIENT_ID']
    AZ_TENANT_ID=os.environ['AZURE_TENANT_ID']
    AZ_SECRET=os.environ['AZURE_CLIENT_SECRET']
    AZ_CONTAINER=os.environ['AZURE_STORAGE_CONTAINER']
    AZ_CONN_STR=os.environ['AZURE_STORAGE_CONNECTION_STRING']
except:
    print('azure config not set')

try:
    from doodad.wrappers.easy_launch.config_private import *
except ImportError:
    print('Please set config_private.py')
