from boto.exception import S3ResponseError, BotoServerError
from boto.s3.connection import S3Connection
from boto.ec2.autoscale import AutoScaleConnection
from boto.beanstalk import connect_to_region
from boto.s3.key import Key

from datetime import datetime
from time import time, sleep
import zipfile
import os
import subprocess
import sys
import yaml
import re
import logging


logger = None
LOGGER_NAME = 'ebs_deploy'
MAX_RED_SAMPLES = 20


def out(message):
    """
    print alias
    """
    if logger:
        logger.info("%s", message)
    else:
        sys.stdout.write(message + "\n")
        sys.stdout.flush()


def init_logging(use_logging=False):
    global logger

    if use_logging:
        logger = logging.getLogger(LOGGER_NAME)


def configure_logging(level, handlers):
    l = logging.getLogger(LOGGER_NAME)
    l.setLevel(level)
    for h in l.handlers[:]:
        l.removeHandler(h)
    for h in handlers:
        l.addHandler(h)
    return l


def merge_dict(dict1, dict2):
    ret = dict(dict2)
    for key, val in dict1.items():
        val2 = dict2.get(key)
        if val2 is None:
            ret[key] = val
        elif isinstance(val, dict) and isinstance(val2, dict):
            ret[key] = merge_dict(val, val2)
        elif isinstance(val, (list,)) and isinstance(val2, (list,)):
            ret[key] = val + val2
        else:
            ret[key] = val2
    return ret


def get(vals, key, default_val=None):
    """
    Returns a dictionary value
    """
    val = vals
    for part in key.split('.'):
        if isinstance(val, dict):
            val = val.get(part, None)
            if val is None:
                return default_val
        else:
            return default_val
    return val


def parse_option_settings(option_settings):
    """
    Parses option_settings as they are defined in the configuration file
    """
    ret = []
    for namespace, params in option_settings.items():
        for key, value in params.items():
            ret.append((namespace, key, value))
    return ret


def override_scaling(option_settings, min_size, max_size):
    """ takes the merged option_settings and injects custom min/max autoscaling sizes """
    match_namespace = "aws:autoscaling:asg"
    match_keys = {"MinSize": min_size, "MaxSize": max_size}

    copied_option_settings = []
    for (namespace, key, value) in option_settings:
        new_option = (namespace, key, value)
        if match_namespace == namespace and key in match_keys:
            new_option = (namespace, key, match_keys[key])
        copied_option_settings.append(new_option)

    return copied_option_settings


def parse_env_config(config, env_name):
    """
    Parses an environment config
    """
    all_env = get(config, 'app.all_environments', {})
    env = get(config, 'app.environments.' + str(env_name), {})
    return merge_dict(all_env, env)


def upload_application_archive(helper, env_config, archive=None, directory=None, version_label=None):
    if version_label is None:
        version_label = datetime.now().strftime('%Y%m%d_%H%M%S')
    else:
        # don't attempt to create an application version which already exists
        existing_version_labels = [version['VersionLabel'] for version in helper.get_versions()]
        if version_label in existing_version_labels:
            return version_label

    archive_file_name = None
    if archive:
        archive_file_name = os.path.basename(archive)

    archive_files = get(env_config, 'archive.files', [])

    # generate the archive externally
    if get(env_config, 'archive.generate'):
        cmd = get(env_config, 'archive.generate.cmd')
        output_file = get(env_config, 'archive.generate.output_file')
        use_shell = get(env_config, 'archive.generate.use_shell', True)
        exit_code = get(env_config, 'archive.generate.exit_code', 0)
        if not cmd or not output_file:
            raise Exception('Archive generation requires cmd and output_file at a minimum')
        output_regex = None
        try:
            output_regex = re.compile(output_file)
        except:
            pass
        result = subprocess.call(cmd, shell=use_shell)
        if result != exit_code:
            raise Exception('Generate command execited with code %s (expected %s)' % (result, exit_code))

        if output_file and os.path.exists(output_file):
            archive_file_name = os.path.basename(output_file)
        else:
            for root, dirs, files in os.walk(".", followlinks=True):
                for f in files:
                    fullpath = os.path.join(root, f)
                    if fullpath.endswith(output_file):
                        archive = fullpath
                        archive_file_name = os.path.basename(fullpath)
                        break
                    elif output_regex and output_regex.match(fullpath):
                        archive = fullpath
                        archive_file_name = os.path.basename(fullpath)
                        break
                if archive:
                    break
            if not archive or not archive_file_name:
                raise Exception('Unable to find expected output file matching: %s' % (output_file))

    # create the archive
    elif not archive:
        if not directory:
            directory = "."
        includes = get(env_config, 'archive.includes', [])
        excludes = get(env_config, 'archive.excludes', [])

        def _predicate(f):
            for exclude in excludes:
                if re.match(exclude, f):
                    return False
            if len(includes) > 0:
                for include in includes:
                    if re.match(include, f):
                        return True
                return False
            return True
        archive = create_archive(directory, str(version_label) + ".zip", config=archive_files, ignore_predicate=_predicate)
        archive_file_name = str(version_label) + ".zip"

    add_config_files_to_archive(directory, archive, config=archive_files)
    helper.upload_archive(archive, archive_file_name)
    helper.create_application_version(version_label, archive_file_name)
    return version_label


