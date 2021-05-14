import os
import json
import uuid
import six
import base64
import pprint
import shlex

from doodad.utils import shell
from doodad.utils import safe_import
from doodad import mount
from doodad.apis.ec2.autoconfig import Autoconfig
from doodad.credentials.ec2 import AWSCredentials

googleapiclient = safe_import.try_import('googleapiclient')
googleapiclient.discovery = safe_import.try_import('googleapiclient.discovery')
boto3 = safe_import.try_import('boto3')
botocore = safe_import.try_import('botocore')
from doodad.apis import gcp_util, aws_util, azure_util


def _remove_duplicates(lst):
    new_lst = []
    for item in lst:
        if item not in new_lst:
            new_lst.append(item)
    return new_lst


class LaunchMode(object):
    """
    A LaunchMode object is responsible for executing a shell script on a specified platform.

    Args:
        shell_interpreter (str): Interpreter command for script. Default 'sh'
        async_run (bool): If True,
    """
    def __init__(self, shell_interpreter='sh', async_run=False, use_gpu=False):
        self.shell_interpreter = shell_interpreter
        self.async_run = async_run
        self.use_gpu = use_gpu

    def run_script(self, script_filename, dry=False, return_output=False, verbose=False):
        """
        Runs a shell script.

        Args:
            script_filename (str): A string path to a shell script.
            dry (bool): If True, prints commands to be run but does not run them.
            verbose (bool): Verbose mode
            return_output (bool): If True, returns stdout from the script as a string.
        """
        run_cmd = self._get_run_command(script_filename)
        if verbose:
            print('Executing command:', run_cmd)
        if return_output:
            output = shell.call_and_get_output(run_cmd, shell=True, dry=dry)
            if output:
                return output.decode('utf-8')
        else:
            shell.call(run_cmd, shell=True, dry=dry, wait=not self.async_run)

    def _get_run_command(self, script_filename):
        raise NotImplementedError()

    def print_launch_message(self):
        pass


class LocalMode(LaunchMode):
    """
    A LocalMode executes commands locally using the host computer's shell interpreter.
    """
    def __init__(self, **kwargs):
        super(LocalMode, self).__init__(**kwargs)

    def __str__(self):
        return 'LocalMode'

    def _get_run_command(self, script_filename):
        return '%s %s' % (self.shell_interpreter, script_filename)


class SSHMode(LaunchMode):
    def __init__(self, ssh_credentials, **kwargs):
        super(SSHMode, self).__init__(**kwargs)
        self.ssh_cred = ssh_credentials

    def _get_run_command(self, script_filename):
        return self.ssh_cred.get_ssh_script_cmd(script_filename,
                                                shell_interpreter=self.shell_interpreter)


