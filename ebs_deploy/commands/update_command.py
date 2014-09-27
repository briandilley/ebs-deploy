
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def add_arguments(parser):
    """
    adds arguments for the deploy command
    """
    parser.add_argument('-e', '--environment',      help='Environment name', required=True)
    parser.add_argument('-w', '--dont-wait',        help='Skip waiting for the init to finish', action='store_true')
    parser.add_argument('-l', '--version-label',    help='Version label', required=False)

def execute(helper, config, args):
    """
    Deploys to an environment
    """
    env_config = parse_env_config(config, args.environment)
    cname_prefix = env_config.get('cname_prefix', None)
    env_name = args.environment

    # change version
    if args.version_label:
        helper.deploy_version(env_name, args.version_label)
        if not args.dont_wait:
            helper.wait_for_environments(env_name, status='Ready', version_label=args.version_label)

    # update it
    env = parse_env_config(config, env_name)
    option_settings = parse_option_settings(env.get('option_settings', {}))
    helper.update_environment(env_name,
        description=env.get('description', None),
        option_settings=option_settings,
        tier_type=env.get('tier_type'),
        tier_name=env.get('tier_name'),
        tier_version=env.get('tier_version'))

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(env_name, health='Green', status='Ready', version_label=args.version_label)

    # delete unused
    helper.delete_unused_versions(versions_to_keep=int( get(config, 'app.versions_to_keep', 10) ))