
from ebs_deploy import out, get, parse_env_config, parse_option_settings, upload_application_archive

def add_arguments(parser):
    """
    adds arguments for the deploy command
    """
    parser.add_argument('-e', '--environment',      help='Environment name', required=True)
    parser.add_argument('-w', '--dont-wait',        help='Skip waiting for the init to finish', action='store_true')
    parser.add_argument('-a', '--archive',          help='Archive file', required=False)
    parser.add_argument('-d', '--directory',        help='Directory', required=False)
    parser.add_argument('-l', '--version-label',    help='Version label', required=False)

def execute(helper, config, args):
    """
    Deploys to an environment
    """
    version_label = args.version_label
    archive = args.archive
    env_config = parse_env_config(config, args.environment)
    cname_prefix = env_config.get('cname_prefix', None)
    env_name = args.environment
    real_env_name = helper.environment_name_for_cname(cname_prefix)

    # upload or build an archive
    version_label = upload_application_archive(
        helper, env_config, archive=args.archive, directory=args.directory, version_label=version_label)

    # deploy it
    helper.deploy_version(real_env_name, version_label)

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(real_env_name, status='Ready', version_label=version_label, include_deleted=False)

    # update it
    env = parse_env_config(config, env_name)
    option_settings = parse_option_settings(env.get('option_settings', {}))
    helper.update_environment(real_env_name,
        description=env.get('description', None),
        option_settings=option_settings,
        tier_type=env.get('tier_type'),
        tier_name=env.get('tier_name'),
        tier_version=env.get('tier_version'))

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(real_env_name, health='Green', status='Ready', version_label=version_label, include_deleted=False)

    # delete unused
    helper.delete_unused_versions(versions_to_keep=int( get(config, 'app.versions_to_keep', 10) ))