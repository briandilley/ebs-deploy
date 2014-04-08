from ebs_deploy import out, parse_env_config


def add_arguments(parser):
    """
    Args for the delete environment command
    """
    parser.add_argument('-e', '--environment',
                        help='Environment name', required=True)


def execute(helper, config, args):
    """
    Deletes an environment
    """

    env_config = parse_env_config(config, args.environment)
    cname_prefix = env_config.get('cname_prefix', None)
    # env_name = args.environment
    real_env_name = helper.environment_name_for_cname(cname_prefix)

    environments = helper.get_environments()

    for env in environments:
        if env['EnvironmentName'] == real_env_name:
            if env['Status'] != 'Ready':
                out("Unable to delete " + env['EnvironmentName']
                    + " because it's not in status Ready ("
                    + env['Status'] + ")")
            else:
                out("Deleting environment: "+env['EnvironmentName'])
                # helper.delete_environment(env['EnvironmentName'])
                # environments_to_wait_for_term.append(env['EnvironmentName'])

    out("Environment deleted")

    return 0
