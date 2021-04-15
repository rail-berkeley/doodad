import sys
import time
import os.path as osp

from doodad.utils import REPO_DIR

import doodad
from doodad.wrappers.easy_launch import arg_parse, metadata
from doodad.wrappers.easy_launch.config_private import AZ_SUB_ID, AZ_CLIENT_ID, AZ_TENANT_ID, AZ_SECRET, AZ_CONN_STR, AZ_CONTAINER, CODE_DIRS_TO_MOUNT, NON_CODE_DIRS_TO_MOUNT
from doodad.wrappers.sweeper import DoodadSweeper


def sweep_function(
        method_call,
        params,
        log_path,
        use_cloudpickle=True,
        add_date_to_logname=True,
        mode='azure',
        use_gpu=False,
        gpu_id=0,
):
    """
    Usage:
    ```
    def foo(doodad_config, variant):
        x = variant['x']
        y = variant['y']
        print("sum", x+y)
        with open(doodad_config.base_log_dir, "w") as f:
          f.write('sum = %f' % x + y)

    params = {
        'x': [1, 4],
        'y': [3, 4],
    }
    sweep_function(foo, variant, log_path='my-experiment')
    ```
    :param method_call: A function
    :param params:
    :param log_path:
    :return:
    """
    if add_date_to_logname:
        datestamp = time.strftime("%y-%m-%d")
        log_path = '%s_%s' % (datestamp, log_path)
    target = osp.join(REPO_DIR, 'doodad/easy_launch/run_experiment.py')
    sweeper, output_mount = _create_sweeper_and_output_mount()
    git_infos = metadata.generate_git_infos()

    doodad_config = metadata.DoodadConfig(
        use_gpu=use_gpu,
        gpu_id=gpu_id,
        git_infos=git_infos,
        script_name=' '.join(sys.argv),
        extra_launch_info={},
    )
    def postprocess_config(variant):
        args = {
            'method_call': method_call,
            'output_dir': '/output/{}'.format(log_path),
            'doodad_config': doodad_config,
            'variant': variant,
            'mode': mode,
        }
        args_encoded, cp_version = arg_parse.encode_args(args, cloudpickle=use_cloudpickle)
        # python_cmd = '{ad_header}={args_data} {use_cp_header}={use_cp} {cp_version_header}={cp_version} python'.format(
        #     ad_header=arg_parse.ARGS_DATA,
        #     args_data=args_encoded,
        #     use_cp_header=arg_parse.USE_CLOUDPICKLE,
        #     use_cp=str(int(use_cloudpickle)),
        #     cp_version_header=arg_parse.CLOUDPICKLE_VERSION,
        #     cp_version=cp_version,
        # )
        new_config = {
            arg_parse.ARGS_DATA: args_encoded,
            arg_parse.USE_CLOUDPICKLE: str(int(use_cloudpickle)),
            arg_parse.CLOUDPICKLE_VERSION :cp_version,
        }
        return new_config
    # args_encoded, cp_version = arg_parse.encode_args(args, cloudpickle=use_cloudpickle)
    # python_cmd = '{ad_header}={args_data} {use_cp_header}={use_cp} {cp_version_header}={cp_version} python'.format(
    #     ad_header=arg_parse.ARGS_DATA,
    #     args_data=args_encoded,
    #     use_cp_header=arg_parse.USE_CLOUDPICKLE,
    #     use_cp=str(int(use_cloudpickle)),
    #     cp_version_header=arg_parse.CLOUDPICKLE_VERSION,
    #     cp_version=cp_version,
    # )
    sweeper.run_sweep_azure(
        target, params, log_path=log_path,
        add_date_to_logname=False,
        # python_cmd=python_cmd,
        postprocess_config=postprocess_config,
    )


def _create_mounts():
    NON_CODE_MOUNTS = [
        doodad.MountLocal(**non_code_mapping)
        for non_code_mapping in NON_CODE_DIRS_TO_MOUNT
    ]
    CODE_MOUNTS = [
        doodad.MountLocal(local_dir=code_dir, pythonpath=True)
        for code_dir in CODE_DIRS_TO_MOUNT
    ]
    mounts = CODE_MOUNTS + NON_CODE_MOUNTS
    return mounts


def _create_sweeper_and_output_mount():
    mounts = _create_mounts()
    az_mount = doodad.MountAzure(
        'azure_script_output',
        mount_point='/output',
    )
    sweeper = DoodadSweeper(
        mounts=mounts,
        docker_img='vitchyr/railrl_v12_cuda10-1_mj2-0-2-2_torch1-1-0_gym0-12-5_py3-6-5:latest',
        azure_subscription_id=AZ_SUB_ID,
        azure_storage_connection_str=AZ_CONN_STR,
        azure_client_id=AZ_CLIENT_ID,
        azure_authentication_key=AZ_SECRET,
        azure_tenant_id=AZ_TENANT_ID,
        azure_storage_container=AZ_CONTAINER,
        azure_output_mount=az_mount,
    )
    return sweeper, az_mount


def foo(doodad_config, variant):
    x = variant['x']
    y = variant['y']
    print("sum", x+y)
    import os
    directory = doodad_config.base_log_dir
    if not os.path.exists(directory):
        os.makedirs(directory)
    with open(directory + '/foo_output.txt', "w") as f:
        f.write('sum = %f' % x + y)

    import sys
    with open('/output/test_from_doodad', "a") as f:
        f.write("this is a test. argv = {}\n".format(sys.argv))
        f.write("variant = {}".format(str(variant)))


if __name__ == '__main__':
    params = {
        'x': [1],
        'y': [3],
    }
    sweep_function(foo, params, log_path='test_sweep_function_with_test_from_output')
