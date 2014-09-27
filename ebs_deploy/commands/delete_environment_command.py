from ebs_deploy import out, parse_env_config


def add_arguments(parser):
    """
    Args for the delete environment command
    """
    parser.add_argument('-e', '--environment',
                        help='Environment name', required=True)
    parser.add_argument('-w', '--dont-wait',
                        help='Skip waiting for the init to finish',
                        action='store_true')


def execute(helper, config, args):
    """
    Deletes an environment
    """

    env_config = parse_env_config(config, args.environment)
    environments_to_wait_for_term = []
    environments = helper.get_environments()

    for env in environments:
        if env['EnvironmentName'] == args.environment:
            if env['Status'] != 'Ready':
                out("Unable to delete " + env['EnvironmentName']
                    + " because it's not in status Ready ("
                    + env['Status'] + ")")
            else:
                out("Deleting environment: "+env['EnvironmentName'])
                helper.delete_environment(env['EnvironmentName'])
                environments_to_wait_for_term.append(env['EnvironmentName'])

    if not args.dont_wait:
        helper.wait_for_environments(environments_to_wait_for_term,
                                     status='Terminated',
                                     include_deleted=True)

    out("Environment deleted")
    return 0
