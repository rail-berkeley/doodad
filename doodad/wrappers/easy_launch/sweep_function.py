import sys
import time
import os.path as osp

from doodad import mode as ddmode
from doodad.utils import REPO_DIR

import doodad
from doodad.wrappers.easy_launch import run_experiment, metadata
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
        name_runs_by_id=True,
        start_run_id=0
):
    """
    Usage:
    ```
    def foo(doodad_config, variant):
        x = variant['x']
        y = variant['y']
        with open(doodad_config.output_directory + '/foo_output.txt', "w") as f:
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
    :param name_runs_by_id: If true, then each run will be in its own
    ```
    sub-directory to create a structure of
        log_path/
            run0/
            run1/
            run2/
            ...
    ```
    otherwise, all the runs will be saved to `log_path/` directly (possibly with
    some collision-logic that's mode-dependent).
    :param start_run_id:
    :return: How many
    """
    if add_date_to_logname:
        datestamp = time.strftime("%y-%m-%d")
        log_path = '%s_%s' % (datestamp, log_path)
    target = osp.join(REPO_DIR, 'doodad/wrappers/easy_launch/run_experiment.py')
    sweeper, output_mount = _create_sweeper_and_output_mount()
    git_infos = metadata.generate_git_infos()

    doodad_config = metadata.DoodadConfig(
        use_gpu=use_gpu,
        gpu_id=gpu_id,
        git_infos=git_infos,
        script_name=' '.join(sys.argv),
        output_directory=output_mount.mount_point,
        extra_launch_info={},
    )

    def postprocess_config_and_run_mode(config, run_mode, config_idx):
        if name_runs_by_id:
            path_suffix = '/run{}'.format(start_run_id + config_idx)
        else:
            path_suffix = ''
        new_log_path = log_path + path_suffix
        args = {
            'method_call': method_call,
            'output_dir': output_mount.mount_point,
            'doodad_config': doodad_config,
            'variant': config,
            'mode': mode,
        }
        args_encoded, cp_version = run_experiment.encode_args(args, cloudpickle=use_cloudpickle)
        new_config = {
            run_experiment.ARGS_DATA: args_encoded,
            run_experiment.USE_CLOUDPICKLE: str(int(use_cloudpickle)),
            run_experiment.CLOUDPICKLE_VERSION :cp_version,
        }
        if isinstance(run_mode, ddmode.AzureMode):
            run_mode.log_path = new_log_path
        if isinstance(run_mode, ddmode.GCPMode):
            run_mode.gcp_log_path = new_log_path
        if isinstance(run_mode, ddmode.EC2Mode):
            run_mode.s3_log_path = new_log_path
        return new_config, run_mode

    sweeper.run_sweep_azure(
        target, params, log_path=log_path,
        add_date_to_logname=False,
        postprocess_config_and_run_mode=postprocess_config_and_run_mode,
    )


def _create_mounts():
    NON_CODE_MOUNTS = [
        doodad.MountLocal(**non_code_mapping)
        for non_code_mapping in NON_CODE_DIRS_TO_MOUNT
    ]
    if REPO_DIR not in CODE_DIRS_TO_MOUNT:
        CODE_DIRS_TO_MOUNT.append(REPO_DIR)
    CODE_MOUNTS = [
        doodad.MountLocal(local_dir=code_dir, pythonpath=True)
        for code_dir in CODE_DIRS_TO_MOUNT
    ]
    mounts = CODE_MOUNTS + NON_CODE_MOUNTS
    return mounts


def _create_sweeper_and_output_mount():
    mounts = _create_mounts()
    az_mount = doodad.MountAzure(
        '',
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
    print("OUTPUT_DIR_IS", doodad_config.output_directory)
    with open(doodad_config.output_directory + '/foo_output.txt', "w") as f:
        f.write('sum = {}\n'.format(x + y))

    from doodad.wrappers.easy_launch.metadata import save_doodad_config
    save_doodad_config(doodad_config)


if __name__ == '__main__':
    params = {
        'x': [1,2],
        'y': [3],
    }
    sweep_function(foo, params, log_path='exp_16_save_doodad_config_in_foo')
