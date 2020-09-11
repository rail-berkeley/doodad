import os
import doodad
import uuid

SUBSC_ID = os.environ['AZURE_SUBSCRIPTION_ID']
CLIENT_ID = os.environ['AZURE_CLIENT_ID']
TENANT_ID = os.environ['AZURE_TENANT_ID']
SECRET = os.environ['AZURE_CLIENT_SECRET']
CONN_STR = os.environ['AZURE_STORAGE_CONNECTION_STRING']
CONTAINER_NAME = os.environ['AZURE_STORAGE_CONTAINER']

def run():
    log_path = 'sac-' + uuid.uuid4().hex[:4]
    print(log_path)
    launcher = doodad.AzureMode(
        azure_subscription_id=SUBSC_ID,
        azure_storage_container=CONTAINER_NAME,
        azure_storage_connection_str=CONN_STR,
        azure_client_id=CLIENT_ID,
        azure_authentication_key=SECRET,
        azure_tenant_id=TENANT_ID,
        log_path=log_path,
        region='eastus',
        instance_type='Standard_DS1_v2',
    )
    mounts = [
        doodad.MountAzure(
            'data',
        )
    ]
    doodad.run_command(
        command='echo foo >> /data/secret.txt',
        mode=launcher,
        mounts=mounts,
        verbose=True
    )

if __name__ == '__main__':
    run()
