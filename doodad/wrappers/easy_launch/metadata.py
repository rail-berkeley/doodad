"""Store meta-data about the launch."""
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
        ('gpu_id', Union[int, str]),
        ('git_infos', List[GitInfo]),
        ('script_name', str),
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
                pass
    except (ImportError, UnboundLocalError, NameError):
        git_infos = None
    return git_infos
