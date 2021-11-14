"""Store meta-data about the launch."""
import json
import os
import os.path as osp
from typing import NamedTuple, List, Union

import doodad
from doodad.wrappers.easy_launch import config

GitInfo = NamedTuple(
    'GitInfo',
    [
        ('directory', str),
        ('code_diff', str),
        ('code_diff_staged', str),
        ('commit_hash', str),
        ('branch_name', str),
    ],
)
DoodadConfig = NamedTuple(
    'DoodadConfig',
    [
        ('use_gpu', bool),
        ('num_gpu', int),
        ('git_infos', List[GitInfo]),
        ('script_name', str),
        ('output_directory', str),
        ('extra_launch_info', dict),
    ],
)


def generate_git_infos():
    try:
        import git
        doodad_path = osp.abspath(osp.join(
            osp.dirname(doodad.__file__),
            os.pardir
        ))
        dirs = config.CODE_DIRS_TO_MOUNT + [doodad_path]

        git_infos = []
        for directory in dirs:
            # Idk how to query these things, so I'm just doing try-catch
            try:
                repo = git.Repo(directory)
                try:
                    branch_name = repo.active_branch.name
                except TypeError:
                    branch_name = '[DETACHED]'
                git_infos.append(GitInfo(
                    directory=directory,
                    code_diff=repo.git.diff(None),
                    code_diff_staged=repo.git.diff('--staged'),
                    commit_hash=repo.head.commit.hexsha,
                    branch_name=branch_name,
                ))
            except git.exc.InvalidGitRepositoryError:
                git_infos.append(GitInfo(
                    directory=directory,
                    code_diff='',
                    code_diff_staged='',
                    commit_hash='',
                    branch_name='(not a git repo)',
                ))
                pass
    except (UnboundLocalError, NameError) as e:
        print("Error with GitPython: {}".format(e))
        git_infos = []
    except ImportError as e:
        print("Install GitPython to automatically save git information.")
        git_infos = []
    return git_infos


def save_doodad_config(doodad_config: DoodadConfig):
    os.makedirs(doodad_config.output_directory, exist_ok=True)
    save_git_infos(doodad_config.git_infos, doodad_config.output_directory)
    save_script_name(doodad_config.script_name, doodad_config.output_directory)

    with open(osp.join(doodad_config.output_directory, "extra_doodad_info.txt"),
              "w") as f:
        f.write('extra_launch_info:\n')
        f.write(
            json.dumps(doodad_config.extra_launch_info, indent=2)
        )
        f.write('\n')
        f.write('use_gpu={}\n'.format(doodad_config.use_gpu))
        f.write('num_gpu={}\n'.format(doodad_config.num_gpu))


def save_script_name(script_name: str, log_dir: str):
    with open(osp.join(log_dir, "script_name.txt"), "w") as f:
        f.write(script_name)


def save_git_infos(git_infos: List[GitInfo], log_dir: str):
    for (
            directory, code_diff, code_diff_staged, commit_hash, branch_name
    ) in git_infos:
        if directory[-1] == '/':
            diff_file_name = directory[1:-1].replace("/", "-") + ".patch"
            diff_staged_file_name = (
                    directory[1:-1].replace("/", "-") + "_staged.patch"
            )
        else:
            diff_file_name = directory[1:].replace("/", "-") + ".patch"
            diff_staged_file_name = (
                    directory[1:].replace("/", "-") + "_staged.patch"
            )
        if code_diff is not None and len(code_diff) > 0:
            with open(osp.join(log_dir, diff_file_name), "w") as f:
                f.write(code_diff + '\n')
        if code_diff_staged is not None and len(code_diff_staged) > 0:
            with open(osp.join(log_dir, diff_staged_file_name), "w") as f:
                f.write(code_diff_staged + '\n')
        with open(osp.join(log_dir, "git_infos.txt"), "a") as f:
            f.write("directory: {}".format(directory))
            f.write('\n')
            f.write("git hash: {}".format(commit_hash))
            f.write('\n')
            f.write("git branch name: {}".format(branch_name))
            f.write('\n\n')
