#!/bin/sh
mkdir -p /home/doodad
query_metadata() {
    attribute_name=$1
    curl -H Metadata:true --noproxy "*" "http://169.254.169.254/metadata/instance?api-version=2020-06-01" | jq -r ".compute.$attribute_name"
}
{
    sudo apt-get update
    sudo apt-get install -y jq git unzip
    name=$(query_metadata name)
    resource_group=$(query_metadata resourceGroupName)
    doodad_log_path=DOODAD_LOG_PATH
    account_name=DOODAD_STORAGE_ACCOUNT_NAME
    account_key=DOODAD_STORAGE_ACCOUNT_KEY
    container_name=DOODAD_CONTAINER_NAME
    remote_script_path=DOODAD_REMOTE_SCRIPT_PATH
    remote_script_args='DOODAD_REMOTE_SCRIPT_ARGS'
    shell_interpreter=DOODAD_SHELL_INTERPRETER
    terminate_on_end=DOODAD_TERMINATE_ON_END
    use_gpu=DOODAD_USE_GPU

    # Install docker following instructions from
    # https://docs.docker.com/engine/install/ubuntu/
    sudo apt-get install -y \
        apt-transport-https \
        ca-certificates \
        curl \
        gnupg-agent \
        software-properties-common
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add -
    sudo add-apt-repository \
        "deb [arch=amd64] https://download.docker.com/linux/ubuntu \
        $(lsb_release -cs) \
        stable"
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io
    echo "starting docker!"
    systemctl status docker.socket
    echo "docker started"

    # install Azure CLI
    # https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-apt?view=azure-cli-latest
    # currently we might be able to skip this since we use the bloblfuse to connect to the container.
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

    # Prep Linux Software Repository for Microsoft Products
    # https://docs.microsoft.com/en-us/windows-server/administration/Linux-Package-Repository-for-Microsoft-Software
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
    sudo apt-add-repository https://packages.microsoft.com/ubuntu/18.04/prod
    sudo apt-get update

    # Mount blob storage with blobfuse
    # https://docs.microsoft.com/en-us/azure/storage/blobs/storage-how-to-mount-container-linux
    sudo apt-get install -y blobfuse
    sudo mkdir /mnt/resource/blobfusetmp -p
    sudo chown doodad /mnt/resource/blobfusetmp

    echo "accountName $account_name" >> /home/doodad/fuse_connection.cfg
    echo "accountKey $account_key" >> /home/doodad/fuse_connection.cfg
    echo "containerName $container_name" >> /home/doodad/fuse_connection.cfg

    chmod 600 /home/doodad/fuse_connection.cfg

    mkdir -p /doodad_tmp
    sudo blobfuse /doodad_tmp \
        --tmp-path=/mnt/resource/blobfusetmp \
        --config-file=/home/doodad/fuse_connection.cfg \
        -o attr_timeout=240 \
        -o entry_timeout=240 \
        -o negative_timeout=120 \
        -o allow_other

    if [ -d /doodad_tmp/$doodad_log_path ]
    then
        timestamp=$(date +%d-%m-%Y_%H-%M-%S)
        randomid=$(uuidgen | cut -d '-' -f1)
        doodad_log_path="${doodad_log_path}_copy_${timestamp}_${randomid}"
        echo "directory exists. creating new log path ${doodad_log_path}"
        mkdir -p /doodad_tmp/$doodad_log_path
    else
        mkdir -p /doodad_tmp/$doodad_log_path
    fi
    ln -s /doodad_tmp/$doodad_log_path /doodad

    # This logs in using the system-assigned identity. The system-assigned
    # identity is the "virtual machine identity." So, rather than needing to
    # pass credentials to the VM, the VM can automatically authenticate by
    # virtue of being a microsoft-provided system.
    # https://docs.microsoft.com/en-us/cli/azure/authenticate-azure-cli?view=azure-cli-latest#sign-in-with-a-managed-identity
    az login --identity

    if [ "$use_gpu" = "true" ]; then
        sudo apt install -y aptdaemon
        echo 'Installing nvidia extension'
          az vm extension set \
              --resource-group $resource_group \
              --vm-name $name \
              --name NvidiaGpuDriverLinux \
              --publisher Microsoft.HpcCompute \
              --version 1.3

        # Install Nvidia Docker
        distribution=$(. /etc/os-release;echo $ID$VERSION_ID) \
           && curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add - \
           && curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

        echo 'Waiting for installation to complete'
        sudo aptdcon --refresh
        echo "Installing nvidia-docker2"
        yes | sudo aptdcon --hide-terminal --install nvidia-docker2
        sudo systemctl restart docker
        echo 'Testing nvidia-smi inside docker'
        sudo docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
    fi

    echo "test before script" >> /home/doodad/test_before_script.txt
    cp /home/doodad/* /doodad_tmp/$doodad_log_path/

    # Run the script
    cp /doodad_tmp/$remote_script_path /tmp/remote_script.sh
    echo $shell_interpreter /tmp/remote_script.sh $remote_script_args
    $shell_interpreter /tmp/remote_script.sh $remote_script_args

    # Sync std out/err
    mkdir -p /doodad_tmp/$doodad_log_path/azure_instance_output/
    cp /home/doodad/* /doodad_tmp/$doodad_log_path/azure_instance_output/
    if [ $terminate_on_end = true ];then
      # Delete everything!
      echo "Finished experiment. Terminating"
      az group delete -y --no-wait --name $resource_group
    fi
} >> /home/doodad/user_data.log 2>&1
# Sync std out/err again
cp /home/doodad/* /doodad_tmp/$doodad_log_path/azure_instance_output/