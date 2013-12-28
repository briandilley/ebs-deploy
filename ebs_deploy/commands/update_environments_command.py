
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def add_arguments(parser):
    """
    Args for the init command
    """
    parser.add_argument('-e', '--environment',  help='Environment name', required=False, nargs='+')
    parser.add_argument('-w', '--dont-wait', help='Skip waiting for the app to be deleted', action='store_true')

def execute(helper, config, args):
    """
    Updates environments
    """
    environments = []
    if args.environment:
        for env_name in args.environment:
            environments.append(env_name)
    else:
        for env_name, env_config in get(config, 'app.environments').items():
            environments.append(env_name)

    wait_environments = []
    for env_name in environments:
        env = parse_env_config(config, env_name)
        option_settings = parse_option_settings(env.get('option_settings', {}))
        cname_prefix = env.get('cname_prefix', None)
        real_env_name = helper.environment_name_for_cname(cname_prefix)
        helper.update_environment(real_env_name,
            description=env.get('description', None),
            option_settings=option_settings,
            tier_type=env.get('tier_type'),
            tier_name=env.get('tier_name'),
            tier_version=env.get('tier_version'))
        wait_environments.append(real_env_name)

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(wait_environments, health='Green', status='Ready')
