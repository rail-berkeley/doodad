import os

from doodad.utils import REPO_DIR, safe_import

blob = safe_import.try_import('azure.storage.blob')
azure = safe_import.try_import('azure')

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
        blob_service_client = blob.BlobServiceClient.from_connection_string(connection_str)
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


GPU_INSTANCE_DICT = {'nvidia-tesla-v100': {1: 'Standard_NC6s_v3', 2: 'Standard_NC12s_v3', 4:'Standard_NC24s_v3'},
                     'nvidia-tesla-k80': {1: 'Standard_NC6', 2: 'Standard_NC12', 4: 'Standard_NC24'},
                     'nvidia-tesla-t4': {1: {'default': 'Standard_NC4as_T4_v3', 4: 'Standard_NC4as_T4_v3', 8: 'Standard_NC8as_T4_v3', 16: 'Standard_NC16as_T4_v3'}, 4: 'Standard_NC64as_T4_v3'},
                     'nvidia-tesla-p100': {1: 'Standard_NC6s_v2', 2: 'Standard_NC12s_v2', 4: 'Standard_NC24s_v2'},
                     # 'nvidia-tesla-m60': {1: 'Standard_NV6', 2: 'Standard_NV12', 4: 'Standard_NV24'}  # installation breaks because VM restarts during nvidia drivers install
                                                                                                        # M60 is not efficient in DL, they are more suitable for visualizations
                    }

PROMO_GPU = []

def get_gpu_type_instance(gpu_model, num_gpu, num_vcpu, promo_price):
    """
    Check the available gpu models for each zone
    https://cloud.google.com/compute/docs/gpus/
    """
    if gpu_model not in GPU_INSTANCE_DICT:
        ValueError('Unsuported GPU {}'.format(gpu_model))
    instance_series = GPU_INSTANCE_DICT[gpu_model]
    if num_gpu not in instance_series:
        raise ValueError('Unsuported GPU no. {} for GPU {}'.format(num_gpu, gpu_model))
    instance_type = instance_series[num_gpu]
    if isinstance(instance_type, dict):
        if num_vcpu not in instance_type:
            raise ValueError('Unsuported vCPU no. {} for GPU {} with GPU no. {}'.format(num_vcpu, gpu_model, num_gpu))
        ret = instance_type[num_vcpu]
    else:
        ret = instance_type
    if promo_price and gpu_model in PROMO_GPU:
        ret += '_Promo'
    return ret


if __name__ == '__main__':
    import os
    cstr = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
    rmt_path = upload_file_to_azure_storage(filename='hello.txt',
                                 container_name='ddtest',
                                 connection_str=cstr,
                                 )
