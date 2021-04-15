"""
Usage

args = {
'param1': [1e-3, 1e-2, 1e-2],
'param2': [1,5,10,20],
}

run_sweep_parallel(path_to_script, args)

or

run_sweep_serial(path_to_script, args)

"""
import copy
import itertools
import os
import random

from doodad import mount
from doodad.darchive import archive_builder_docker as archive_builder
from doodad.launch import launch_api
from doodad.wrappers.sweeper import pythonplusplus as ppp


class Sweeper(object):
    """
    Do a grid search over hyperparameters based on a predefined set of
    hyperparameters.
    """
    def __init__(self, hyperparameters, default_parameters=None):
        """

        :param hyperparameters: A dictionary of the form
        ```
        {
            'hp_1': [value1, value2, value3],
            'hp_2': [value1, value2, value3],
            ...
        }
        ```
        This format is like the param_grid in SciKit-Learn:
        http://scikit-learn.org/stable/modules/grid_search.html#exhaustive-grid-search
        :param default_parameters: Default key-value pairs to add to generated
        config.

        Keys with periods in them are converted into nested dictionaries. I.e.
        ```
        {
            'module1.hp1': [value1, value2, value3],
        }
        ```
        will yield a config of the form
        ```
        {
            'module1': {
                'hp1': value1,
            }
        }
        ```
        """
        self._hyperparameters = hyperparameters
        self._default_kwargs = default_parameters or {}
        named_hyperparameters = []
        for name, values in self._hyperparameters.items():
            named_hyperparameters.append(
                [(name, v) for v in values]
            )
        self._hyperparameters_dicts = [
            ppp.dot_map_dict_to_nested_dict(dict(tuple_list))
            for tuple_list in itertools.product(*named_hyperparameters)
        ]

    def __iter__(self):
        """
        Iterate over the hyperparameters in a grid-manner.

        :return: List of dictionaries. Each dictionary is a map from name to
        hyperpameter.
        """
        for hyperparameters in self._hyperparameters_dicts:
            yield ppp.merge_recursive_dicts(
                hyperparameters,
                copy.deepcopy(self._default_kwargs),
                ignore_duplicate_keys_in_second_dict=True,
            )


def chunker(sweeper, num_chunks=10, confirm=True):
    chunks = [ [] for _ in range(num_chunks) ]
    print('computing chunks')
    configs = [config for config in sweeper]
    random.shuffle(configs, random.random)
    for i, config in enumerate(configs):
        chunks[i % num_chunks].append(config)
    print('num chunks:  ', num_chunks)
    print('chunk sizes: ', [len(chunk) for chunk in chunks])
    print('total jobs:  ', sum([len(chunk) for chunk in chunks]))

    resp = 'y'
    if confirm:
        print('continue?(y/n)')
        resp = str(input())

    if resp == 'y':
        return chunks
    else:
        return []


def run_sweep_doodad(
        target, params, run_mode, mounts, test_one=False,
        docker_image='python:3', return_output=False, verbose=False,
        command_suffix=None,
        postprocess_config=lambda x: x,
        default_params=None
):
    # build archive
    target_dir = os.path.dirname(target)
    target_mount_dir = os.path.join('target', os.path.basename(target_dir))
    target_mount = mount.MountLocal(local_dir=target_dir, mount_point=target_mount_dir)
    mounts = list(mounts) + [target_mount]
    target_full_path = os.path.join(target_mount.mount_point, os.path.basename(target))
    command = launch_api.make_python_command(
        target_full_path
    )

    print('Launching jobs with mode %s' % run_mode)
    results = []
    njobs = 0
    with archive_builder.temp_archive_file() as archive_file:
        archive = archive_builder.build_archive(archive_filename=archive_file,
                                                payload_script=command,
                                                verbose=verbose,
                                                docker_image=docker_image,
                                                use_nvidia_docker=run_mode.use_gpu,
                                                mounts=mounts)

        sweeper = Sweeper(params, default_params)
        for config in sweeper:
            config = postprocess_config(config)
            if config is None:
                continue
            njobs += 1
            cli_args= ' '.join(['--%s %s' % (key, config[key]) for key in config])
            cmd = archive + ' -- ' + cli_args
            if command_suffix is not None:
               cmd += command_suffix
            result = run_mode.run_script(cmd, return_output=return_output, verbose=False)
            if return_output:
                result = archive_builder._strip_stdout(result)
                results.append(result)
            if test_one:
                break
    print('Launching completed for %d jobs' % njobs)
    run_mode.print_launch_message()
    return tuple(results)


def run_sweep_doodad_chunked(target, params, run_mode, mounts, num_chunks=10, docker_image='python:3', return_output=False, test_one=False, confirm=True, verbose=False):
    # build archive
    target_dir = os.path.dirname(target)
    target_mount_dir = os.path.join('target', os.path.basename(target_dir))
    target_mount = mount.MountLocal(local_dir=target_dir, mount_point=target_mount_dir)
    mounts = list(mounts) + [target_mount]
    target_full_path = os.path.join(target_mount.mount_point, os.path.basename(target))
    command = launch_api.make_python_command(
        target_full_path
    )

    print('Launching jobs with mode %s' % run_mode)
    results = []
    njobs = 0
    with archive_builder.temp_archive_file() as archive_file:
        archive = archive_builder.build_archive(archive_filename=archive_file,
                                                payload_script=command,
                                                verbose=verbose,
                                                docker_image=docker_image,
                                                use_nvidia_docker=run_mode.use_gpu,
                                                mounts=mounts)

        sweeper = Sweeper(params)
        chunks = chunker(sweeper, num_chunks, confirm=confirm)
        for chunk in chunks:
            command = ''
            for config in chunk:
                njobs += 1
                cli_args=' '.join(['--%s %s' % (key, config[key]) for key in config])
                single_command = archive + ' -- ' + cli_args
                command += '%s;' % single_command

            result = run_mode.run_script(command, return_output=return_output, verbose=False)
            if return_output:
                result = archive_builder._strip_stdout(result)
                results.append(result)
            if test_one:
                break
    print('Launching completed for %d jobs on %d machines' % (njobs, num_chunks))
    run_mode.print_launch_message()
    return tuple(results)

