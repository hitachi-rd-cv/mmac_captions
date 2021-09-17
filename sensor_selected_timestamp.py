# coding: utf-8
"""
Select sensor data that the range of the timestamps are after video starting.

Note. Normal case is video start after sensor, exception case is sensor start
after video

Copyright (c) 2021 Hitachi,Ltd.

This software is released under the MIT License.
http://opensource.org/licenses/mit-license.php
"""
import argparse
from collections import OrderedDict
import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
import toml


IS_DEBUG = False


def select_data_main(
        sensor_files_mapping, video_head_timestamp_mapping, setting):
    """Select sensor data suitable timestamp range."""
    output_data_dir = setting['selected_timestamp']['output_data_dir']
    if not os.path.exists(output_data_dir):
        os.makedirs(output_data_dir)
    is_debug = IS_DEBUG
    keys = [key_ for key_ in sensor_files_mapping]
    keys.sort()
    input_data_dir = \
        setting['selected_timestamp']['input_sensor_data_dir']
    files_count = 0

    for i_key_, key_ in enumerate(keys):
        print(
            '%03d/%03d: %s' % (
                i_key_+1, len(keys), key_))
        input_path = \
            Path(input_data_dir).joinpath(
                sensor_files_mapping[key_]).as_posix()
        df_sensor_in = pd.read_csv(input_path, header=0)
        df_sensor_in['timestamp'] = df_sensor_in['timestamp'].map(
            pd.to_datetime)
        if np.array(df_sensor_in['timestamp']).shape[0] == 0:
            print('[INFO] Sensor timestamp of %s is empty.' % key_)
            print(' Maybe no caption data in it.')
            continue

        min_time_video = pd.to_datetime(video_head_timestamp_mapping[key_])
        min_time_sensor_in = pd.to_datetime(np.array(
            df_sensor_in['timestamp'])[0])
        max_time_sensor_in = pd.to_datetime(np.array(
            df_sensor_in['timestamp'])[-1])
        if min_time_video < min_time_sensor_in:
            msg = '[INFO] In %s; ' % key_
            msg += ' (min time video) < (min time sensor), \n'
            msg += ' (min time video) : %s\n' % min_time_video
            msg += ' (min time sensor): %s\n' % min_time_sensor_in
            msg += ' Adding zero padding to start with video head.'
            print(msg)
            # zero paddinig
            timestamp_diff = (min_time_sensor_in - min_time_video)
            time_sec = \
                timestamp_diff.seconds + \
                timestamp_diff.microseconds / 1000000.0
            fps = setting['general']['sampling_frequency']
            row_number = int(time_sec * fps)
            df_timestamps = pd.DataFrame(
                [min_time_sensor_in
                 - pd.Timedelta((row_number-i)*1.0/fps, unit='s')
                 for i in range(0, row_number)],
                columns={'timestamp': str})
            df_timestamps['timestamp'] = df_timestamps['timestamp'].map(
                pd.to_datetime)
            feature_size = len(df_sensor_in.columns)-1
            col_names = df_sensor_in.columns[1:]
            columns = OrderedDict(zip(col_names, [np.float32]*feature_size))
            df_zeros = pd.DataFrame(
                np.zeros((row_number, feature_size), dtype=np.float32),
                columns=columns
            )
            df_timestamp_and_zeros = pd.concat(
                [df_timestamps, df_zeros], axis=1)
            df_sensor_out = pd.concat(
                [df_timestamp_and_zeros, df_sensor_in], axis=0)
        else:
            min_time = max(min_time_video, min_time_sensor_in)
            df_sensor_out = df_sensor_in[
                (min_time <= df_sensor_in['timestamp']) &
                (df_sensor_in['timestamp'] <= max_time_sensor_in)]
        output_path = Path(
            output_data_dir).joinpath(
                sensor_files_mapping[key_]).as_posix()
        df_sensor_out.to_csv(
            output_path, header=True, index=None, float_format='%.6f')
        files_count += 1
        if is_debug:
            print('[WARNING] this is debug, break with only one loop.')
            break

    print('[INFO] output %d files in \"%s\"' % (
        files_count, output_data_dir))


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        prog='Select sensor data that the range of the timestamps are '
        'after video starting',
        add_help=True)
    parser.add_argument(
        '-s', '--setting_path',
        help='psth to setting toml',
        default='./setting/setting_sensor_default.toml',
        action='store', required=False)

    args = parser.parse_args()
    setting_path = args.setting_path
    setting = toml.load(setting_path)

    df_video_head_timestamp = pd.read_csv(
        setting['general']['video_head_timestamp_path'], header=0)

    # short name from file as key
    def get_key(video_name_):
        return '_'.join(video_name_.split('_')[0:2])

    video_head_timestamp_mapping = {}
    for video_name, timestamp in zip(
            df_video_head_timestamp['video_name'],
            df_video_head_timestamp['timestamp_of_video_head']):
        key_ = get_key(video_name)
        video_head_timestamp_mapping[key_] = timestamp

    # sensor file names mapping from short name
    sensor_files_mapping = {}
    input_data_dir = \
        setting['selected_timestamp']['input_sensor_data_dir']
    wild_path = Path(input_data_dir).joinpath('*.csv').as_posix()
    sensor_file_names = glob.glob(wild_path)
    sensor_file_names.sort()

    for i, file_path in enumerate(sensor_file_names):
        _, file_name = os.path.split(file_path)
        key_ = get_key(file_name)
        print(
            '%03d/%03d: %s' % (
                i+1, len(sensor_file_names), key_))
        if key_ in video_head_timestamp_mapping.keys():
            sensor_files_mapping[key_] = file_name
        else:
            print('[INFO] key: %s is not found in video.' % key_)

    select_data_main(
        sensor_files_mapping, video_head_timestamp_mapping, setting)


if __name__ == '__main__':
    main()
