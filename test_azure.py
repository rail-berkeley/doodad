import os
import doodad

SUBSC_ID = 'dc2a7d68-6f03-4c8b-9fab-291d5cbedd37'
CLIENT_ID = 'ec0d30fe-4b51-439a-a7af-4259cc2ae1b4'
TENANT_ID = '1466f6e4-adf5-439f-a023-d0d9afd3e764'
SECRET = 'rzMVNyC2p~Ve1WS27b~-F~hac-~WP4S3m6'
CONN_STR = r'DefaultEndpointsProtocol=https;AccountName=railuseaststorage;AccountKey=yFU2I6GNVMz68ps0cUuEw6xrOj270CaKsOdDUTIB2tiWeGYC8IZq9ipxXt/kcROEodT/gknCwmKUZ3zvrVzmDw==;EndpointSuffix=core.windows.net'

def run():
    launcher = doodad.AzureMode(
         azure_subscription_id=SUBSC_ID,
         azure_resource_group='rail_useast',
         azure_storage_container='doodad-test',
         azure_storage_connection_str=CONN_STR,
         azure_client_id=CLIENT_ID,
         azure_authentication_key=SECRET,
         azure_tenant_id=TENANT_ID,
         azure_network_interface='rail_useast_nic',
         log_path='foobarbaz',
         region='eastus',
         instance_type='Standard_DS1_v2',
    )
    mounts = [
        doodad.MountAzure(
            'vitchyr-test',
        )
    ]
    doodad.run_command(
        command='cat /data/secret.txt > /output/secret.txt',
        mode=launcher,
        mounts=mounts,
        verbose=True
    )

if __name__ == '__main__':
    run()
