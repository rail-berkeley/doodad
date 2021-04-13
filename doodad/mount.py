"""
These objects are pointers to code/data you wish to give access
to a launched job.

Each object defines a source and a mount point (where the directory will be visible
to the launched process)

"""
import os
import shutil
import tarfile
import tempfile
from contextlib import contextmanager

from doodad.apis import aws_util
from doodad import utils


class Mount(object):
    """
    Args:
        mount_point (str): Location of directory visible to the running process *inside* container
        pythonpath (bool): If True, adds this folder to the $PYTHONPATH environment variable
        output (bool): If False, this is a "code" directory. If True, this should be an empty
            "output" directory (nothing will be copied to remote)
    """
    def __init__(self, mount_point=None, pythonpath=False, output=False):
        self.pythonpath = pythonpath
        self.read_only = not output
        self.mount_point = mount_point
        self._name = None
        self.local_dir = None

    def dar_build_archive(self, deps_dir):
        raise NotImplementedError()

    def dar_extract_command(self):
        raise NotImplementedError()

    @property
    def writeable(self):
        return not self.read_only

    @property
    def name(self):
        return self._name

    def __str__(self):
        return '%s@%s'% (type(self).__name__, self.name)


class MountLocal(Mount):
    """
    """
    def __init__(self, local_dir, mount_point=None, cleanup=True,
                filter_ext=('.pyc', '.log', '.git', '.mp4'),
                filter_dir=('data', '.git'),
                delete_before_mount=True,
                **kwargs):
        """

        :param local_dir:
        :param mount_point:
        :param cleanup:
        :param filter_ext:
        :param filter_dir:
        :param delete_before_mount: If True, then if you mount to an existing
        directory, then the contents of that directory will be deleted before
        mounting. In other words, the behavior is
        ```
        $ rm -rf mount_point
        $ mv local_dir mount_point
        ```
        Default is True because this follows standard mounting behavior, in
        which the original mount point is invisible if it existed.

        If False, then the contents of local_dir are copied to the mount_point,
        with individual files being overwritten but not necessarily the entire
        directory. In other words, the behavior is
        ```
        $ mv local_dir/* mount_point/*
        ```
        So, existing files in `mount_point/` will not change unless they are
        overwritten by corresponding files in `local_dir/`.

        :param kwargs:
        """
        super(MountLocal, self).__init__(mount_point=mount_point, **kwargs)
        self.local_dir = os.path.realpath(os.path.expanduser(local_dir))
        self._name = self.local_dir.replace('/', '_')
        self.sync_dir = self.local_dir
        self.cleanup = cleanup
        self.filter_ext = filter_ext
        self.filter_dir = filter_dir
        self.delete_before_mount = delete_before_mount
        if mount_point is None:
            self.mount_point = self.local_dir
        else:
            assert not self.mount_point.endswith('/'), "Do not end mount points with backslash:"+self.mount_point
        if self.writeable:
            if not self.mount_point.startswith('/'):
                raise ValueError('Output mount points must be absolute')
            if not self.local_dir.startswith('/'):
                raise ValueError('Output local directories must be absolute')

    def ignore_patterns(self, dirname, contents):
        to_ignore = []
        for content in contents:
            if any([content.endswith(ext) for ext in self.filter_ext]):
                to_ignore.append(content)
            elif any([content == _dirname for _dirname in self.filter_dir]):
                to_ignore.append(content)
        return to_ignore

    def dar_build_archive(self, deps_dir):
        utils.makedirs(os.path.join(deps_dir, 'local'))
        dep_dir = os.path.join(deps_dir, 'local', self.name)
        extract_file = os.path.join(dep_dir, 'extract.sh')
        mount_dir = os.path.dirname(self.mount_point)

        if self.read_only:
            shutil.copytree(self.local_dir, dep_dir, ignore=self.ignore_patterns)
        else:
            os.makedirs(dep_dir)
        with open(extract_file, 'w') as f:
            if self.read_only:
                f.write('mkdir -p %s\n' % mount_dir)
                if self.delete_before_mount:
                    f.write('rm -rf  {mount}\n'.format(mount=self.mount_point))
                    f.write('mkdir -p %s\n' % self.mount_point)
                f.write('mv ./deps/local/{name}/* {mount}/\n'.format(name=self.name, mount=self.mount_point))
            else:
                f.write('mkdir -p %s\n' % mount_dir)
            if self.pythonpath:
                f.write('export PYTHONPATH=$PYTHONPATH:{mount_dir}\n'.format(mount_dir=mount_dir))
        os.chmod(extract_file, 0o777)

    def dar_extract_command(self):
        return './deps/local/{name}/extract.sh'.format(
            name=self.name,
        )

    def __str__(self):
        return 'MountLocal@%s'%self.local_dir

    def docker_mount_dir(self):
         return os.path.join('/mounts', self.mount_point.replace('~/',''))


