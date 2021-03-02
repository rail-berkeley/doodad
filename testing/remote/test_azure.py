"""
Instructions:

1) Set up testing/config.py (copy from config.py.example and fill in the fields)
2) Run this script
3) Look inside your AZ_CONTAINER and you should see results in doodad_test_experiment/azure_script_output/secret.txt
"""
import os
import doodad
from doodad.utils import TESTING_DIR
from testing.config import AZ_SUB_ID, AZ_CLIENT_ID, AZ_TENANT_ID, AZ_SECRET, AZ_CONN_STR, AZ_CONTAINER

def run():
    launcher = doodad.AzureMode(
        azure_subscription_id=AZ_SUB_ID,
        azure_storage_connection_str=AZ_CONN_STR,
        azure_client_id=AZ_CLIENT_ID,
        azure_authentication_key=AZ_SECRET,
        azure_tenant_id=AZ_TENANT_ID,
        azure_storage_container=AZ_CONTAINER,
        log_path='doodad_test_experiment',
        region='eastus',
        instance_type='Standard_DS1_v2'
    )

    az_mount = doodad.MountAzure(
        'azure_script_output',
        mount_point='/output',
    )

    local_mount = doodad.MountLocal(
        local_dir=TESTING_DIR,
        mount_point='/data',
        output=False
    )
    mounts = [local_mount, az_mount]

    doodad.run_command(
        command='cat /data/secret.txt > /output/secret.txt',
        mode=launcher,
        mounts=mounts,
        verbose=True
    )

if __name__ == '__main__':
    run()