def create_archive(directory, filename, config={}, ignore_predicate=None, ignored_files=['.git', '.svn']):
    """
    Creates an archive from a directory and returns
    the file that was created.
    """
    with zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED) as zip_file:
        root_len = len(os.path.abspath(directory))

        # create it
        out("Creating archive: " + str(filename))
        for root, dirs, files in os.walk(directory, followlinks=True):
            archive_root = os.path.abspath(root)[root_len + 1:]
            for f in files:
                fullpath = os.path.join(root, f)
                archive_name = os.path.join(archive_root, f)

                # ignore the file we're creating
                if filename in fullpath:
                    continue

                # ignored files
                if ignored_files is not None:
                    for name in ignored_files:
                        if fullpath.endswith(name):
                            out("Skipping: " + str(name))
                            continue

                # do predicate
                if ignore_predicate is not None:
                    if not ignore_predicate(archive_name):
                        out("Skipping: " + str(archive_name))
                        continue

                out("Adding: " + str(archive_name))
                zip_file.write(fullpath, archive_name, zipfile.ZIP_DEFLATED)

    return filename


def add_config_files_to_archive(directory, filename, config={}):
    """
    Adds configuration files to an existing archive
    """
    with zipfile.ZipFile(filename, 'a') as zip_file:
        for conf in config:
            for conf, tree in conf.items():
                if tree.has_key('yaml'):
                    content = yaml.dump(tree['yaml'], default_flow_style=False)
                else:
                    content = tree.get('content', '')
                out("Adding file " + str(conf) + " to archive " + str(filename))
                file_entry = zipfile.ZipInfo(conf)
                file_entry.external_attr = tree.get('permissions', 0644) << 16L 
                zip_file.writestr(file_entry, content)

    return filename


class AwsCredentials:
    """
    Class for holding AwsCredentials
    """

    def __init__(self, access_key, secret_key, security_token, region, bucket, bucket_path):
        self.access_key = access_key
        self.secret_key = secret_key
        self.security_token = security_token
        self.bucket = bucket
        self.region = region
        self.bucket_path = bucket_path
        if not self.bucket_path.endswith('/'):
            self.bucket_path += '/'