class MountGit(Mount):
    def __init__(self, git_url, branch=None,
                 ssh_identity=None, **kwargs):
        super(MountGit, self).__init__(output=False, **kwargs)
        self.git_url = git_url
        self.repo_name = os.path.splitext(os.path.split(git_url)[1])[0]
        assert self.mount_point.endswith(self.repo_name)
        self.ssh_identity = ssh_identity
        if ssh_identity is not None:
            self.ssh_identity = os.path.expanduser(ssh_identity)
        self.branch = branch
        self._name = self.repo_name

    def dar_build_archive(self, deps_dir):
        dep_dir = os.path.join(deps_dir, 'git', self.name)
        os.makedirs(dep_dir)

        extract_file = os.path.join(dep_dir, 'extract.sh')
        with open(extract_file, 'w') as f:
            mount_point = os.path.dirname(self.mount_point)
            f.write('mkdir -p %s\n' % mount_point)
            f.write('pushd %s > /dev/null\n' % mount_point)
            if self.ssh_identity:
                shutil.copy(self.ssh_identity, dep_dir)
                id_file = os.path.split(self.ssh_identity)[1]
                id_file = os.path.join('/dar_payload/deps/git/{name}'.format(name=self.name), id_file)
                f.write("GIT_SSH_COMMAND='ssh -o StrictHostKeyChecking=no -i {id}' git clone --quiet {repo_url}\n".format(id=id_file, repo_url=self.git_url))
            else:
                f.write("git clone --quiet {repo_url}\n".format(repo_url=self.git_url))
            if self.branch:
                f.write('cd {repo_name}\n'.format(repo_name=self.repo_name))
                f.write('git checkout --quiet {branch}\n'.format(branch=self.branch))
            if self.pythonpath:
                f.write('export PYTHONPATH=$PYTHONPATH:{repo_dir}\n'.format(repo_dir=os.path.join(mount_point, self.repo_name)))
            f.write('popd > /dev/null\n')
        os.chmod(extract_file, 0o777)

    def dar_extract_command(self):
        return './deps/git/{name}/extract.sh'.format(
            name=self.name,
        )


class MountS3(Mount):
    def __init__(self,
                s3_path,
                **kwargs):
        super(MountS3, self).__init__(output=True, **kwargs)
        # load from config
        if s3_path.startswith('/'):
            raise NotImplementedError('Local dir cannot be absolute')
        else:
            # We store everything into a fixed dir /doodad on the remote machine
            # so EC2Mode knows to simply sync /doodad
            # (this is b/c we no longer pass in mounts to the launch mode)
            self.sync_dir = os.path.join('/doodad', s3_path)
        self._name = self.sync_dir.replace('/', '_')

    def dar_build_archive(self, deps_dir):
        return

    def dar_extract_command(self):
        return 'echo helloMountS3'


class MountGCP(Mount):
    def __init__(self,
                gcp_path=None,
                **kwargs):
        """

        Args:
            gcp_path (str): Path underneath bucket. The full path will become
                gs://{gcp_bucket}/{gcp_path}
        """
        super(MountGCP, self).__init__(output=True, **kwargs)
        # load from config
        if gcp_path.startswith('/'):
            raise NotImplementedError('Local dir cannot be absolute')
        else:
            # We store everything into a fixed dir /doodad on the remote machine
            # so GCPMode knows to simply sync /doodad
            # (this is b/c we no longer pass in mounts to the launch mode)
            self.sync_dir = os.path.join('/doodad', gcp_path)
        self._name = self.sync_dir.replace('/', '_')

    def dar_build_archive(self, deps_dir):
        return

    def dar_extract_command(self):
        return 'echo helloMountGCP'


class MountAzure(Mount):
    def __init__(self,
                 azure_path=None,
                 **kwargs):
        """
        Args:
            azure_path (str): Path to mount in the synced Azure container. This will become /doodad/{log_path}/{azure_path},
                where log_path comes from AzureMode launch argument.
        """
        super(MountAzure, self).__init__(output=True, **kwargs)
        # load from config
        if azure_path.startswith('/'):
            raise NotImplementedError('Local dir cannot be absolute')
        else:
            self.sync_dir = os.path.join('/doodad', azure_path)
        self._name = self.sync_dir.replace('/', '_')

    def dar_build_archive(self, deps_dir):
        return

    def dar_extract_command(self):
        return 'echo helloMountAzure'

