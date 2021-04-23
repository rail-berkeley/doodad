import sys
import time
import os.path as osp

from doodad import mode as ddmode
from doodad.utils import REPO_DIR

import doodad
from doodad.wrappers.easy_launch import run_experiment, metadata
from doodad.wrappers.easy_launch import config
from doodad.wrappers.easy_launch.metadata import save_doodad_config
from doodad.wrappers.sweeper import DoodadSweeper
from doodad.wrappers.sweeper.hyper_sweep import Sweeper


def sweep_function(
        method_call,
        params,
        log_path,
        default_params=None,
        use_cloudpickle=True,
        add_date_to_logname=True,
        mode='azure',
        use_gpu=False,
        num_gpu=1,
        name_runs_by_id=True,
        add_time_to_run_id=True,
        start_run_id=0,
        docker_image=config.DEFAULT_DOCKER,
):
    """
    Usage:
    ```
    def function(doodad_config, variant):
        x = variant['x']
        y = variant['y']
        z = variant['z']
        with open(doodad_config.output_directory + '/function_output.txt', "w") as f:
            f.write('sum = {}'.format(x+y+z))

    params_to_sweep = {
        'x': [1, 4],
        'y': [3, 4],
    }
    default_params = {
        'z': 10,
    }
    sweep_function(
        function,
        params_to_sweep,
        default_params=default_params,
        log_path='my-experiment',
        mode='azure',
    )
    ```
    :param mode: Mode to run this in. Supported modes:
        - 'azure'
        - 'here_no_doodad'
        - 'local'
        - 'gcp' (untested)
    :param method_call: A function that takes in two parameters:
        doodad_config: metadata.DoodadConfig
        variant: dictionary
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
    otherwise, all the runs will be saved to `log_path/` directly. The way path
    collisions are handled depends on the mode.
    :param add_time_to_run_id: If true, append the time to the run id name
    :param start_run_id:
    :return: How many
    """
    if add_date_to_logname:
        datestamp = time.strftime("%y-%m-%d")
        log_path = '%s_%s' % (datestamp, log_path)
    target = osp.join(REPO_DIR, 'doodad/wrappers/easy_launch/run_experiment.py')
    sweeper, output_mount = create_sweeper_and_output_mount(mode, log_path, docker_image)
    git_infos = metadata.generate_git_infos()

    doodad_config = metadata.DoodadConfig(
        use_gpu=use_gpu,
        num_gpu=num_gpu,
        git_infos=git_infos,
        script_name=' '.join(sys.argv),
        output_directory=output_mount.mount_point,
        extra_launch_info={},
    )

    def _create_final_log_path(base_path, run_id):
        if name_runs_by_id:
            path_suffix = '/run{}'.format(start_run_id + run_id)
            if add_time_to_run_id:
                timestamp = time.strftime("%Hh-%Mm-%Ss")
                path_suffix += '_{}'.format(timestamp)
        else:
            path_suffix = ''
        return base_path + path_suffix

    if mode == 'here_no_doodad':
        return _run_method_here_no_doodad(
            method_call,
            doodad_config,
            params,
            default_params,
            log_path,
            _create_final_log_path,
        )

    def postprocess_config_and_run_mode(config, run_mode, config_idx):
        new_log_path = _create_final_log_path(log_path, config_idx)
        args = {
            'method_call': method_call,
            'output_dir': output_mount.mount_point,
            'doodad_config': doodad_config,
            'variant': config,
            'mode': mode,
        }
        if isinstance(run_mode, ddmode.AzureMode):
            run_mode.log_path = new_log_path
        if isinstance(run_mode, ddmode.GCPMode):
            run_mode.gcp_log_path = new_log_path
        if isinstance(run_mode, ddmode.LocalMode):
            args['output_dir'] = _create_final_log_path(
                args['output_dir'], config_idx
            )
        args_encoded, cp_version = run_experiment.encode_args(args, cloudpickle=use_cloudpickle)
        new_config = {
            run_experiment.ARGS_DATA: args_encoded,
            run_experiment.USE_CLOUDPICKLE: str(int(use_cloudpickle)),
            run_experiment.CLOUDPICKLE_VERSION :cp_version,
        }
        return new_config, run_mode

    def _run_sweep():
        if mode == 'azure':
            sweeper.run_sweep_azure(
                target,
                params,
                default_params=default_params,
                log_path=log_path,
                add_date_to_logname=False,
                postprocess_config_and_run_mode=postprocess_config_and_run_mode,
                instance_type=config.DEFAULT_AZURE_INSTANCE_TYPE,
                gpu_model=config.DEFAULT_AZURE_GPU_MODEL,
                use_gpu=use_gpu,
                num_gpu=num_gpu,
                region=config.DEFAULT_AZURE_REGION,
            )
        elif mode == 'gcp':
            sweeper.run_sweep_gcp(
                target,
                params,
                default_params=default_params,
                log_prefix=log_path,
                add_date_to_logname=False,
                postprocess_config_and_run_mode=postprocess_config_and_run_mode,
                num_gpu=num_gpu,
                use_gpu=use_gpu,
            )
        elif mode == 'local':
            sweeper.run_sweep_local(
                target,
                params,
                default_params=default_params,
                postprocess_config_and_run_mode=postprocess_config_and_run_mode,
            )
        else:
            raise ValueError('Unknown mode: {}'.format(mode))

    _run_sweep()


