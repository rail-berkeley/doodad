"""
By defining these utility functions in this file, this file has no dependency
on doodad.
"""
import pickle
import base64
import argparse


ARGS_DATA = 'DOODAD_ARGS_DATA'
USE_CLOUDPICKLE = 'DOODAD_USE_CLOUDPICKLE'
CLOUDPICKLE_VERSION = 'DOODAD_CLOUDPICKLE_VERSION'


def _get_args_dict():
    parser = argparse.ArgumentParser()
    parser.add_argument('--'+USE_CLOUDPICKLE, type=bool, default=False)
    parser.add_argument('--'+ARGS_DATA, type=str, default='')
    parser.add_argument('--'+CLOUDPICKLE_VERSION, type=str, default='')
    args = parser.parse_args()

    return vars(args)


def get_args(key=None, default=None):
    args = _get_args_dict()

    if args[ARGS_DATA]:
        if args[USE_CLOUDPICKLE]:
            import cloudpickle
            assert args[CLOUDPICKLE_VERSION] == cloudpickle.__version__, "Cloudpickle versions do not match! (host) %s vs (remote) %s" % (args[CLOUDPICKLE_VERSION], cloudpickle.__version__)
            data = cloudpickle.loads(base64.b64decode(args[ARGS_DATA]))
        else:
            data = pickle.loads(base64.b64decode(args[ARGS_DATA]))
    else:
        data = {}

    if key is not None:
        return data.get(key, default)
    return data


def encode_args(call_args, cloudpickle=False):
    """
    Encode call_args dictionary as a base64 string
    """
    assert isinstance(call_args, dict)

    if cloudpickle:
        import cloudpickle
        cpickle_version = cloudpickle.__version__
        data = base64.b64encode(cloudpickle.dumps(call_args)).decode("utf-8")
    else:
        data = base64.b64encode(pickle.dumps(call_args)).decode("utf-8")
        cpickle_version = 'n/a'
    return data, cpickle_version


if __name__ == "__main__":
    import sys
    with open('/output/test_from_doodad', "a") as f:
        f.write("this is a test. argv = {}".format(sys.argv))
    print('hello123')

    from rlkit.core import logger
    text_log_path = '/output/debug.log'
    logger.add_text_output(text_log_path)
    logger.set_snapshot_dir('/output/')
    logger.log('hello123')

    import torch

    import rlkit.torch.pytorch_util as ptu
    logger.log(str(torch.__version__))
    if torch.cuda.is_available():
        x = torch.randn(3)
        logger.log(str(x.to(ptu.device)))

    logger.log("start mujoco")
    import mujoco_py
    logger.log("imported mujoco")
    from gym.envs.mujoco import HalfCheetahEnv
    e = HalfCheetahEnv()
    img = e.sim.render(32, 32)
    logger.log(str(sum(img)))
    logger.log("end mujoco_py")

    import matplotlib
    matplotlib.use('agg')

    args_dict = get_args()
    logger.log(str(args_dict))
    print('args_dict', args_dict)
    print('args_dict', args_dict.keys())
    method_call = args_dict['method_call']
    doodad_config = args_dict['doodad_config']
    variant = args_dict['variant']
    output_dir = args_dict['output_dir']
    run_mode = args_dict.get('mode', None)
    logger.log(str(doodad_config))
    logger.log(str(variant))
    logger.log(str(output_dir))
    if run_mode and run_mode in ['slurm_singularity', 'sss', 'htp']:
        import os
        doodad_config.extra_launch_info['slurm-job-id'] = os.environ.get(
            'SLURM_JOB_ID', None
        )
    if run_mode and (run_mode in {'ec2', 'gcp', 'azure'}):
        if run_mode == 'ec2':
            try:
                import urllib.request
                instance_id = urllib.request.urlopen(
                    'http://169.254.169.254/latest/meta-data/instance-id'
                ).read().decode()
                doodad_config.extra_launch_info['EC2_instance_id'] = instance_id
            except Exception as e:
                print("Could not get AWS instance ID. Error was...")
                print(e)
        if run_mode == 'gcp':
            try:
                import urllib.request
                request = urllib.request.Request(
                    "http://metadata/computeMetadata/v1/instance/name",
                )
                # See this URL for why we need this header:
                # https://cloud.google.com/compute/docs/storing-retrieving-metadata
                request.add_header("Metadata-Flavor", "Google")
                instance_name = urllib.request.urlopen(request).read().decode()
                doodad_config.extra_launch_info['GCP_instance_name'] = (
                    instance_name
                )
            except Exception as e:
                print("Could not get GCP instance name. Error was...")
                print(e)
        # Do this in case base_log_dir was already set
        doodad_config = doodad_config._replace(
            base_log_dir=output_dir,
        )

    import os
    import os.path as osp
    if not osp.exists(output_dir):
        os.mkdir(output_dir)

    method_call(doodad_config, variant)
