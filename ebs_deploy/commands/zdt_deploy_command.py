import time
from ebs_deploy import out, get, parse_env_config, parse_option_settings, upload_application_archive


def add_arguments(parser):
    """
    adds arguments for the deploy command
    """
    parser.add_argument('-e', '--environment', help='Environment name', required=True)
    parser.add_argument('-w', '--dont-wait', help='Skip waiting', action='store_true')
    parser.add_argument('-a', '--archive', help='Archive file', required=False)
    parser.add_argument('-d', '--directory', help='Directory', required=False)
    parser.add_argument('-l', '--version-label', help='Version label', required=False)
    parser.add_argument('-t', '--termination-delay',
                        help='Delay termination of old environment by this number of seconds',
                        type=int, required=False)


def execute(helper, config, args):
    """
    Deploys to an environment
    """
    version_label = args.version_label
    archive = args.archive

    # get the environment configuration
    env_config = parse_env_config(config, args.environment)
    option_settings = parse_option_settings(env_config.get('option_settings', {}))
    cname_prefix = env_config.get('cname_prefix', None)

    # find existing environment name
    old_env_name = helper.environment_name_for_cname(cname_prefix)
    if old_env_name is None:
        raise Exception("Unable to find current environment with cname: " + cname_prefix)
    out("Current environment name is " + old_env_name)

    # find an available environment name
    out("Determining new environment name...")
    new_env_name = None
    if not helper.environment_exists(args.environment):
        new_env_name = args.environment
    else:
        for i in xrange(10):
            temp_env_name = args.environment + '-' + str(i)
            if not helper.environment_exists(temp_env_name):
                new_env_name = temp_env_name
                break
    if new_env_name is None:
        raise Exception("Unable to determine new environment name")
    out("New environment name will be " + new_env_name)

    # find an available cname name
    out("Determining new environment cname...")
    new_env_cname = None
    for i in xrange(10):
        temp_cname = cname_prefix + '-' + str(i)
        if not helper.environment_name_for_cname(temp_cname):
            new_env_cname = temp_cname
            break
    if new_env_cname is None:
        raise Exception("Unable to determine new environment cname")
    out("New environment cname will be " + new_env_cname)

    # upload or build an archive
    version_label = upload_application_archive(
        helper, env_config, archive=args.archive, directory=args.directory, version_label=version_label)

    # create the new environment
    helper.create_environment(new_env_name,
                              solution_stack_name=env_config.get('solution_stack_name'),
                              cname_prefix=new_env_cname,
                              description=env_config.get('description', None),
                              option_settings=option_settings,
                              version_label=version_label,
                              tier_name=env_config.get('tier_name'),
                              tier_type=env_config.get('tier_type'),
                              tier_version=env_config.get('tier_version'))
    helper.wait_for_environments(new_env_name, status='Ready', health='Green', include_deleted=False)

    # swap C-Names
    out("Swapping environment cnames")
    helper.swap_environment_cnames(old_env_name, new_env_name)
    helper.wait_for_environments([old_env_name, new_env_name], status='Ready', include_deleted=False)

    # delete the old environment
    if args.termination_delay:
        out("Termination delay specified, sleeping for {} seconds...".format(args.termination_delay))
        time.sleep(args.termination_delay)
    helper.delete_environment(old_env_name)

    # delete unused
    helper.delete_unused_versions(versions_to_keep=int(get(config, 'app.versions_to_keep', 10)))
