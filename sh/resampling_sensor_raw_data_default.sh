#!/bin/bash

cd `dirname $0`
python3 ../resampling_sensor_raw_data.py \
    -s ../setting/setting_sensor_default.toml
