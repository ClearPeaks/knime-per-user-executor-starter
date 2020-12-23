#!/bin/bash
# command to set virtualenv or conda env
python /path/to/wipe_data_knime_users.py /path/to/wipe_data_knime_users.config
 
# Add in crontab (crontab -e) the following
# 30 4 10 * * /path/to/wipe_data_knime_users.sh