#!/bin/bash
# First, we need to activate (with conda or virtualenv) the Python 3 environment that contains pika and psutil (the only requirement to run the code)
# Example:
# source /path/to/python3-venv-with-pika-and-psutil/bin/activate

# Second, we just call the python script giving as argument the configuration file
# IMPORTANT: use absolute paths if you plan to add the knime-executor-per-user.service
# Example:
# python /path/to/knime_executor_per_user_starter.py /path/to/knime_executor_per_user_starter.config
