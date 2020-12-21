import os
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
    print(' ./wipe_data_knime_repository.py [JSON configuration file]')
    sys.exit()
# Parses configuration file
try:
    settings = json.loads(open(sys.argv[1]).read())
except Exception as ex:
    print('ERROR: Parsing configuration file: {}'.format(ex))
    sys.exit()

# Check script runs with root
if getpass.getuser() != settings['repository_owner']:
    print('ERROR: Run this script with {}'.format(settings['repository_owner']))
    sys.exit()
    
# Loads logging
logger = logging.getLogger("wipe_data_knime_repository")
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
    
keep_files = settings["keep_files"]
exceptions = settings["exceptions"]
for exception in exceptions:
    if not os.path.isabs(exception) or not os.path.exists(exception):
        logger.error('Exceptions must be existing absolute paths')
        sys.exit()
        
just_log = settings['just_log']
if not isinstance(just_log, bool):
    logger.error('just_log must be boolean')
    sys.exit()
    
delete_days = settings['delete_days']
if not isinstance(delete_days, int):
    logger.error('delete_days must be int')
    sys.exit()
    
now = datetime.now()

def wipe_folder(folder):
    logger.debug('Checking folder {}'.format(folder))
    elements = os.listdir(folder)
    for element in elements:
        elementAbsPath = os.path.abspath(os.path.join(folder, element))
        if elementAbsPath in exceptions:
            logger.debug('Ignoring {}'.format(elementAbsPath))
        else:
            if os.path.isfile(elementAbsPath):
                if element not in keep_files:
                    fname = pathlib.Path(elementAbsPath)
                    mtime = datetime.fromtimestamp(fname.stat().st_mtime)
                    tdiff=now-mtime
                    if tdiff.days > delete_days:
                        logger.info("Deleting {} (now-mtime={}days)".format(elementAbsPath,tdiff.days))
                        if not just_log:
                            os.remove(elementAbsPath)
                else:
                    logger.debug("Keeping {}".format(elementAbsPath))
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
