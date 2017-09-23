import sh
import shlex
import time
from ebs_deploy import out, get, parse_env_config, parse_option_settings, upload_application_archive, override_scaling
from uuid import uuid4


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
    parser.add_argument('-C', '--check-command',
                        help='Command to run after environment turns green', required=False)
    parser.add_argument("-s", "--copy-previous-size",
                        help="Copy the previous cluster's min/max/desired size", required=False,
                        default=True)

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

    # no zdt for anything but web server
    tier_name = env_config.get('tier_name', 'WebServer')
    if tier_name != 'WebServer':
        raise Exception(
            "Only able to do zero downtime deployments for "
            "WebServer tiers, can't do them for %s" % (tier_name, ))

    # find an available environment name
    out("Determining new environment name...")
    new_env_name = None
    if not helper.environment_exists(args.environment, include_deleted=True):
        new_env_name = args.environment
    else:
        for i in xrange(10):
            temp_env_name = args.environment + '-' + str(i)
            if not helper.environment_exists(temp_env_name, include_deleted=True):
                new_env_name = temp_env_name
                break
    if new_env_name is None:
        raise Exception("Unable to determine new environment name")
    else:
        out("New environment name will be " + new_env_name)

    # find an available cname name
    new_env_cname = cname_prefix + "-" + uuid4().hex[:8]
    out("New environment cname will be " + new_env_cname)

    # find existing environment name
    old_env_name = helper.get_previous_environment_for_subdomain(cname_prefix)

    min_size = None
    max_size = None
    desired_capacity = None

    if old_env_name:
        min_size, max_size, desired_capacity = helper.get_env_sizing_metrics(old_env_name)
        out("Retrieved old cluster sizes from {}: MinSize - {}, MaxSize - {}, DesiredCapacity - {}".format(
            old_env_name, min_size, max_size, desired_capacity))

    should_copy_scaling_sizes = args.copy_previous_size and desired_capacity and max_size and min_size

    if should_copy_scaling_sizes:
        # We want the new cluster to start up with `desired_capacity` instances,
        # so set its min_size to that value. Later, we will adjust.
        option_settings = override_scaling(option_settings, desired_capacity, max_size)
        out("Overriding new cluster sizes: MinSize - {}, MaxSize - {}".format(
            desired_capacity, max_size))


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
                              tier_name=tier_name,
                              tier_type=env_config.get('tier_type'),
                              tier_version=env_config.get('tier_version'))
    helper.wait_for_environments(new_env_name, status='Ready', health='Green', include_deleted=False)

    if old_env_name is None:
        raise Exception("Unable to find current environment with cname: " + cname_prefix)
    out("Current environment name is " + old_env_name)

    env_data = helper.environment_data(new_env_name)

    if args.check_command:
        if callable(args.check_command):
            out("Running check-command function")
            args.check_command(env_data)
            out("check-command passed")
        elif isinstance(args.check_command, basestring):
            command = shlex.split(args.check_command) + [new_env_cname]
            out("Running check-command {}".format(command))
            rc = sh.Command(command[0])(command[1:], _iter=True)
            for line in rc:
                out(line.rstrip())
            out("Exit Code: {}".format(rc.exit_code))

    # we need to readjust the min_size of the new cluster, because it's currently set to the old cluster's
    # desired_capacity
    if should_copy_scaling_sizes and desired_capacity != min_size:
        helper.set_env_sizing_metrics(new_env_name, min_size, max_size)
        out("Resizing new cluster MinSize to {}".format(min_size))
        helper.wait_for_environments(new_env_name, status='Ready', health='Green', include_deleted=False)

    # swap C-Names
    out("Swapping environment cnames")
    helper.swap_environment_cnames(old_env_name, new_env_name)
    helper.wait_for_environments([old_env_name, new_env_name], status='Ready', include_deleted=False)

    # delete the old environment
    if args.termination_delay:
        out("Termination delay specified, sleeping for {} seconds...".format(args.termination_delay))
        time.sleep(args.termination_delay)
    out("Deleting old environment {}".format(old_env_name))
    helper.delete_environment(old_env_name)

    # delete unused
    helper.delete_unused_versions(versions_to_keep=int(get(config, 'app.versions_to_keep', 10)))
