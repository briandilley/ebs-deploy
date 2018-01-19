from setuptools import setup

setup(

    # general meta
    name='ebs-deploy',
    version='2.0.0',
    author='Brian C. Dilley (Python 3 fixes by Erik Wallentinsen)',
    author_email='brian.dilley@gmail.com',
    description='Python based command line tools for managing '
                'Amazon Elastic Beanstalk applications. Python 3 '
                'version by Erik Wallentinsen',
    platforms='any',
    url='https://github.com/erikwt/briandilley/ebs-deploy',
    download_url='https://github.com/erikwt/ebs-deploy',

    # packages
    packages=[
        'ebs_deploy',
        'ebs_deploy.commands'
    ],

    # dependencies
    install_requires=[
        'boto>=2.45.0',
        'pyyaml>=3.10'
    ],
    # additional files to include
    include_package_data=True,

    # the scripts
    scripts=['scripts/ebs-deploy'],

    # wut?
    classifiers=['Intended Audience :: Developers']
)
