import os
import azure
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

from doodad.utils import hash_file, REPO_DIR, safe_import
#storage = safe_import.try_import('google.cloud.storage')

AZURE_STARTUP_SCRIPT_PATH = os.path.join(REPO_DIR, "scripts/azure/azure_startup_script.sh")
AZURE_SHUTDOWN_SCRIPT_PATH = os.path.join(REPO_DIR, "scripts/azure/azure_shutdown_script.sh")
AZURE_CLOUD_INIT_PATH = os.path.join(REPO_DIR, "scripts/azure/cloud-init.txt")


def upload_file_to_azure_storage(
    filename,
    container_name,
    #storage_account,
    connection_str,
    remote_filename=None,
    dry=False,
    check_exists=True
):
    if remote_filename is None:
        remote_filename = os.path.basename(filename)
    remote_path = 'doodad/mount/' + remote_filename

    if not dry:
        blob_service_client = BlobServiceClient.from_connection_string(connection_str)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=remote_path)
        if check_exists:
            try:
                blob_client.get_blob_properties()
                exists = True
            except azure.core.exceptions.ResourceNotFoundError:
                exists = False
            if exists:
                print("{remote_path} already exists".format(remote_path=remote_path))
                return remote_path
        with open(filename, "rb") as data:
            blob_client.upload_blob(data)
    return remote_path


def get_gpu_type_instance(gpu_model, num_gpu=1):
    """
    Check the available gpu models for each zone
    https://cloud.google.com/compute/docs/gpus/
    """

    # if gpu_model == 'nvidia-tesla-t4':
    #     return 'Standard_NC4as_T4_v3'
    if gpu_model == 'nvidia-tesla-v100':
        return 'Standard_NC6s_v3'
    elif gpu_model == 'nvidia-tesla-k80':
        return 'Standard_NC6'
    else:
        raise ValueError('Unsuported GPU {}'.format(gpu_model))



if __name__ == '__main__':
    import os
    cstr = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    rmt_path = upload_file_to_azure_storage(filename='hello.txt',
                                 container_name='ddtest',
                                 connection_str=cstr,
                                 )
