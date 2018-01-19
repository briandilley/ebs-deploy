# ebs-deploy
ebs-deploy is a command line tool for managing application deployments on Amazon's [Beanstalk].  Deployment of applications to any of [Beanstalk]'s available solution stacks is achievable with ebs-deploy.

## Installation
Installation is possible with pip and easy_install and can be done system wide or in a virtual environment.

with pip:

    > easy_install pip # if you don't already have pip installed
    > pip install ebs-deploy

with easy_install:

    > easy_install ebs-deploy


## Usage
Usage of ebs-deploy uses the following pattern:

    > ebs-deploy command options

Running ebs-deploy without arguments will list the available commands:

    > ebs-deploy 
    usage: ebs-deploy command [options | help]
    Where command is one of:
        delete_application
        delete_environment
        deploy
        describe_events
        dump
        help
        init
        list_environments
        list_solution_stacks
        list_versions
        rebuild
        swap_urls
        update
        update_environments
        wait_for_environment
        zdt_deploy


Every command requires a configuration file named `ebs.config` to be present in the directory in which the command is run or by passing the `-c` or `--config-file` argument.  Documentation on the format of the configuration file can be found later in this document.  To get help on any of the commands simply run:

    > ebs-deploy command --help

## Examples
The following examples omit the `--config-file` argument for brevity.  If you're configuration file is not named `ebs.config` and\or does not exist in the working directory of the ebs-deploy program you will need to add the `-c` or `--config-file` argument.

### Initialize your application
After creating your application's configuration file you will first need to create your application and it's environments.  To do this you use the `init` command:

    > ebs-deploy init

This will create the application and it's environments.  This command can be run at any time, even if the application already exists.  For instance, if you want to add a new environment to your application simply add it to your configuration file and run this command; the new environment will be created and the existing ones left alone.  Also, if you want to remove an environment you simply remove it from your configuration file and run the command; the environment will be terminated.

### Deploy your application
Once your application and it's environments have been created you are ready to deploy an application to an environment.  To do this use the deploy command:

    > ebs-deploy deploy --environment MyCo-MyApp-Prod
   
This will create an application archive (or use one passed in via the `--archive` argument) and deploy it to the given environment.

### Update an environment(s)
You may decide that you need to update your environment configuration in some way (change auto-scaling parameters, add a file, run a container command, etc).  This can be achieved by modifying your configuration file and running the update_environments command:

    > ebs-deploy update_environments --environment MyCo-MyApp-Prod

### Rebuild an environment
Sometimes things aren't working as expected in your Beanstalk environment and you just want to start from scratch.  This can be done by running the rebuild command:

    > ebs-deploy rebuild --environment MyCo-MyApp-Prod

The environment will then be completely rebuilt (load balancers, instances and all)

### Deploy an existing version
If you need to re-deploy a previously deployed version this can be achieved by using the update command.

    > ebs-deploy update --environment --version-label my-app-version-1

This will re-deploy the version `my-app-version-1` to the environment.  The version label supplied must be a previously deployed version and must not have been deleted from the application.  The update command also applies the same configuration updates that the update_environments command does.

### Zero downtime deployment
For an actively used application or an application where any amount of downtime is unacceptable the zero downtime deployment option can be used:

    > ebs-deploy zdt_deploy --environment MyCo-MyApp-Prod

Zero downtime deployment takes a while because it creates an entirely new environment, deploys the new application version to it, swaps the cnames with the currently running environment and then terminates the old environment.

Zero downtime deployments are only available for WebServer tier types, they cannot work for Worker tier types since worker tier types do not have cnames.

### Swap URLS
If you need to do zero-downtime deployment, but want to run tests before switching to the new environment, you can deploy to a new environment, run your tests, then swap URLs in a separate step:

    > ebs-deploy swap_urls --old-environment MyCo-MyApp-0 --new-environment MyCo-MyApp-1

This is a relatively fast operation since both environments have already been deployed.

### Delete the application
When your application is ready to be decommissioned you can use the delete_application command:

    > ebs-deploy delete_application

The application and all of it's environments will be deleted.

