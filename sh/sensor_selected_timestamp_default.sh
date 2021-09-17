#!/bin/bash

cd `dirname $0`
python3 ../sensor_selected_timestamp.py \
    -s ../setting/setting_sensor_default.toml