class EC2Mode(LaunchMode):
    def __init__(self,
                 ec2_credentials,
                 s3_bucket,
                 s3_log_path,
                 ami_name=None,
                 terminate_on_end=True,
                 region='auto',
                 instance_type='r3.nano',
                 spot_price=0.0,
                 security_group_ids=None,
                 security_groups=None,
                 aws_key_name=None,
                 iam_instance_profile_name='doodad',
                 swap_size=4096,
                 tag_exp_name='doodad_experiment',
                 **kwargs):
        super(EC2Mode, self).__init__(**kwargs)
        self.credentials = ec2_credentials
        self.s3_bucket = s3_bucket
        self.s3_log_path = s3_log_path
        self.tag_exp_name = tag_exp_name
        self.ami = ami_name
        self.terminate_on_end = terminate_on_end
        if region == 'auto':
            region = 'us-west-1'
        self.region = region
        self.instance_type = instance_type
        self.use_gpu = False
        self.spot_price = spot_price
        self.image_id = ami_name
        self.aws_key_name = aws_key_name
        self.iam_instance_profile_name = iam_instance_profile_name
        self.security_groups = security_groups
        self.security_group_ids = security_group_ids
        self.swap_size = swap_size
        self.sync_interval = 15

    def dedent(self, s):
        lines = [l.strip() for l in s.split('\n')]
        return '\n'.join(lines)

    def run_script(self, script_name, dry=False, return_output=False, verbose=False):
        if return_output:
            raise ValueError("Cannot return output for AWS scripts.")

        default_config = dict(
            image_id=self.image_id,
            instance_type=self.instance_type,
            key_name=self.aws_key_name,
            spot_price=self.spot_price,
            iam_instance_profile_name=self.iam_instance_profile_name,
            security_groups=self.security_groups,
            security_group_ids=self.security_group_ids,
            network_interfaces=[],
        )
        aws_config = dict(default_config)
        time_key = gcp_util.make_timekey()

        s3_base_dir = os.path.join('s3://'+self.s3_bucket, self.s3_log_path)
        s3_log_dir = os.path.join(s3_base_dir, 'outputs')
        stdout_log_s3_path = os.path.join(s3_base_dir, 'stdout_$EC2_INSTANCE_ID.log')

        sio = six.StringIO()
        sio.write("#!/bin/bash\n")
        sio.write("truncate -s 0 /tmp/user_data.log\n")
        sio.write("{\n")
        sio.write("echo hello!\n")
        sio.write('die() { status=$1; shift; echo "FATAL: $*"; exit $status; }\n')
        sio.write('EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id`"\n')
        sio.write("""
            aws ec2 create-tags --resources $EC2_INSTANCE_ID --tags Key=Name,Value={exp_name} --region {aws_region}
        """.format(exp_name=self.tag_exp_name, aws_region=self.region))

        # Add swap file
        if self.use_gpu:
            swap_location = '/mnt/swapfile'
        else:
            swap_location = '/var/swap.1'
        sio.write(
            'sudo dd if=/dev/zero of={swap_location} bs=1M count={swap_size}\n'
            .format(swap_location=swap_location, swap_size=self.swap_size))
        sio.write('sudo mkswap {swap_location}\n'.format(swap_location=swap_location))
        sio.write('sudo chmod 600 {swap_location}\n'.format(swap_location=swap_location))
        sio.write('sudo swapon {swap_location}\n'.format(swap_location=swap_location))

        sio.write("service docker start\n")
        #sio.write("docker --config /home/ubuntu/.docker pull {docker_image}\n".format(docker_image=self.docker_image))
        sio.write("export AWS_DEFAULT_REGION={aws_region}\n".format(aws_region=self.s3_bucket))
        sio.write("""
            curl "https://s3.amazonaws.com/aws-cli/awscli-bundle.zip" -o "awscli-bundle.zip"
            unzip awscli-bundle.zip
            sudo ./awscli-bundle/install -i /usr/local/aws -b /usr/local/bin/aws
        """)

        # 1) Upload script and download it to remote
        script_split = os.path.split(script_name)[-1]
        aws_util.s3_upload(script_name, self.s3_bucket, os.path.join('doodad/mount', script_split), dry=dry)
        script_s3_filename = 's3://{bucket_name}/doodad/mount/{script_name}'.format(
            bucket_name=self.s3_bucket,
            script_name=script_split
        )
        sio.write('aws s3 cp --region {region} {script_s3_filename} /tmp/remote_script.sh\n'.format(
            region=self.region,
            script_s3_filename=script_s3_filename
        ))

        # 2) Sync data
        # In theory the ec2_local_dir could be some random directory,
        # but we make it the same as the mount directory for
        # convenience.
        #
        # ec2_local_dir: directory visible to ec2 spot instance
        # moint_point: directory visible to docker running inside ec2
        #               spot instance
        ec2_local_dir = '/doodad'

        # Sync interval
        sio.write("""
        while /bin/true; do
            aws s3 sync --exclude '*' {include_string} {log_dir} {s3_path}
            sleep {periodic_sync_interval}
        done & echo sync initiated
        """.format(
            include_string='',
            log_dir=ec2_local_dir,
            s3_path=s3_log_dir,
            periodic_sync_interval=self.sync_interval
        ))

        # Sync on terminate. This catches the case where the spot
        # instance gets terminated before the user script ends.
        #
        # This is hoping that there's at least 3 seconds between when
        # the spot instance gets marked for  termination and when it
        # actually terminates.
        sio.write("""
            while /bin/true; do
                if [ -z $(curl -Is http://169.254.169.254/latest/meta-data/spot/termination-time | head -1 | grep 404 | cut -d \  -f 2) ]
                then
                    logger "Running shutdown hook."
                    aws s3 cp --region {region} --recursive {log_dir} {s3_path}
                    aws s3 cp --region {region} /tmp/user_data.log {stdout_log_s3_path}
                    break
                else
                    # Spot instance not yet marked for termination.
                    # This is hoping that there's at least 3 seconds
                    # between when the spot instance gets marked for
                    # termination and when it actually terminates.
                    sleep 3
                fi
            done & echo log sync initiated
        """.format(
            region=self.region,
            log_dir=ec2_local_dir,
            s3_path=s3_log_dir,
            stdout_log_s3_path=stdout_log_s3_path,
        ))

        sio.write("""
        while /bin/true; do
            aws s3 cp --region {region} /tmp/user_data.log {stdout_log_s3_path}
            sleep {periodic_sync_interval}
        done & echo sync initiated
        """.format(
            region=self.region,
            stdout_log_s3_path=stdout_log_s3_path,
            periodic_sync_interval=self.sync_interval
        ))

        if self.use_gpu:
            #sio.write("""
            #    for i in {1..800}; do su -c "nvidia-modprobe -u -c=0" ec2-user && break || sleep 3; done
            #    systemctl start nvidia-docker
            #""")
            sio.write("echo 'Testing nvidia-smi'\n")
            sio.write("nvidia-smi\n")
            sio.write("echo 'Testing nvidia-smi inside docker'\n")
            sio.write("nvidia-docker run --rm {docker_image} nvidia-smi\n".format(docker_image=self.docker_image))

        docker_cmd = '%s /tmp/remote_script.sh' % self.shell_interpreter
        sio.write(docker_cmd+'\n')

        # Sync all output mounts to s3 after running the user script
        # Ideally the earlier while loop would be sufficient, but it might be
        # the case that the earlier while loop isn't fast enough to catch a
        # termination. So, we explicitly sync on termination.
        sio.write("aws s3 cp --region {region} --recursive {local_dir} {s3_dir}\n".format(
            region=self.region,
            local_dir=ec2_local_dir,
            s3_dir=s3_log_dir
        ))
        sio.write("aws s3 cp --region {region} /tmp/user_data.log {s3_dir}\n".format(
            region=self.region,
            s3_dir=stdout_log_s3_path,
        ))

        if self.terminate_on_end:
            sio.write("""
                EC2_INSTANCE_ID="`wget -q -O - http://169.254.169.254/latest/meta-data/instance-id || die \"wget instance-id has failed: $?\"`"
                aws ec2 terminate-instances --instance-ids $EC2_INSTANCE_ID --region {aws_region}
            """.format(aws_region=self.region))
        sio.write("} >> /tmp/user_data.log 2>&1\n")

        full_script = self.dedent(sio.getvalue())
        ec2 = boto3.client(
            "ec2",
            region_name=self.region,
            aws_access_key_id=self.credentials.aws_key,
            aws_secret_access_key=self.credentials.aws_secret_key,
        )

        user_data = full_script
        instance_args = dict(
            ImageId=aws_config["image_id"],
            KeyName=aws_config["key_name"],
            UserData=user_data,
            InstanceType=aws_config["instance_type"],
            EbsOptimized=False,
            SecurityGroups=aws_config["security_groups"],
            SecurityGroupIds=aws_config["security_group_ids"],
            NetworkInterfaces=aws_config["network_interfaces"],
            IamInstanceProfile=dict(
                Name=aws_config["iam_instance_profile_name"],
            ),
            #**config.AWS_EXTRA_CONFIGS,
        )

        if verbose:
            print("************************************************************")
            print('UserData:', instance_args["UserData"])
            print("************************************************************")
        instance_args["UserData"] = base64.b64encode(instance_args["UserData"].encode()).decode("utf-8")
        spot_args = dict(
            DryRun=dry,
            InstanceCount=1,
            LaunchSpecification=instance_args,
            SpotPrice=str(aws_config["spot_price"]),
            # ClientToken=params_list[0]["exp_name"],
        )

        if verbose:
            pprint.pprint(spot_args)
        if not dry:
            response = ec2.request_spot_instances(**spot_args)
            print('Launched EC2 job - Server response:')
            pprint.pprint(response)
            print('*****'*5)
            spot_request_id = response['SpotInstanceRequests'][
                0]['SpotInstanceRequestId']
            for _ in range(10):
                try:
                    ec2.create_tags(
                        Resources=[spot_request_id],
                        Tags=[
                            {'Key': 'Name', 'Value': self.tag_exp_name}
                        ],
                    )
                    break
                except botocore.exceptions.ClientError:
                    continue


