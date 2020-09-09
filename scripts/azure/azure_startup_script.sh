#!/bin/sh
echo 'hello world' > /tmp/myscript.txt
echo 'hello-world' > hello.txt
echo 'hello from startup script'
mkdir -p /doodad
touch hello
#sudo apt-get update
sudo apt-get install -y jq git unzip
