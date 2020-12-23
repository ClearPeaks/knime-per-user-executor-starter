import os
import pwd
import logging
import json
import sys
import getpass
from logging.handlers import TimedRotatingFileHandler
from datetime import datetime
import pathlib
 
# Checks configuration file is provided
if len(sys.argv) != 2:
    print('ERROR: Provide configuration file. Usage:')
    print(' ./wipe_data_knime_users.py [JSON configuration file]')
    sys.exit()
 
# Parses configuration file
try:
    settings = json.loads(open(sys.argv[1]).read())
except Exception as ex:
    print('ERROR: Parsing configuration file: {}'.format(ex))
    sys.exit()
 
# Check script runs with root
if getpass.getuser() != 'root':
    print('ERROR: Run this script with root')
    sys.exit()
 
# Loads logging
logger = logging.getLogger("wipe_data_knime_users")
logger.setLevel(getattr(logging, settings['log_level'].upper()))
handler = TimedRotatingFileHandler(settings['log_file'], when=settings['log_rotation_when'], interval=settings['log_rotation_interval'], backupCount=settings['log_rotation_keep'])
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
 
pathsToWipe = settings['paths']
if isinstance(settings['paths'], str):
    pathsToWipe = [settings['paths'], ]
elif not isinstance(settings['paths'], list):
    print('ERROR: Parsing configuration file: paths must be a str or a list')
    sys.exit()
 
just_log = settings['just_log']
if not isinstance(just_log, bool):
    logger.error('just_log must be boolean')
    sys.exit()
 
delete_days = settings['delete_days']
if not isinstance(delete_days, int):
    logger.error('delete_days must be int')
    sys.exit()
 
exceptions_startwith = settings['exceptions_startwith']
if isinstance(settings['exceptions_startwith'], str):
    exceptions_startwith = [settings['exceptions_startwith'], ]
elif not isinstance(settings['exceptions_startwith'], list):
    print('ERROR: Parsing configuration file: exceptions_startwith must be a str or a list')
    sys.exit()
 
users = []
for user in os.listdir(settings["workspaces_dir"]):
    if not user.endswith('_temp'):
        users.append(user)
if len(users):
    logger.info('Users: {}'.format(users))
else:
    logger.error('no users found in {}'.format(settings["workspaces_dir"]))
    sys.exit()
 
now = datetime.now()
 
def wipe_folder(folder):
logger.debug('Checking folder {}'.format(folder))
elements = os.listdir(folder)
    for element in elements:
        elementAbsPath = os.path.abspath(os.path.join(folder, element))
        ignoreElement = False
        for exception_startwith in exceptions_startwith:
            if element.startswith(exception_startwith):
                ignoreElement = True
                logger.debug('Ignoring {}'.format(elementAbsPath))
         
        if not ignoreElement:
            if os.path.isfile(elementAbsPath):
                fname = pathlib.Path(elementAbsPath)
                fowner = pwd.getpwuid(os.stat(elementAbsPath).st_uid).pw_name
                mtime = datetime.fromtimestamp(fname.stat().st_mtime)
                tdiff=now-mtime
                if fowner in users and tdiff.days > delete_days:
                    logger.info("Deleting {} (now-mtime={}days)".format(elementAbsPath,tdiff.days))
                    if not just_log:
                        os.remove(elementAbsPath)
            elif os.path.isdir(elementAbsPath):
                wipe_folder(elementAbsPath)
         
for pathToWipe in pathsToWipe:
    if not os.path.exists(pathToWipe):
        logger.warn('{} does not exist. Ignoring folder.'.format(pathToWipe))
    elif os.path.isfile(pathToWipe):
        logger.warn('{} is a file. Ignoring file.'.format(pathToWipe))
    else:
        # It is a folder that exists
        wipe_folder(pathToWipe)