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
REMOTE_DIRS_TO_MOUNT = []
LOCAL_LOG_DIR = '/home/user/logs/'
OVERWRITE_LOGS = False

# see https://docs.microsoft.com/en-us/azure/virtual-machines/ncv3-series
DEFAULT_AZURE_GPU_MODEL = 'nvidia-tesla-v100'
DEFAULT_AZURE_INSTANCE_TYPE = 'Standard_DS1_v2'
DEFAULT_AZURE_REGION = 'westus'

DEFAULT_DOCKER = 'python:3'

import os
try:
    AZ_SUB_ID=os.environ['AZURE_SUBSCRIPTION_ID']
    AZ_CLIENT_ID=os.environ['AZURE_CLIENT_ID']
    AZ_TENANT_ID=os.environ['AZURE_TENANT_ID']
    AZ_SECRET=os.environ['AZURE_CLIENT_SECRET']
    AZ_CONTAINER=os.environ['AZURE_STORAGE_CONTAINER']
    AZ_CONN_STR=os.environ['AZURE_STORAGE_CONNECTION_STRING']
except:
    print('config.py: Azure environment variables not set')

try:
    from doodad.wrappers.easy_launch.config_private import *
except ImportError:
    print("""
    Consider copying config.py to config_private.py, i.e.

    cp doodad/wrappers/easy_launch/config.py doodad/wrappers/easy_launch/config_private.py
    """)
