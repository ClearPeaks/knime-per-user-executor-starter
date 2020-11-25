# knime-per-user-executor-starter
This repository contains a Python script (and auxiliary files) to allow KNIME to start Executor processes for each user that submit jobs. An started KNIME Executor processes runs with the same OS user as the one who submitted the job.

## Overview

When KNIME is running with distributed Executors, i.e. KNIME Executors are running in hardware (physical or virtual) different than KNIME Server (https://docs.knime.com/latest/server_admin_guide/index.html#knime-server-distributed-executors), normally one would use a service account (or just the "knime" user) to run the Executor processes on the VMs running KNIME Executors. That may be the same service account (of "knime" user) that was used to do the KNIME Server installation or it may be a dedicated service account only used to run the Executors (example "knimeexe").

However, there may be situations in which we need to run per-user Executors. In this scenario, when a user submits a job, that job will be executed in a KNIME Executor that is running with the same OS user as the user that submitted the job, and not with a service account. Situations where this may be helpful are:
- You need to access data sources for which there are not KNIME nodes that enable the access, but for which there is an OS method to do it. An example is to access network drives such as Samba or NFS with Kerberos. Currently KNIME does not have connectors for them, though it is possible to access Samba 3 without Kerberos using the nodes in the Erlwood extension (https://hub.knime.com/erlwood_cheminf/extensions/org.erlwood.features.core.base/latest). Therefore, a way to provide access is to mount the network drives at OS level and then have the per-user Executor access them. In this manner it is possible to use the user-based authorization rules that may have been setup for the network drives.
- You need direct auditing capabilites and need to easily know which user did what. When Executors run with a service account, in order to find out which user did what, one needs to cross-match the jobId on the Executor log (knime.log) with the information on the server logs. When Executors run per-user, each user has its own log file so there is not need to check the server logs to find out who did what.

## Procedure

When a user submits a job via KNIME Web Portal or via KNIME Analytics Platform (AP), a Python script running on the machine (virtual or physical) in which the KNIME Executors will run will read the job (in KNIME enterprise environments jobs are communicated using RabbitMQ) and will start a KNIME Executor process using the same OS user as the user that submitted the job. In highly available (HA) environments there may be more than one machine running KNIME Executors. In this case, each machine would run the Python script and each machine would spawn a KNIME Executor for the user. This provides HA at KNIME Executor level, since each user would always have more than one KNIME Executor ready to get his/her jobs.

A plugin that is added in KNIME Executor installation (in the dropins folder) takes care to auto-terminate executors that have been unused for a while. 

## Users mapping
This solutions requires that KNIME Server users are synchronized with LDAP and that OS users in the Executor VMs are also synchronized with the same LDAP. The latter can be achieved for example using SSSD.

Note that because the Python script needs to start processes under different OS users it is required to run this solution using root.

Note that it may happen that a user that submits a job has never logged in into the KNIME Executor machines. A KNIME Executor process will write some Java and Eclipse preference files in the home folder of the user running the process. When the user has not logged in into the machine (which is actually what we want since we do not want users able to login into these machines), the home folder needs to be created prior to running the KNIME Executor with that user, otherwise the KNIME process will fail – this is taken care of by the Python script. The script creates the home folder if it does not exist.

## Requirements
In order to run this solution one needs:
- A KNIME enterprise deployment (with RabbitMQ and distributed executors). This solution has been tested to work with KNIME Executors version 4.2.2 and KNIME Server 4.11
- A Python 3 environment ready-to-use with pika and psutil on the Executor machines.
- Download this repository which includes knime_executor_per_user_starter.py to start KNIME Executors on-demand; the configuration file for the Python script (knime_executor_per_user_starter.config); a bash script template to execute the Python script (knime_executor_per_user_starter.sh); and a file (knime-executor-per-user.service) to add the Python script as a service so it starts automatically on-boot.
- A plugin (JAR file) to autoterminate idle Executors. The file is called com.knime.enterprise.executor.autoshutdown_[version].jar. Contact KNIME support to download this plugin.
- Prope licensing schema - note each KNIME Executor process will acquire core tokens from the KNIME Server, therefore you need to configure the Executors accordingly (via knime.ini) to avoid asking too many cores per process depending on the number of users you will have. Otherwise starting processes will fail since all tokens will be used.

## Installation steps
### Steps on KNIME Server
Perform the following on the KNIME Server.

When a user starts using KNIME (for first time or after a while of not using it) his/her first job will trigger the starting of a KNIME Executor process in each Executor machine. Starting this process takes 10-20 seconds. Therefore we need to increase the default timeout (1min) to 2min so that KNIME Server waits a bit more before deciding no Executor is available. For this, modify the following line in knime-server.config: 
```
com.knime.server.job.default_load_timeout=2m
```

Since the knime-server.config is stored in the workflow repository, there is no need to do this step multiple times if there are multiple KNIME Servers since these will be sharing the workflow repository.

Important: there is also the need to update another timeout configuration (when opening an existing job) that is set now to 10 seconds. In next release of KNIME it will be possible to modify this.

### Steps on KNIME Executors
Performs the following steps in all the machines that will run KNIME Executor:

#### With root:

1-	Copy knime_executor_per_user_starter.py, knime_executor_per_user_starter.config, knime_executor_per_user_starter.sh and knime-executor-per-user.service into the KNIME Executor installation folder

2-	Ensure the files are executable
```
cd /path/to/knime_X.X.X
chmod u+x knime_executor_per_user_starter.*
```

3-	Create the folder for the workspaces and give permissions so that any user can create a folder there.
```
cd /path/to/workspaces
chmod 777 ../workspaces
```

4-	Edit the knime_executor_per_user_starter.config accordingly. Default configuration sets rotation of the Python script log to one per day and keep them for 90 days. If RabbitMQ usses SSL encryption, specify the CA certificate is needed, change the port to 5671 and specify the protocol is amqps. You will also need to provide the credentials for RabbitMQ, and the installation (home) folder for the KNIME executor (which should contain the knime executable). It is also needed to specify the folder in which the KNIME workspaces will be created, one for each user. Finally, if there is some KNIME user that is not in LDAP but it is on the local KNIME user base, specify the mapping for that user to which LDAP user is going to be used.

5-	Ensure you have a valid Python 3 environment which contains the required Python module (pika and psutil)
```
# conda or virtualenv command to activate the environment
python -c "import pika"
python -c "import psutil"
```

6-	Create dropins folder in the KNIME Executor installation folder, put the autoterminate plugin in it, set ownership and permissions as for the knime executable:
```
cd /path/to/knime_X.X.X
mkdir dropins
cp /path/to/com.knime.enterprise.executor.autoshutdown_X.jar dropins
chown [installation owner]:users dropins/*
chmod --reference knime dropins/*
```

7-	Modify the knime.ini to configure the autoterminate plugin.
```
-Dcom.knime.executor.autoshutdown.delay_in_min=30
```
Since there will be one KNIME Executor process per user, you may also want to modify the -Dorg.knime.core.maxThreads property to meet the licensing deal. Remember 2 threads consume one 1 core token. If there are too many executors running that consume all tokens, new executors will fail to start. Similarly, you may want to edit the RAM that each KNIME Executor process with utilize with the -Xmx parameter.

#### With the user that owns the installation directory:

8-	Clean the installation of the executor:
```
cd /path/to/knime_X.X.X
./knime -clean -application org.knime.product.KNIME_BATCH_APPLICATION
```

#### With root: 

9-	Edit knime_executor_per_user_starter.sh accordingly. 

10-	Make the shell script executable
```
chmod u+x knime_executor_per_user_starter.sh
```

11-	Edit the knime-executor-per-user.service accordingly

12-	Enable the service
```
cp knime-executor-per-user.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable knime-executor-per-user.service
```

13-	You can start and stop the service with (leave it running)
```
systemctl start knime-executor-per-user.service
systemctl stop knime-executor-per-user.service
```

14-	In case of error check the possible errors messages with:
```
journalctl -b --unit=knime-executor-per-user.service
```

15-	If it was added before, disable the service to start the single KNIME Executor
```
systemctl disable knime-executor.service
```

16-	 Optionally you can try to reboot the VM and ensure the process has been started. To check that the process are running use:
```
ps aux | grep knime
```
You should see 2 lines, one for the shell script and the other for the python script. If there are executor running you can also see them here.