class EC2Autoconfig(EC2Mode):
    def __init__(self,
            autoconfig_file=None,
            region='us-west-1',
            s3_bucket=None,
            ami_name=None,
            aws_key_name=None,
            iam_instance_profile_name=None,
            **kwargs
            ):
        # find config file
        autoconfig = Autoconfig(autoconfig_file)
        s3_bucket = autoconfig.s3_bucket() if s3_bucket is None else s3_bucket
        image_id = autoconfig.aws_image_id(region) if ami_name is None else ami_name
        aws_key_name= autoconfig.aws_key_name(region) if aws_key_name is None else aws_key_name
        iam_profile= autoconfig.iam_profile_name() if iam_instance_profile_name is None else iam_instance_profile_name
        credentials=AWSCredentials(aws_key=autoconfig.aws_access_key(), aws_secret=autoconfig.aws_access_secret())
        security_group_ids = autoconfig.aws_security_group_ids()[region]
        security_groups = autoconfig.aws_security_groups()

        super(EC2Autoconfig, self).__init__(
                s3_bucket=s3_bucket,
                ami_name=image_id,
                aws_key_name=aws_key_name,
                iam_instance_profile_name=iam_profile,
                ec2_credentials=credentials,
                region=region,
                security_groups=security_groups,
                security_group_ids=security_group_ids,
                **kwargs
                )


