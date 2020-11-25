"""
Python Script for starting KNIME Executor processes for each user when a job is added into RabbitMQ. The started KNIME Executor process will run with the same OS user as the user that submitted the job

author: oscar.martinez@clearpeaks.com
"""

import pika
import psutil
import os
import pwd
import subprocess
import time
import ssl
import logging
import json
import sys
import getpass
import random
from logging.handlers import TimedRotatingFileHandler

# Check script runs with root
if getpass.getuser() != 'root':
    print('ERROR: Run this script with root')
    sys.exit()

# Checks configuration file is provided
if len(sys.argv) != 2:
    print('ERROR: Provide configuration file. Usage:')
    print('    ./knime_executor_per_user_starter.py [JSON configuration file]')
    sys.exit()

# Parses configuration file
try:
    settings = json.loads(open(sys.argv[1]).read())
except Exception as ex:
    print('ERROR: Parsing configuration file: {}'.format(ex))
    sys.exit() 

# Loads logging
logger = logging.getLogger("knime_executor_per_user_starter")
logger.setLevel(getattr(logging, settings['log_level'].upper()))
handler = TimedRotatingFileHandler(settings['log_file'], when=settings['log_rotation_when'], interval=settings['log_rotation_interval'], backupCount=settings['log_rotation_keep'])
formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Checks KNIME home exists and contains knime executable
knime_process_name = "knime"
if not os.path.exists(settings['knime_home']):
    logger.error('KNIME home ({}) does not exist'.format(settings['knime_home']))
    sys.exit()
if not knime_process_name in os.listdir(settings['knime_home']):
    logger.error('KNIME executable not found in KNIME home ({})'.format(settings['knime_home']))
    sys.exit()
knime_start_to_format = os.path.join(settings['knime_home'], knime_process_name) + " -nosplash -consolelog -data {} -application com.knime.enterprise.slave.KNIME_REMOTE_APPLICATION"

# Checks folder to contain workspaces exists
if not os.path.exists(settings['knime_workspace_parent_folder']):
    logger.error('KNIME workspace parent folder ({}) does not exist'.format(settings['knime_workspace_parent_folder']))
    sys.exit()
knime_workspace_to_format = settings['knime_workspace_parent_folder'] + "/{}"

# This script requires KNIME is syncing users from LDAP and it also requires that LDAP users also exist at OS level in the machines in which the Executors VMs will run. This can be achieved for example with SSSD
# For LDAP users, they exist both in the KNIME user base (since KNIME is syncing users from LDAP) and also as OS users in the KNIME Executor VMs
# However, if KNIME is configured to also support local userbase in addition to LDAP users, it may happen that non-LDAP users may not have equivalent OS users
# In this case we support mapping KNIME local users to OS users on the Executor VMs (which may or may not be LDAP users)
local_knime_user_os_user_mapping = settings['local_knime_user_os_user_mapping']

# Get setting that controls number of attempts to start a executor for each user
max_attempts_executor_start = settings['max_attempts_executor_start']
attempts_executor_start = {}

all_rabbitmq_hosts = settings['rabbitmq_host_name']
if isinstance(settings['rabbitmq_host_name'], str):
    all_rabbitmq_hosts = [settings['rabbitmq_host_name'], ]
elif not isinstance(settings['rabbitmq_host_name'], list):
    print('ERROR: Parsing configuration file: rabbitmq_host_name must be a str or a list')
    sys.exit() 

logger.info('Starting KNIME Executor Per-User Starter with the following settings')
for setting in settings:
    if not 'password' in setting:
        logger.info('{}:{}'.format(setting, settings[setting]))

# Finds a running KNIME process for a given user
def find_process(user):
    for proc in psutil.process_iter():
        if proc.name() == knime_process_name and proc.username() == user:
            return True
    return False
    # Equivalent code if psutil NA
    # pprocess = subprocess.run('ps axo user:60,comm | grep ' + knime_process_name + ' | grep ' + user, stdout=subprocess.PIPE, shell=True)
    # lines = pprocess.stdout.decode('utf-8').split('\n')
    # for line in lines:
        # fields = line.split()
        # if len(fields) == 2 and fields[0] == user and fields[1] == knime_process_name:
            # return True
    # return False

# Starts a new KNIME executor for a given user listening to a queue
def start_process(knime_user_name, os_user_name):
    pw_record = pwd.getpwnam(os_user_name)
    user_name      = pw_record.pw_name
    user_home_dir  = pw_record.pw_dir
    user_uid       = pw_record.pw_uid
    user_gid       = pw_record.pw_gid
    
    if not os.path.exists(user_home_dir):
        # KNIME (eclipse actually) will write some metadata in home folder, so we need the home folder to exist, if the user has never logged into the machine the log folder will not exist, so we need to create it
        logger.info('Home directory for user {} did not exist. Creating and setting proper ownership'.format(os_user_name))
        os.system('mkdir {}'.format(user_home_dir))
        os.system('chown -R {}:root {}'.format(os_user_name, user_home_dir))
    
    env = os.environ.copy()
    env['HOME']  = user_home_dir
    env['LOGNAME']  = user_name
    env['PWD']  = settings['knime_home']
    env['USER']  = user_name
    knime_executor_msgq = "{}://{}:{}@{}/{}".format(settings["rabbitmq_protocol"], settings['rabbitmq_client_user'], settings['rabbitmq_client_password'], all_rabbitmq_hosts[0], settings['rabbitmq_virtual_host'])
    for i in range(1,len(all_rabbitmq_hosts)):
        knime_executor_msgq = knime_executor_msgq + ',{}://{}:{}'.format(settings["rabbitmq_protocol"], all_rabbitmq_hosts[i], settings['rabbitmq_port'])
    env['KNIME_EXECUTOR_MSGQ'] = knime_executor_msgq
    # TODO - add quotes '{}' - in version 4.11.3 -> replace (user = {}) by (user = '{}')
    env['KNIME_EXECUTOR_RESERVATION'] = "(user = {})".format(knime_user_name)
    process = subprocess.Popen(
        knime_start_to_format.format(knime_workspace_to_format.format(os_user_name)), preexec_fn=demote(user_uid, user_gid), cwd=settings['knime_home'], env=env, shell=True
    )
   
    logger.info('Process started for user {}. PID is: {}'.format(os_user_name, process.pid))