def _run_method_here_no_doodad(
        method_call, doodad_config, params, default_params, log_path,
        create_final_log_path
):
    sweeper = Sweeper(params, default_params)
    for xid, param in enumerate(sweeper):
        new_log_path = create_final_log_path(log_path, xid)
        doodad_config = doodad_config._replace(
            output_directory=osp.join(config.LOCAL_LOG_DIR, new_log_path),
        )
        save_doodad_config(doodad_config)
        method_call(doodad_config, param)


def create_mounts():
    NON_CODE_MOUNTS = [
        doodad.MountLocal(**non_code_mapping)
        for non_code_mapping in config.NON_CODE_DIRS_TO_MOUNT
    ]
    if REPO_DIR not in config.CODE_DIRS_TO_MOUNT:
        config.CODE_DIRS_TO_MOUNT.append(REPO_DIR)
    CODE_MOUNTS = [
        doodad.MountLocal(local_dir=code_dir, pythonpath=True)
        for code_dir in config.CODE_DIRS_TO_MOUNT
    ]
    mounts = CODE_MOUNTS + NON_CODE_MOUNTS
    return mounts


def create_sweeper_and_output_mount(mode, log_path, docker_image):
    mounts = create_mounts()
    az_mount = doodad.MountAzure(
        '',
        mount_point='/output',
    )
    sweeper = DoodadSweeper(
        mounts=mounts,
        docker_img=docker_image,
        azure_subscription_id=config.AZ_SUB_ID,
        azure_storage_connection_str=config.AZ_CONN_STR,
        azure_client_id=config.AZ_CLIENT_ID,
        azure_authentication_key=config.AZ_SECRET,
        azure_tenant_id=config.AZ_TENANT_ID,
        azure_storage_container=config.AZ_CONTAINER,
        mount_out_azure=az_mount,
        local_output_dir=osp.join(config.LOCAL_LOG_DIR, log_path),  # TODO: how to make this vary in local mode?
    )
    # TODO: the sweeper should probably only have one output mount that is
    # set rather than read based on the mode
    if mode == 'azure':
        output_mount = sweeper.mount_out_azure
    elif mode == 'gcp':
        output_mount = sweeper.mount_out_gcp
    elif mode == 'here_no_doodad':
        output_mount = sweeper.mount_out_local  # this will be ignored
    elif mode == 'local':
        output_mount = sweeper.mount_out_local
    else:
        raise ValueError('Unknown mode: {}'.format(mode))
    return sweeper, output_mount
