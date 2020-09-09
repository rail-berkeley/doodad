#!/bin/sh
mkdir -p /home/doodad
{
    sudo apt-get update
    sudo apt-get install -y jq git unzip
    query_metadata() {
        attribute_name=$1
        curl -H Metadata:true --noproxy "*" "http://169.254.169.254/metadata/instance?api-version=2020-06-01" | jq ".compute.$attribute_name"
    }
    name=$(query_metadata name)
    remote_script_path=DOODADREMOTESCRIPTPATH

    echo "name:" $name
    echo "remote_script": $remote_script_path
    echo "name:" $name >> /tmp/test
    echo "remote_script": $remote_script_path >> /tmp/test
    echo 'hello world' >> /tmp/test
    echo 'hello from startup script'
    touch hello

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

    echo "accountName $accountName" >> /home/doodad/fuse_connection.cfg
    echo "accountKey $storageaccesskey" >> /home/doodad/fuse_connection.cfg
    echo "containerName $mycontainer" >> /home/doodad/fuse_connection.cfg

    chmod 600 /home/doodad/fuse_connection.cfg

    mkdir -p /doodad
    sudo blobfuse /doodad \
        --tmp-path=/mnt/resource/blobfusetmp \
        --config-file=/home/doodad/fuse_connection.cfg \
        -o attr_timeout=240 \
        -o entry_timeout=240 \
        -o negative_timeout=120


} >> /home/doodad/user_data.log 2>&1