# Sets up a new process to run as a given user
def demote(user_uid, user_gid):
    def result():
        os.setgid(user_gid)
        os.setuid(user_uid)
    return result

def on_message(channel, method_frame, header_frame, body):
    logger.debug(method_frame.delivery_tag)
    logger.debug(header_frame)
    logger.debug(body)
    
    knime_user_name = None
    try:
        knime_user_name = json.loads(body.decode('utf-8'))['user'].lower()
    except Exception as ex:
        logger.error('Returning message to queue. Could not extract user name. Unexpected error: {}'.format(ex))
        channel.basic_nack(delivery_tag=method_frame.delivery_tag)
        return
    
    republish = True
    os_user_name = None
    if knime_user_name in local_knime_user_os_user_mapping:
        os_user_name = local_knime_user_os_user_mapping[knime_user_name]
        logger.info('New message/job {} from user {}: this local KNIME user is mapped to OS user {}'.format(method_frame.delivery_tag, knime_user_name, os_user_name))
    else:
        os_user_name = knime_user_name
        logger.info("New message/job {} from user {}".format(method_frame.delivery_tag, knime_user_name))
    
    if find_process(os_user_name):
        logger.info('There is already a KNIME executor running for user {}'.format(os_user_name))
        seconds_sleep = settings['seconds_sleep_executor_existing']
    else:
        logger.info('Starting KNIME Executor process for user {}'.format(os_user_name))
        try:
            start_process(knime_user_name, os_user_name)
        except Exception as ex:
            logger.error('Returning message to queue. Could not start KNIME Executor process. Unexpected error: {}'.format(ex))
            channel.basic_nack(delivery_tag=method_frame.delivery_tag)
            return
        seconds_sleep = settings['seconds_sleep_executor_start']
        
        if os_user_name not in attempts_executor_start:
            attempts_executor_start[os_user_name] = 0
        elif attempts_executor_start[os_user_name] == max_attempts_executor_start:
            # do not publish - since for some reason the executor is not really starting; and we want to avoid infinite loops
            republish = False
            # we though reset counter in case, user wants to try a bit later (after probably contacting admin to check what is happening)
            attempts_executor_start[os_user_name] = 0
        else:
            attempts_executor_start[os_user_name] = attempts_executor_start[os_user_name] + 1
        
    if republish:
        logger.info('Sending ACK for message {} and sleeping for {} seconds before re-publishing message with canHandle=True'.format(method_frame.delivery_tag, seconds_sleep))
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)
        time.sleep(seconds_sleep)
        header_frame.headers['canHandle']=True
        if settings['rabbitmq_exchange'] == '':
            channel.basic_publish(settings['rabbitmq_exchange'], settings['rabbitmq_queue_name'], body, header_frame, mandatory=True)
        else:
            channel.basic_publish(settings['rabbitmq_exchange'], settings['rabbitmq_routing_key'], body, header_frame, mandatory=True)
    else:
        logger.warn('Sending ACK for message {} but NOT re-publishing message due to max_attempts reached (KNIME Executor starting is failing) - message discarded'.format(method_frame.delivery_tag, seconds_sleep))
        channel.basic_ack(delivery_tag=method_frame.delivery_tag)

#Loop to attempt connection recovery, also to support RabbitMQ in HA
while(True):
    try:
        logger.info('Connecting to RabbitMQ...')
        random.shuffle(all_rabbitmq_hosts)
        context = ssl.create_default_context(cafile=settings['ca_cert_file'])
        ssl_options = None
        if settings['rabbitmq_protocol'] == 'amqps':
            ssl_options = pika.SSLOptions(context, settings['rabbitmq_host_name'])
        credentials = pika.PlainCredentials(settings['rabbitmq_client_user'], settings['rabbitmq_client_password'])
        parameters = pika.ConnectionParameters(host=all_rabbitmq_hosts[0],
                                        port=settings['rabbitmq_port'],
                                        ssl_options=ssl_options,
                                        virtual_host=settings['rabbitmq_virtual_host'],
                                        credentials=credentials)

        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()
        if settings['rabbitmq_exchange'] != '':
            channel.exchange_declare(settings['rabbitmq_exchange'])
        channel.basic_consume(settings['rabbitmq_queue_name'], on_message)

        try:
            channel.start_consuming()
        except KeyboardInterrupt:
            channel.stop_consuming()
            connection.close()      
            break
    # Recover from server-initiated connection closure
    except pika.exceptions.ConnectionClosedByBroker:
        continue
    # Do not recover on channel errors
    except pika.exceptions.AMQPChannelError as err:
        logger.error("Caught a channel error: {}, stopping...".format(err))
        break
    except pika.exceptions.AMQPConnectionError:
        logger.error('Connection was closed, retryng...')
        continue