class EbsHelper(object):
    """
    Class for helping with ebs
    """

    def __init__(self, aws, wait_time_secs, app_name=None,):
        """
        Creates the EbsHelper
        """
        self.aws = aws
        self.ebs = connect_to_region(aws.region, aws_access_key_id=aws.access_key,
                                     aws_secret_access_key=aws.secret_key,
                                     security_token=aws.security_token)
        self.autoscale = AutoScaleConnection(aws_access_key_id=aws.access_key,
                                             aws_secret_access_key=aws.secret_key,
                                             security_token=aws.security_token)
        self.s3 = S3Connection(
            aws_access_key_id=aws.access_key, 
            aws_secret_access_key=aws.secret_key, 
            security_token=aws.security_token,
            host=(lambda r: 's3.amazonaws.com' if r == 'us-east-1' else 's3-' + r + '.amazonaws.com')(aws.region))
        self.app_name = app_name
        self.wait_time_secs = wait_time_secs

    def swap_environment_cnames(self, from_env_name, to_env_name):
        """
        Swaps cnames for an environment
        """
        self.ebs.swap_environment_cnames(source_environment_name=from_env_name,
                                         destination_environment_name=to_env_name)

    def upload_archive(self, filename, key, auto_create_bucket=True):
        """
        Uploads an application archive version to s3
        """
        try:
            bucket = self.s3.get_bucket(self.aws.bucket)
            if ((
                  self.aws.region != 'us-east-1' and self.aws.region != 'eu-west-1') and bucket.get_location() != self.aws.region) or (
                  self.aws.region == 'us-east-1' and bucket.get_location() != '') or (
                  self.aws.region == 'eu-west-1' and bucket.get_location() != 'eu-west-1'):
                raise Exception("Existing bucket doesn't match region")
        except S3ResponseError:
            bucket = self.s3.create_bucket(self.aws.bucket, location=self.aws.region)

        def __report_upload_progress(sent, total):
            if not sent:
                sent = 0
            if not total:
                total = 0
            out("Uploaded " + str(sent) + " bytes of " + str(total) \
                + " (" + str(int(float(max(1, sent)) / float(total) * 100)) + "%)")

        # upload the new version
        k = Key(bucket)
        k.key = self.aws.bucket_path + key
        k.set_metadata('time', str(time()))
        k.set_contents_from_filename(filename, cb=__report_upload_progress, num_cb=10)

    def list_available_solution_stacks(self):
        """
        Returns a list of available solution stacks
        """
        stacks = self.ebs.list_available_solution_stacks()
        return stacks['ListAvailableSolutionStacksResponse']['ListAvailableSolutionStacksResult']['SolutionStacks']

    def create_application(self, description=None):
        """
        Creats an application and sets the helpers current
        app_name to the created application
        """
        out("Creating application " + str(self.app_name))
        self.ebs.create_application(self.app_name, description=description)

    def delete_application(self):
        """
        Creats an application and sets the helpers current
        app_name to the created application
        """
        out("Deleting application " + str(self.app_name))
        self.ebs.delete_application(self.app_name, terminate_env_by_force=True)

    def application_exists(self):
        """
        Returns whether or not the given app_name exists
        """
        response = self.ebs.describe_applications(application_names=[self.app_name])
        return len(response['DescribeApplicationsResponse']['DescribeApplicationsResult']['Applications']) > 0

    def create_environment(self, env_name, version_label=None,
                           solution_stack_name=None, cname_prefix=None, description=None,
                           option_settings=None, tier_name='WebServer', tier_type='Standard', tier_version='1.1'):
        """
        Creates a new environment
        """
        out("Creating environment: " + str(env_name) + ", tier_name:" + str(tier_name) + ", tier_type:" + str(tier_type))
        self.ebs.create_environment(self.app_name, env_name,
                                    version_label=version_label,
                                    solution_stack_name=solution_stack_name,
                                    cname_prefix=cname_prefix,
                                    description=description,
                                    option_settings=option_settings,
                                    tier_type=tier_type,
                                    tier_name=tier_name,
                                    tier_version=tier_version)

    def environment_exists(self, env_name, include_deleted=False):
        """
        Returns whether or not the given environment exists
        """
        response = self.ebs.describe_environments(application_name=self.app_name, environment_names=[env_name],
                                                  include_deleted=include_deleted)
        return len(response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']) > 0 \
               and response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments'][0][
                       'Status'] != 'Terminated'

    def environment_resources(self, env_name):
        """
        Returns the description for the given environment's resources
        """
        resp = self.ebs.describe_environment_resources(environment_name=env_name)
        return resp['DescribeEnvironmentResourcesResponse']['DescribeEnvironmentResourcesResult']['EnvironmentResources']

    def get_env_sizing_metrics(self, env_name):
        asg = self.get_asg(env_name)
        return asg.min_size, asg.max_size, asg.desired_capacity

    def get_asg(self, env_name):
        asg_name = self.get_asg_name(env_name)
        asg = self.autoscale.get_all_groups(names=[asg_name])[0]
        return asg

    def get_asg_name(self, env_name):
        resources = self.environment_resources(env_name)
        name = resources["AutoScalingGroups"][0]["Name"]
        return name

    def set_env_sizing_metrics(self, env_name, min_size, max_size):
        self.update_environment(env_name, option_settings=[
            ("aws:autoscaling:asg", "MinSize", min_size), ("aws:autoscaling:asg", "MaxSize", max_size)])

    def environment_data(self, env_name):
        """
        Returns the description for the given environment
        """
        response = self.ebs.describe_environments(application_name=self.app_name, environment_names=[env_name],
                                                  include_deleted=False)
        return response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments'][0]

    def rebuild_environment(self, env_name):
        """
        Rebuilds an environment
        """
        out("Rebuilding " + str(env_name))
        self.ebs.rebuild_environment(environment_name=env_name)

    def get_environments(self):
        """
        Returns the environments
        """
        response = self.ebs.describe_environments(application_name=self.app_name, include_deleted=False)
        return response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']

    def delete_environment(self, environment_name):
        """
        Deletes an environment
        """
        self.ebs.terminate_environment(environment_name=environment_name, terminate_resources=True)

    def update_environment(self, environment_name, description=None, option_settings=[], tier_type=None, tier_name=None,
                           tier_version='1.0'):
        """
        Updates an application version
        """
        out("Updating environment: " + str(environment_name))
        messages = self.ebs.validate_configuration_settings(self.app_name, option_settings,
                                                            environment_name=environment_name)
        messages = messages['ValidateConfigurationSettingsResponse']['ValidateConfigurationSettingsResult']['Messages']
        ok = True
        for message in messages:
            if message['Severity'] == 'error':
                ok = False
            out("[" + message['Severity'] + "] " + str(environment_name) + " - '" \
                + message['Namespace'] + ":" + message['OptionName'] + "': " + message['Message'])
        self.ebs.update_environment(
            environment_name=environment_name,
            description=description,
            option_settings=option_settings,
            tier_type=tier_type,
            tier_name=tier_name,
            tier_version=tier_version)

    def get_previous_environment_for_subdomain(self, env_subdomain):
        """
        Returns an environment name for the given cname
        """

        def sanitize_subdomain(subdomain):
            return subdomain.lower()

        env_subdomain = sanitize_subdomain(env_subdomain)

        def match_cname(cname):
            subdomain = sanitize_subdomain(cname.split(".")[0])
            return subdomain == env_subdomain

        def match_candidate(env):
            return env['Status'] != 'Terminated' \
                    and env.get('CNAME') \
                    and match_cname(env['CNAME'])

        envs = self.get_environments()
        candidates = [env for env in envs if match_candidate(env)]

        match = None
        if candidates:
            match = candidates[0]["EnvironmentName"]

        return match

    def deploy_version(self, environment_name, version_label):
        """
        Deploys a version to an environment
        """
        out("Deploying " + str(version_label) + " to " + str(environment_name))
        self.ebs.update_environment(environment_name=environment_name, version_label=version_label)

    def get_versions(self):
        """
        Returns the versions available
        """
        response = self.ebs.describe_application_versions(application_name=self.app_name)
        return response['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult']['ApplicationVersions']

    def create_application_version(self, version_label, key):
        """
        Creates an application version
        """
        out("Creating application version " + str(version_label) + " for " + str(key))
        self.ebs.create_application_version(self.app_name, version_label,
                                            s3_bucket=self.aws.bucket, s3_key=self.aws.bucket_path+key)

    def delete_unused_versions(self, versions_to_keep=10):
        """
        Deletes unused versions
        """

        # get versions in use
        environments = self.ebs.describe_environments(application_name=self.app_name, include_deleted=False)
        environments = environments['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
        versions_in_use = []
        for env in environments:
            versions_in_use.append(env['VersionLabel'])

        # get all versions
        versions = self.ebs.describe_application_versions(application_name=self.app_name)
        versions = versions['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult'][
            'ApplicationVersions']
        versions = sorted(versions, reverse=True, cmp=lambda x, y: cmp(x['DateCreated'], y['DateCreated']))

        # delete versions in use
        for version in versions[versions_to_keep:]:
            if version['VersionLabel'] in versions_in_use:
                out("Not deleting " + version["VersionLabel"] + " because it is in use")
            else:
                out("Deleting unused version: " + version["VersionLabel"])
                self.ebs.delete_application_version(application_name=self.app_name,
                                                    version_label=version['VersionLabel'])
                sleep(2)

    def describe_events(self, environment_name, next_token=None, start_time=None):
        """
        Describes events from the given environment
        """
        events = self.ebs.describe_events(
            application_name=self.app_name,
            environment_name=environment_name,
            next_token=next_token,
            start_time=start_time)

        return (events['DescribeEventsResponse']['DescribeEventsResult']['Events'], events['DescribeEventsResponse']['DescribeEventsResult']['NextToken'])

    def wait_for_environments(self, environment_names, health=None, status=None, version_label=None,
                              include_deleted=True, use_events=True):
        """
        Waits for an environment to have the given version_label
        and to be in the green state
        """

        # turn into a list
        if not isinstance(environment_names, (list, tuple)):
            environment_names = [environment_names]
        environment_names = environment_names[:]

        # print some stuff
        s = "Waiting for environment(s) " + (", ".join(environment_names)) + " to"
        if health is not None:
            s += " have health " + health
        else:
            s += " have any health"
        if version_label is not None:
            s += " and have version " + version_label
        if status is not None:
            s += " and have status " + status
        out(s)

        started = time()
        seen_events = list()

        for env_name in environment_names:
            (events, next_token) = self.describe_events(env_name, start_time=datetime.now().isoformat())
            for event in events:
                seen_events.append(event)

        delay = 10

        while True:
            # bail if they're all good
            if len(environment_names) == 0:
                break

            # wait
            sleep(delay)

            # # get the env
            try:
                environments = self.ebs.describe_environments(
                    application_name=self.app_name,
                    environment_names=environment_names,
                    include_deleted=include_deleted)
            except BotoServerError as e:
                if not e.error_code == 'Throttling':
                    raise
                delay = min(60, int(delay * 1.5))
                out("Throttling: setting delay to " + str(delay) + " seconds")
                continue

            environments = environments['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
            if len(environments) <= 0:
                raise Exception("Couldn't find any environments")

            # loop through and wait
            for env in environments[:]:
                env_name = env['EnvironmentName']

                # the message
                msg = "Environment " + env_name + " is " + str(env['Health'])
                if version_label is not None:
                    msg = msg + " and has version " + str(env['VersionLabel'])
                if status is not None:
                    msg = msg + " and has status " + str(env['Status'])

                # what we're doing
                good_to_go = True
                if health is not None:
                    good_to_go = good_to_go and str(env['Health']) == health
                if status is not None:
                    good_to_go = good_to_go and str(env['Status']) == status
                if version_label is not None:
                    good_to_go = good_to_go and str(env['VersionLabel']) == version_label

                # allow a certain number of Red samples before failing
                if env['Status'] == 'Ready' and env['Health'] == 'Red':
                    if 'RedCount' not in env:
                        env['RedCount'] = 0

                    env['RedCount'] += 1
                    if env['RedCount'] > MAX_RED_SAMPLES:
                        out('Deploy failed')
                        raise Exception('Ready and red')

                # log it
                if good_to_go:
                    out(msg + " ... done")
                    environment_names.remove(env_name)
                else:
                    out(msg + " ... waiting")

                # log events
                try:
                    (events, next_token) = self.describe_events(env_name, start_time=datetime.now().isoformat())
                except BotoServerError as e:
                    if not e.error_code == 'Throttling':
                        raise
                    delay = min(60, int(delay * 1.5))
                    out("Throttling: setting delay to " + str(delay) + " seconds")
                    break

                for event in events:
                    if event not in seen_events:
                        out("["+event['Severity']+"] "+event['Message'])
                        seen_events.append(event)

            # check the time
            elapsed = time() - started
            if elapsed > self.wait_time_secs:
                message = "Wait time for environment(s) {environments} to be {health} expired".format(
                    environments=" and ".join(environment_names), health=(health or "Green")
                )
                raise Exception(message)
