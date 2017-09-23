from setuptools import setup

setup(

    # general meta
    name='ebs-deploy',
    version='1.9.21',
    author='Brian C. Dilley, MetaBrite',
    author_email='brian.dilley@gmail.com',
    description='Python based command line tools for managing '
                'Amazon Elastic Beanstalk applications.',
    platforms='any',
    url='https://github.com/briandilley/ebs-deploy',
    download_url='https://github.com/briandilley/ebs-deploy',

    # packages
    packages=[
        'ebs_deploy',
        'ebs_deploy.commands'
    ],

    # dependencies
    install_requires=[
        'boto>=2.32.0',
        'pyyaml>=3.10',
        'sh>=1.11',
    ],
    # additional files to include
    include_package_data=True,

    # the scripts
    entry_points={
        'console_scripts': [
            'ebs-deploy = ebs_deploy.main:main'
        ],
    },

    # wut?
    classifiers=['Intended Audience :: Developers']
)
