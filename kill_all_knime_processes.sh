#!/bin/bash
kill -9 $(ps aux | grep knime | awk '{print $2}')
