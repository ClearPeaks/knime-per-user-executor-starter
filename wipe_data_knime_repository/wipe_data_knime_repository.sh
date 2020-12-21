#!/bin/bash
# command to set virtualenv or conda env
python /path/to/wipe_data_knime_repository.py /path/to/wipe_data_knime_repository.config
# Add in crontab (crontab -e) the following
# 30 4 10 * * /path/to/wipe_data_knime_repository.sh
# remember to give proper permission -> chmod u+x wipe_data_knime_repository.sh