class GCPMode(LaunchMode):
    """
    GCP Launch Mode.

    Args:
        gcp_project (str): Name of GCP project to launch from
        gcp_bucket (str): GCP Bucket for storing logs and data
        gcp_log_path (str): Path under GCP bucket to store logs/data.
            The full path will be of the form:
            gs://{gcp_bucket}/{gcp_log_path}
        gcp_image (str): Name of GCE image from which to base instance.
        gcp_image_project (str): Name of project gce_image belongs to.
        disk_size (int): Amount of disk to allocate to instance in Gb.
        terminate_on_end (bool): Terminate instance when script finishes
        preemptible (bool): Start a preemptible instance
        zone (str): GCE compute zone.
        instance_type (str): GCE instance type
        gpu_model (str): GCP GPU model. See https://cloud.google.com/compute/docs/gpus.
        data_sync_interval (int): Number of seconds before each sync on mounts.
    """
    def __init__(self,
                 gcp_project,
                 gcp_bucket,
                 gcp_log_path,
                 gcp_image='ubuntu-1804-bionic-v20181222',
                 gcp_image_project='ubuntu-os-cloud',
                 disk_size=64,
                 terminate_on_end=True,
                 preemptible=True,
                 zone='auto',
                 instance_type='f1-micro',
                 gcp_label='gcp_doodad',
                 num_gpu=1,
                 gpu_model='nvidia-tesla-t4',
                 data_sync_interval=15,
                 **kwargs):
        super(GCPMode, self).__init__(**kwargs)
        self.gcp_project = gcp_project
        self.gcp_bucket = gcp_bucket
        self.gcp_log_path = gcp_log_path
        self.gce_image = gcp_image
        self.gce_image_project = gcp_image_project
        self.disk_size = disk_size
        self.terminate_on_end = terminate_on_end
        self.preemptible = preemptible
        self.zone = zone
        self.instance_type = instance_type
        self.gcp_label = gcp_label
        self.data_sync_interval = data_sync_interval
        self.compute = googleapiclient.discovery.build('compute', 'v1')

        if self.use_gpu:
            self.num_gpu = num_gpu
            self.gpu_model = gpu_model
            self.gpu_type = gcp_util.get_gpu_type(self.gcp_project, self.zone, self.gpu_model)

    def __str__(self):
        return 'GCP-%s-%s' % (self.gcp_project, self.instance_type)

    def print_launch_message(self):
        print('Go to https://console.cloud.google.com/compute to monitor jobs.')

    def run_script(self, script, dry=False, return_output=False, verbose=False):
        if return_output:
            raise ValueError("Cannot return output for GCP scripts.")

        # Upload script to GCS
        cmd_split = shlex.split(script)
        script_fname = cmd_split[0]
        if len(cmd_split) > 1:
            script_args = ' '.join(cmd_split[1:])
        else:
            script_args = ''
        remote_script = gcp_util.upload_file_to_gcp_storage(self.gcp_bucket, script_fname, dry=dry)

        exp_name = "{}-{}".format(self.gcp_label, gcp_util.make_timekey())
        exp_prefix = self.gcp_label

        with open(gcp_util.GCP_STARTUP_SCRIPT_PATH) as f:
            start_script = f.read()
        with open(gcp_util.GCP_SHUTDOWN_SCRIPT_PATH) as f:
            stop_script = f.read()

        metadata = {
            'shell_interpreter': self.shell_interpreter,
            'gcp_bucket_path': self.gcp_log_path,
            'remote_script_path': remote_script,
            'bucket_name': self.gcp_bucket,
            'terminate': json.dumps(self.terminate_on_end),
            'use_gpu': self.use_gpu,
            'script_args': script_args,
            'startup-script': start_script,
            'shutdown-script': stop_script,
            'data_sync_interval': self.data_sync_interval
        }
        # instance name must match regex '(?:[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?)'">
        unique_name= "doodad" + str(uuid.uuid4()).replace("-", "")
        instance_info = self.create_instance(metadata, unique_name, exp_name, exp_prefix, dry=dry)
        if verbose:
            print('Launched instance %s' % unique_name)
            print(instance_info)
        return metadata

    def create_instance(self, metadata, name, exp_name="", exp_prefix="", dry=False):
        compute_images = self.compute.images().get(
            project=self.gce_image_project,
            image=self.gce_image,
        )
        if not dry:
            image_response = compute_images.execute()
        else:
            image_response = {'selfLink': None}
        source_disk_image = image_response['selfLink']
        if self.zone == 'auto':
            raise NotImplementedError('auto zone finder')
        zone = self.zone

        config = {
            'name': name,
            'machineType': gcp_util.get_machine_type(zone, self.instance_type),
            'disks': [{
                    'boot': True,
                    'autoDelete': True,
                    'initializeParams': {
                        'sourceImage': source_disk_image,
                        'diskSizeGb': self.disk_size,
                    }
            }],
            'networkInterfaces': [{
                'network': 'global/networks/default',
                'accessConfigs': [
                    {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
                ]
            }],
            'serviceAccounts': [{
                'email': 'default',
                'scopes': ['https://www.googleapis.com/auth/cloud-platform']
            }],
            'metadata': {
                'items': [
                    {'key': key, 'value': value}
                    for key, value in metadata.items()
                ]
            },
            'scheduling': {
                "onHostMaintenance": "terminate",
                "automaticRestart": False,
                "preemptible": self.preemptible,
            },
            "labels": {
                "exp_name": exp_name,
                "exp_prefix": exp_prefix,
            }
        }
        if self.use_gpu:
            config["guestAccelerators"] = [{
                      "acceleratorType": self.gpu_type,
                      "acceleratorCount": self.num_gpu,
            }]
        compute_instances = self.compute.instances().insert(
            project=self.gcp_project,
            zone=zone,
            body=config
        )
        if not dry:
            return compute_instances.execute()


class AzureMode(LaunchMode):
    """
    Azure Launch Mode.
    For the instructions for 6 first parameters follow https://docs.google.com/document/d/1j_d_FFEIOD99nLPRK-PFqb4YjZX_5FsecL3weNMvz48/edit#bookmark=id.a3b9gc7rf2m3

    Args:
            azure_subscription_id (str): AZURE_SUBSCRIPTION_ID
            azure_storage_container (str): AZURE_STORAGE_CONTAINER
            azure_storage_connection_str (str): AZURE_STORAGE_CONNECTION_STRING
            azure_client_id (str): AZURE_CLIENT_ID
            azure_authentication_key (str): AZURE_CLIENT_SECRET
            azure_tenant_id (str): AZURE_TENANT_ID
            log_path (str): The path inside the container used to mount MountAzure instances
            azure_resource_group (str): Prefix for the resource group created by doodad
            terminate_on_end (bool): Terminate instance when script finishes
            preemptible (bool): Start a preemptible instance (not working for now until Azure fixes the issue)
            region (str): Azure compute zone
            instance_type( (str): VM instance size
            num_gpu (int): No of the GPUs. See GPU_INSTANCE_DICT in https://github.com/rail-berkeley/doodad/blob/master/doodad/apis/azure_util.py
            gpu_model (str): GPU model. See https://cloud.google.com/compute/docs/gpus. GCP names are translated into Azure instance size names.
            num_vcpu (int): Specifies the number of vCPU for GPU instance
            promo_price (bool): Use promo price if available
            spot_price (float): Maximal price for preemptible instance. Specify -1 for the no limit price for the spot instance.
            **kwargs:
    """
    US_REGIONS = ['eastus', 'westus2', 'eastus2', 'westus', 'centralus', 'northcentralus',
                  'southcentralus', 'westcentralus']
    ABROAD_REGIONS = ['canadacentral', 'canadaeast', 'northeurope', 'ukwest', 'uksouth', 'westeurope', 'francecentral',
                      'switzerlandnorth', 'germanywestcentral', 'norwayeast', 'brazilsouth', 'eastasia',
                      'japanwest', 'japaneast', 'koreacentral', 'koreasouth', 'southeastasia',
                      'australiasoutheast', 'australiaeast', 'australiacentral',
                      'westindia', 'southindia', 'centralindia', 'southafricanorth', 'uaenorth'
                      ]

    def __init__(self,
                 azure_subscription_id,
                 azure_storage_container,
                 azure_storage_connection_str,
                 azure_client_id,
                 azure_authentication_key,
                 azure_tenant_id,
                 log_path,
                 azure_resource_group=None,
                 terminate_on_end=True,
                 preemptible=False,
                 region='eastus',
                 instance_type='Standard_DS1',
                 num_gpu=1,
                 gpu_model='nvidia-tesla-k80',
                 num_vcpu='default',
                 promo_price=True,
                 spot_price=-1,
                 tags=None,
                 retry_regions=None,
                 overwrite_logs=False,
                 **kwargs):
        super(AzureMode, self).__init__(**kwargs)
        self.subscription_id = azure_subscription_id
        if azure_resource_group is None:
            azure_resource_group = 'doodad'
        self.azure_resource_group_base = azure_resource_group
        self.azure_container = azure_storage_container
        self.azure_client_id = azure_client_id
        self.azure_authentication_key = azure_authentication_key
        self.azure_tenant_id = azure_tenant_id
        self._log_path = log_path
        self.terminate_on_end = terminate_on_end
        self.preemptible = preemptible
        self.region = region
        self.instance_type = instance_type
        self.spot_max_price = spot_price
        self._retry_regions = retry_regions
        self.overwrite_logs = overwrite_logs
        self.gpu_model = gpu_model
        if tags is None:
            from os import environ, getcwd
            getUser = lambda: environ["USERNAME"] if "C:" in getcwd() else environ[
                "USER"]
            user = getUser()
            tags = {
                'user': user,
                'log_path': log_path,
            }
        if 'user' not in tags:
            raise ValueError("""
            Please set `user` in tags (tags = {'user': 'NAME'}) so that we keep
            track of who is running which experiment.
            """)
        self.tags = tags

        self.connection_str = azure_storage_connection_str
        self.connection_info = dict([k.split('=', 1) for k in self.connection_str.split(';')])

        if self.use_gpu:
            self.instance_type = azure_util.get_gpu_type_instance(self.gpu_model, num_gpu, num_vcpu, promo_price)

    @property
    def log_path(self):
        return self._log_path

    @log_path.setter
    def log_path(self, value):
        self._log_path = value
        self.tags['log_path'] = value

    def __str__(self):
        return 'Azure-%s-%s' % (self.azure_resource_group_base, self.instance_type)

    def print_launch_message(self):
        print('Go to https://portal.azure.com/ to monitor jobs.')

    def run_script(self, script, dry=False, return_output=False, verbose=False):
        if return_output:
            raise ValueError("Cannot return output for Azure scripts.")

        # Upload script to Azure
        cmd_split = shlex.split(script)
        script_fname = cmd_split[0]
        if len(cmd_split) > 1:
            script_args = ' '.join(cmd_split[1:])
        else:
            script_args = ''
        remote_script = azure_util.upload_file_to_azure_storage(filename=script_fname,
                container_name=self.azure_container,
                connection_str=self.connection_str,
                dry=dry)

        with open(azure_util.AZURE_STARTUP_SCRIPT_PATH) as f:
            start_script = f.read()
        with open(azure_util.AZURE_SHUTDOWN_SCRIPT_PATH) as f:
            stop_script = f.read()

        regions_to_try = [self.region]  # always prioritize selected self.region
        if not self._retry_regions:
            regions_to_try += self.US_REGIONS  # always retry us regions
            if self.preemptible:
                # For pre-emptible, try all regions
                regions_to_try += self.ABROAD_REGIONS
        else:
            regions_to_try += self._retry_regions
        regions_to_try = _remove_duplicates(regions_to_try)
        use_data_science_image = self.use_gpu and self.gpu_model == 'nvidia-tesla-v100'
        install_nvidia_extension = self.use_gpu and not use_data_science_image

        first_try = True
        for region in regions_to_try:
            if not first_try:
                print("Retrying on region {}".format(region))
            metadata = {
                'shell_interpreter': self.shell_interpreter,
                'azure_container_path': self.log_path,
                'remote_script_path': remote_script,
                'remote_script_args': script_args,
                'container_name': self.azure_container,
                'terminate': json.dumps(self.terminate_on_end),
                'startup_script': start_script,
                'shutdown_script': stop_script,
                'region': region,
                'overwrite_logs': json.dumps(self.overwrite_logs),
                'use_data_science_image': use_data_science_image,  # processed in create_instance, json.dumps not needed
                'install_nvidia_extension': json.dumps(install_nvidia_extension)
            }
            success, instance_info = self.create_instance(metadata, verbose=verbose)
            first_try = False
            if success:
                print("Instance launched successfully")
                break
        if not success:
            print('Instance launch failed.')

            if self.preemptible:
                print('Preemptible launch creation failed in all regions. Either retry with different VM type or set'
                      ' preemptible=False')
        return metadata

    def create_instance(self, metadata, verbose=False):
        from azure.common.credentials import ServicePrincipalCredentials
        from azure.mgmt.resource import ResourceManagementClient
        from azure.mgmt.compute import ComputeManagementClient
        from azure.mgmt.network import NetworkManagementClient
        from azure.mgmt.compute.models import DiskCreateOption
        from azure.mgmt.authorization import AuthorizationManagementClient

        # TODO: Remove this guard after Azure fixes the issue
        if self.preemptible:
            print("Spot instances are not functional on our subscription just yet. Azure is currently investigating this issue.")
            print("This guard will be removed as soon as the issue is fixed.")
            exit(1)

        azure_resource_group = self.azure_resource_group_base+uuid.uuid4().hex[:6]
        region = metadata['region']
        instance_type_str = 'a spot instance' if self.preemptible else 'an instance'
        print('Creating {} of type {} in {}'.format(instance_type_str, self.instance_type, region))

        credentials = ServicePrincipalCredentials(
            client_id=self.azure_client_id,
            secret=self.azure_authentication_key,
            tenant=self.azure_tenant_id,
        )
        resource_group_client = ResourceManagementClient(
            credentials,
            self.subscription_id
        )
        network_client = NetworkManagementClient(
            credentials,
            self.subscription_id
        )
        compute_client = ComputeManagementClient(
            credentials,
            self.subscription_id
        )
        authorization_client = AuthorizationManagementClient(
            credentials,
            self.subscription_id,
        )
        resource_group_params = {
            'location': region,
            'tags': self.tags,
        }
        resource_group = resource_group_client.resource_groups.create_or_update(
            azure_resource_group,
            resource_group_params
        )
        vm_name = 'doodad-vm'
        print('VM name:', vm_name)
        print('resource group id:', resource_group.id)

        public_ip_addess_params = {
            'location': region,
            'public_ip_allocation_method': 'Dynamic'
        }
        try:
            poller = network_client.public_ip_addresses.create_or_update(
                azure_resource_group,
                'myIPAddress',
                public_ip_addess_params
            )
            publicIPAddress = poller.result()

            vnet_params = {
                'location': region,
                'address_space': {
                    'address_prefixes': ['10.0.0.0/16']
                }
            }
            network_client.virtual_networks.create_or_update(
                azure_resource_group,
                'myVNet',
                vnet_params
            )
            subnet_params = {
                'address_prefix': '10.0.0.0/24'
            }
            poller = network_client.subnets.create_or_update(
                azure_resource_group,
                'myVNet',
                'mySubnet',
                subnet_params
            )
            subnet_info = poller.result()
            nic_params = {
                'location': region,
                'ip_configurations': [{
                    'name': 'myIPConfig',
                    'public_ip_address': publicIPAddress,
                    'subnet': {
                        'id': subnet_info.id
                    }
                }]
            }
            poller = network_client.network_interfaces.create_or_update(
                azure_resource_group,
                'myNic',
                nic_params
            )
            nic = poller.result()

            startup_script_str = metadata['startup_script']
            # TODO: how do we use this shutdown script?
            shutdown_script_str = metadata['shutdown_script']
            for old, new in [
                ('DOODAD_LOG_PATH', self.log_path),
                ('DOODAD_STORAGE_ACCOUNT_NAME', self.connection_info['AccountName']),
                ('DOODAD_STORAGE_ACCOUNT_KEY', self.connection_info['AccountKey']),
                ('DOODAD_CONTAINER_NAME', self.azure_container),
                ('DOODAD_REMOTE_SCRIPT_PATH', metadata['remote_script_path']),
                ('DOODAD_REMOTE_SCRIPT_ARGS', metadata['remote_script_args']),
                ('DOODAD_SHELL_INTERPRETER', metadata['shell_interpreter']),
                ('DOODAD_TERMINATE_ON_END', metadata['terminate']),
                ('DOODAD_OVERWRITE_LOGS', metadata['overwrite_logs']),
                ('DOODAD_INSTALL_NVIDIA_EXTENSION', metadata['install_nvidia_extension'])
            ]:
                startup_script_str = startup_script_str.replace(old, new)
            custom_data = b64e(startup_script_str)

            # vm_name = ('doodad'+str(uuid.uuid4()).replace('-', ''))[:15]
            # this authenthication code is based on
            # https://docs.microsoft.com/en-us/samples/azure-samples/compute-python-msi-vm/compute-python-msi-vm/
            from azure.mgmt.compute import models
            params_identity = {
                'type': models.ResourceIdentityType.system_assigned,
            }
            vm_parameters = {
                'location': region,
                'os_profile': {
                    'computer_name': vm_name,
                    'admin_username': 'doodad',
                    'admin_password': 'Azure1',
                    'custom_data': custom_data,
                },
                'hardware_profile': {
                    'vm_size': self.instance_type
                },
                'storage_profile': {
                    'image_reference': {
                        "offer": "UbuntuServer",
                        "publisher": "Canonical",
                        "sku": "18.04-LTS",
                        "urn": "Canonical:UbuntuServer:18.04-LTS:latest",
                        "urnAlias": "UbuntuLTS",
                        "version": "latest"
                    }
                },
                'network_profile': {
                    'network_interfaces': [{
                        'id': nic.id
                    }]
                },
                'tags': self.tags,
                'identity': params_identity,
            }
            if metadata['use_data_science_image']:
                vm_parameters['storage_profile']['image_reference'] = {
                    "offer": "ubuntu-1804",
                    "publisher": "microsoft-dsvm",
                    "sku": "1804",
                    "urn": "microsoft-dsvm:ubuntu-1804:1804:latest",
                    "version": "latest"
                }
            if self.preemptible:
                spot_args = {
                    "priority": "Spot",
                    "evictionPolicy": "Deallocate",
                    "billingProfile": {
                        "maxPrice": self.spot_max_price
                    }
                }
                vm_parameters.update(spot_args)
            vm_poller = compute_client.virtual_machines.create_or_update(
                resource_group_name=azure_resource_group,
                vm_name=vm_name,
                parameters=vm_parameters,
            )
            vm_result = vm_poller.result()

            # We need to ensure that the VM has permissions to delete its own
            # resource group. We'll assign the built-in "Contributor" role and limit
            # its scope to this resource group.
            role_name = 'Contributor'
            roles = list(authorization_client.role_definitions.list(
                resource_group.id,
                filter="roleName eq '{}'".format(role_name)
            ))
            assert len(roles) == 1
            contributor_role = roles[0]

            # Add RG scope to the MSI tokenddd
            for msi_identity in [vm_result.identity.principal_id]:
                authorization_client.role_assignments.create(
                    resource_group.id,
                    uuid.uuid4(),  # Role assignment random name
                    {
                        'role_definition_id': contributor_role.id,
                        'principal_id': msi_identity
                    }
                )
        except (Exception, KeyboardInterrupt) as e:
            if 'resource_group' in locals():
                if verbose:
                    print("Deleting created resource group id: {}.".format(resource_group.id))
                resource_group_client.resource_groups.delete(
                    azure_resource_group
                )
            from msrestazure.azure_exceptions import CloudError as AzureCloudError
            if isinstance(e, AzureCloudError):
                print("Error when creating VM. Error message:")
                print(e.message + '\n')
                return False, e
            raise e
        success = True
        return success, resource_group.id


def b64e(s):
    return base64.b64encode(s.encode()).decode()

