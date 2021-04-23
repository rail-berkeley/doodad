from doodad.wrappers.easy_launch import sweep_function, save_doodad_config


def example_function(doodad_config, variant):
    x = variant['x']
    y = variant['y']
    z = variant['z']
    with open(doodad_config.output_directory + '/function_output.txt', "w") as f:
        f.write('sum = {}'.format(x+y+z))
    print('x, y, z = ', x, y, z)
    save_doodad_config(doodad_config)


if __name__ == "__main__":
    params_to_sweep = {
        'x': [1, 2],
        'y': [100],
    }
    default_params = {
        'z': 10,
    }
    for mode in [
        'here_no_doodad',
        'local',
        'azure',
    ]:
        sweep_function(
            example_function,
            params_to_sweep,
            default_params=default_params,
            log_path='test_easy_launch_{}'.format(mode),
            mode=mode,
            use_gpu=True,
        )
