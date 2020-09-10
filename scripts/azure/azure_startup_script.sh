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

    # install Azure CLI
    # https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-apt?view=azure-cli-latest
    # currently we might be able to skip this since we use the bloblfuse to connect to the container.
    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

    # Prep Linux Software Repository for Microsoft Products
    # https://docs.microsoft.com/en-us/windows-server/administration/Linux-Package-Repository-for-Microsoft-Software
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
    sudo apt-add-repository https://packages.microsoft.com/ubuntu/16.04/prod
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
        -o negative_timeout=120

    if [ -d /doodad_tmp/$doodad_log_path ]
    then
        timestamp=$(date +%d-%m-%Y_%H-%M-%S)
        randomid=$(uuidgen | cut -d '-' -f1)
        doodad_log_path="${doodad_log_path}_${timestamp}_${randomid}"
        echo "directory exists. creating new log path ${doodad_log_path}"
        mkdir -p /doodad_tmp/$doodad_log_path
    else
        mkdir -p /doodad_tmp/$doodad_log_path
    fi
    ln -s /doodad_tmp/$doodad_log_path /doodad

    echo 'hello world' > /doodad/foo.txt

    # This logs in using the system-assigned identity. The system-assigned
    # identity is the "virtual machine identity." So, rather than needing to
    # pass credentials to the VM, the VM can automatically authenticate by
    # virtue of being a microsoft-provided system.
    # https://docs.microsoft.com/en-us/cli/azure/authenticate-azure-cli?view=azure-cli-latest#sign-in-with-a-managed-identity
    az login --identity

    # Delete everything!
    az group delete -y --no-wait --name $resource_group


} >> /home/doodad/user_data.log 2>&1