# Environment variables
The following environment variables affect ebs-deploy configuration but can be overriden on a per project basis in the configuration file:

- **AWS_ACCESS_KEY_ID** - the aws access key id
- **AWS_SECRET_ACCESS_KEY** - the secret access key
- **AWS_DEFAULT_REGION** - the region
- **AWS_BEANSTALK_BUCKET_NAME** - the bucket that beanstalk apps will be stored in
- **AWS_BEANSTALK_BUCKET_NAME_PATH** - the path in the bucket where beanstalk apps will be stored

# Configuration File Format
Before you can begin using ebs-deploy you need to create a configration file for your application.  A list of available namespaces and `option_settings` for Elastic Beanstalk can be found [here](http://docs.aws.amazon.com/elasticbeanstalk/latest/dg/command-options.html).  

### Keys and other secret information

Keys and other secret information that should not be checked into source control can be added to the configuration file via environment variables. Strings with the format of `${VARIABLE}` will be replaced with the contents of `VARIABLE`. This is helpful for AWS access keys and passwords.

### Structure

Configuration files are written in YAML and have the following structure:

```yaml

# aws account config
aws:
    # override environment variables here
    access_key: '...'
    secret_key: '...'
    region: 'us-west-1'
    bucket: 'my-company-ebs-archives'
    bucket_path: 'my-app'

# application configuration
app:
    versions_to_keep: 10 # the number of unused application versions to keep around
    app_name: 'My awesome app' # the name of your application
    description: 'An application that is awesome' # description of your app

    # configuration that applies to all environments, environment
    # specific configuration is merged with this configuration allowing
    # for default values that can be overriden (or added to) on
    # an environment specific basis.  Any of the values\nodes below
    # can also be specified in the environment specific configuration
    # below
    all_environments:
        solution_stack_name: '64bit Amazon Linux running Python'

        # optional information on the tier type
        # check the boto documentation for create_environment
        # for an explanation on the default values.  Most
        # configurations don't need to specify these values
        # at all.
        # Boto: http://docs.pythonboto.org/en/latest/ref/beanstalk.html
        tier_name: 'WebServer'
        tier_type: 'Standard'
        tier_version: '1.0'

        # option_settings contain namespaced key\value pairs that are
        # supported by Beanstalk, follows is an example of some of
        # the values that you might want to set for a python application
        option_settings:

            'aws:autoscaling:launchconfiguration':
                Ec2KeyName: 'mycompany-ssh-key-name'
                InstanceType: 't1.micro'
                SecurityGroups: 'mycompany-prod'

            'aws:elasticbeanstalk:container:python':
                WSGIPath: 'runsite.py'
                NumProcesses: 1
                NumThreads: 15

            'aws:autoscaling:asg':
                MinSize: 1
                MaxSize: 5

            'aws:elasticbeanstalk:container:python:staticfiles':
                "/static/": "my_app/static/"

            'aws:elb:loadbalancer':
                SSLCertificateId: 'arn:aws:iam::XXXXXXX:server-certificate/my-company'
                LoadBalancerHTTPSPort: 443

            'aws:elb:policies':
                Stickiness Policy: true

            'aws:elasticbeanstalk:sns:topics':
                Notification Endpoint: 'ops@mycompany.com'

            'aws:elasticbeanstalk:application':
                Application Healthcheck URL: '/'

            'aws:elasticbeanstalk:application:environment':
                AWS_ACCESS_KEY_ID: '${MY_AWS_ACCESS_KEY_ID}'
                AWS_SECRET_KEY: '${MY_AWS_SECRET_KEY}'

        # instructions on how to build the application archive
        archive:

            # Generate an application archive ...        
            generate:
                cmd: #... command here to generate an archive file ...
                output_file: .*target/.*\.war # a regex pattern for finding the
                                              # file generated above
        
            # ... or build one from the current directory
            includes: # files to include, a list of regex
            excludes: # files to exclude, a list of regex
                - '^.gitignore$'
                - '^\.git*'
                - '.*\.egg-info$'
                - '^tests.*'
                - '.*\.zip$'
                - '^venv.*'

            # a list of files to add to the archive, follows are
            # the two ways to dynamically add files to the archive:
            # contet, and yaml
            files:
            
                # here's an example of adding a "content" file to
                # the archive at the root of the archive called
                # "deflate.conf" that configures apache to serve
                # things using mod_deflate (gzip).
                - deflate.conf:
                    # permissions of the file
                    permissions: 0644
                    # the content node is important here
                    content: |
                        <Location />
                            # Insert filter
                            SetOutputFilter DEFLATE
                            # Don't compress images
                             SetEnvIfNoCase Request_URI \.(?:gif|jpe?g|png)$ no-gzip dont-vary
                            # Make sure proxies don't deliver the wrong content
                            Header append Vary User-Agent env=!dont-vary
                        </Location>

                # here's an example of adding a "yaml" file to
                # the archive in the .ebextensions sub directory
                # named "02-packages.config".  The yaml nodes that
                # follow the "yaml" node under this will be added
                # to the file
                - .ebextensions/02-packages.config:
                    # permissions of the file
                    permissions: 0777
                    # the yaml node is important here
                    yaml:
                        packages:
                            yum:
                                rubygems: ''
                                pcre-devel: ''
                                memcached-devel: ''
                            rubygems:
                                sass: ''

                # another example of adding a yaml file to the archive
                # this one tells beanstalk to run some commands on deployment
                - .ebextensions/03-commands.config:
                    # permissions of the file
                    permissions: 0666
                    yaml:
                        commands:
                            00010-timezone:
                                command: "ln -sf /usr/share/zoneinfo/America/Los_Angeles /etc/localtime"
                        container_commands:
                            00020-deflate:
                                command: "cp deflate.conf /etc/httpd/conf.d/"
                            00030-migrations:
                                command: "... some db migration command here ..."

    # Under the environments node is each environment and their config.
    # Environment specific configuration is determined by first processing
    # the all_environments config and then "overlaying" the environment
    # specific configuration onto it.  Any number of environments can be
    # specified
    environments:

        # the production version of the app
        'MyCo-MyApp-Prod': 
            cname_prefix: 'myco-myapp-prod'
            option_settings:
                'aws:elasticbeanstalk:application:environment':
                    MYAPP_ENV_NAME: 'prod'
                'aws:autoscaling:launchconfiguration':
                    InstanceType: 'm1.medium'

        # the QA version of the app
        'MyCo-MyApp-QA': 
            cname_prefix: 'myco-myapp-qa'
            option_settings:
                'aws:elasticbeanstalk:application:environment':
                    MYAPP_ENV_NAME: 'qa'

```

Here's an example of how you might use ebs-deploy to deploy a Scalatra app to beanstalk:

```yaml
aws:
    access_key: '...'
    secret_key: '...'
    region: 'us-west-1'
    bucket: 'mycomppany-apps-us-west-1'
    bucket_path: 'Scalatra-App'

app:
    versions_to_keep: 10
    app_name: 'Scalatra-App'
    description: 'My Scalatra Application'

    all_environments:
        solution_stack_name: '64bit Amazon Linux running Tomcat 7'

        option_settings:

            'aws:autoscaling:launchconfiguration':
                Ec2KeyName: 'mycompany'
                InstanceType: 'm1.small'
                SecurityGroups: 'mycompany-web'

            'aws:autoscaling:asg':
                MinSize: 1
                MaxSize: 10

            'aws:elasticbeanstalk:application':
                Application Healthcheck URL: '/'

        # instructions on how to build the application archive
        archive:
            generate:
                cmd: sbt package
                output_file: .*target/.*\.war

    environments:

        # the Testing version of the app
        'Scalatra-App-Testing':
            cname_prefix: 'scalatra-app-testing'

        # the production version of the app
        'Scalatra-App-Prod':
            cname_prefix: 'scalatra-app-prod'

```

## Pyhon 3
Thanks Erik Wallentinsen for the Python 3 fixes

## License
-
MIT

  [Beanstalk]: http://aws.amazon.com/elasticbeanstalk/
  

    
