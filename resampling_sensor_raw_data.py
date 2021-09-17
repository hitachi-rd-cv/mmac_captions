# coding: utf-8
"""Sensor raw data resampling.

Copyright (c) 2021 Hitachi,Ltd.

This software is released under the MIT License.
http://opensource.org/licenses/mit-license.php
"""
import argparse
import datetime
import os
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import toml


IS_DEBUG = False

# ---------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------


def convert_time_text_format_to_microsec(time_text):
    """Convert timestamp text format to datetime value.

    Convert timestamp text format "YY/MM/DD hh:mm:ss.000000" to
    datetime value
    """
    before_dec_point, after_dec_point = time_text.split('.')
    d_sec = datetime.datetime.strptime(
        before_dec_point, '%Y-%m-%d %H:%M:%S')
    assert len(after_dec_point) == 6
    # instead of use .%f, , add msec part (digits after the decimal)
    m_seconds = datetime.timedelta(
        microseconds=int(after_dec_point))
    result_d = d_sec + m_seconds
    return result_d


def convert_to_data_time_format_microsec(time_text):
    """Convert the time text format of CMU-MMAC to a datetime value.

    Convert timestamp text format from CMU-MMAC's one to Python's
    datetime value of "YY/MM/DD hh:mm:ss.000000"
    """
    time_cols = [int(txt) for txt in time_text.split('_')]
# coding: utf-8
    txt = '%02d:%02d:%02d' % (time_cols[0], time_cols[1], time_cols[2])
    d_sec = datetime.datetime.strptime(txt, '%H:%M:%S')
    # original is 7 digits after the decimal point,
    # and change to 6 digits after the decimal point
    m_seconds = datetime.timedelta(
        microseconds=int(time_cols[3]//10))
    result_d = d_sec + m_seconds
    return result_d


# ---------------------------------------------------------------------
# raw data resampling
# ---------------------------------------------------------------------


def interpolate(df_in, col_name, width, b_r):
    """Interpolate.

    Parameters
    ----------
    df_in:
        pre-interpolated data series
        (column 0: time, column 1: value at each time)
    width:
        width between points
    b_r:
        a representative element of lattice point in time axis

    Returns
    -------
    times
    series values
    """
    leading_time = pd.Timestamp(
        np.array(df_in.SysTime)[0]).to_pydatetime()
    tail_time = pd.Timestamp(
        np.array(df_in.SysTime)[-1]).to_pydatetime()
    dt1 = (b_r-leading_time).total_seconds()
    b_0 = b_r-datetime.timedelta(seconds=(dt1 // width) * width)
    dt2 = (tail_time - b_0).total_seconds()
    number = dt2 // width
    bs_ = np.array([
        b_0+datetime.timedelta(seconds=t)
        for t in np.linspace(0, width * number, int(number + 1))])
    df_temp = pd.DataFrame(np.array([bs_, [np.NAN] * len(bs_)]).T)
    df_temp.index = df_temp[0]  # column 0 is time
    # Note.
    #   - add the dummy records by sampling.
    #   - following is troubleshoot for crash if duplicated
    #     index of df_in.
    df_modif = df_in.reindex(df_in.index.union(df_temp.index))
    df_result_ = df_modif[col_name].interpolate(method='values')
    index_intersect = df_result_.index.intersection(df_temp.index)
    return bs_, df_result_[index_intersect]


def get_data_file_path_list(data_file_list_path):
    """Get mappting of video id to sensor data files.

    video id to (original video id, [file 1, ..., file n])
     where file 1, ..., file n are one series data.
    Note.
    - Original video id in input files sometimes mixed lower and upper case.
    - To treat several case, lower case of them are used as key of mapping.
    """
    mapping = {}
    with open(data_file_list_path) as f_in:
        for line in f_in.readlines():
            if line.strip() == '':
                continue
            video_name_prefix, files_txt = line.strip().split('\t')
            mapping[video_name_prefix.lower()] = (
                video_name_prefix, files_txt.split(','))
    return mapping


def get_start_timestamp_mapping(file_path):
    """Get mapping of video name id to star timestamp."""
    mapping = {}
    with open(file_path) as f_in:
        for line in f_in.readlines():
            if line.strip() == '':
                continue
            video_name, time_txt = line.strip().split(',')
            video_name_prefix = \
                '_'.join(video_name.split('_')[0:2])
            mapping[video_name_prefix.lower()] = time_txt
    return mapping


def resampling(
        setting, sample_freq, output_data_dir,
        data_files, start_timestamp, common_values):
    """Resampling sensor data for one video id."""
    input_data_dir = setting['resampling']['sensor_original_data_root_path']
    series_names = setting['resampling']['use_columns']
    # Note.
    # to get more precise sample width value, here using following
    # formula (insted of (1.0 / sample_freq))
    sample_width = int(1000000*(1.0 / sample_freq)) / 1000000.0

    ret = {}
    ret['err'] = False
    for file_name_after_root in data_files:
        input_path = \
            Path(input_data_dir).joinpath(
                file_name_after_root).as_posix()
        if not os.path.exists(input_path):
            print(
                '[WARNING] skip %s (file not found)' %
                file_name_after_root)
            ret['err'] = True
            if 'ng_files' in ret:
                ret['ng_files'].append(file_name_after_root)
            else:
                ret['ng_files'] = [file_name_after_root]
            continue
        df_in = pd.read_csv(
            input_path,
            sep='\t', skiprows=1, header=0,
            index_col=None)
        # remove record of lack value
        if not df_in['Count'].dtype == 'int64':
            df_in = df_in[
                (df_in['Count'].astype(str).str.contains('ERR*')).map(
                    lambda x: not x)]
        # check
        check_ng_info = [
            (file_name_after_root, i, type(t), t)
            for i, t in enumerate(df_in.SysTime) if type(t) is not str]
        if len(check_ng_info) > 0:
            print('[WARNING] some data broken')
            print(check_ng_info)
            assert False
        df_in.SysTime = [
            convert_to_data_time_format_microsec(t)
            for t in df_in.SysTime]
        df_in.index = df_in.SysTime
        for series_name in series_names:
            _, df_result = interpolate(
                df_in, series_name, sample_width, start_timestamp)
            output_path = \
                Path(output_data_dir).joinpath(
                    '%s_%s%s.csv' % (
                        file_name_after_root.replace('.txt', ''),
                        series_name,
                        common_values['resampling_file_name_surfix'])
                    ).as_posix()
            output_dir_leaf, _ = os.path.split(output_path)
            if not os.path.exists(output_dir_leaf):
                # Note. not support symlink case
                os.makedirs(output_dir_leaf)
            df_result.to_csv(output_path, header=False, float_format='%.6f')

    return ret


def resampling_main(setting, common_values):
    """Resampling all sensor data."""
    sample_freq = float(setting['general']['sampling_frequency'])
    data_files_mapping = get_data_file_path_list(
        setting['resampling']['sensor_files_list_path'])
    start_timestamp_mapping = get_start_timestamp_mapping(
        setting['general']['video_head_timestamp_path'])
    output_sensor_resample_data_path = \
        setting['resampling']['output_sensor_resample_data_path']
    if not os.path.exists(output_sensor_resample_data_path):
        # Note. not support symlink case
        os.makedirs(output_sensor_resample_data_path)

    ret = {}
    ret['err'] = False
    ret['ng_files'] = []
    is_debug = IS_DEBUG
    keys = [k for k in data_files_mapping]
    keys.sort()
    for i, video_name_key in enumerate(keys):
        video_name_prefix, data_files = \
            data_files_mapping[video_name_key]
        if video_name_key not in start_timestamp_mapping.keys():
            print('[WARNING] skip %s, '
                  'there is no correspondence of timestamp.'
                  % video_name_prefix)
            continue
        start_time_text = start_timestamp_mapping[video_name_key]
        start_timestamp = convert_time_text_format_to_microsec(
            start_time_text)
        print('%03d/%03d: %s' % (i+1, len(keys), video_name_prefix))
        common_values['resampling_file_name_surfix'] = \
            '_resample_%.1fHz' % sample_freq
        ret_ = resampling(
            setting,
            sample_freq,
            output_sensor_resample_data_path,
            data_files,
            start_timestamp,
            common_values)
        ret['err'] = ret['err'] or ret_['err']
        if ret['err']:
            ret['ng_files'] += ret_['ng_files']
        if is_debug:
            print('[WARNING] this is debug, break with only one loop.')
            break
    return common_values, ret


# ---------------------------------------------------------------------
# column concat (=create feature)
# ---------------------------------------------------------------------


def get_column_name_from_file_path(file_name_after_root):
    """Get column name from file path.

    For example,
    from
    S07_Brownie_3DMGX1/3337_01-30_16_30_49-time.txt
    to
    3DMGX1_3337
    """
    # Note.
    # this function is only support for CMU-MMAC dataset and
    # other general dataset should be supprted.
    folder_name, file_name = file_name_after_root.split('/')
    if folder_name.endswith('3DMGX1'):
        series_type = '3DMGX1'
    elif folder_name.endswith('6DOFv4'):
        series_type = '6DOFv4'
    sensor_id = file_name.split('_')[0]
    return '%s_%s' % (series_type, sensor_id)


def create_feature(
        input_data_dir,
        output_data_dir,
        series_names,
        data_files,
        data_file_surfix,
        output_file_name_prefix,
        time_stamp_col_name):
    """Create one file by concatenating each columns of series.

    Note.
      - ordering to adjacent the same physical quantity
      - (such as Accel_X of location 0,1,2...) for each sensor devices.
    """
    is_first_column = True
    is_success = True

    for series_name in series_names:
        for file_name_after_root in data_files:
            file_id = get_column_name_from_file_path(
                file_name_after_root)
            time_series_column_path = os.path.join(
                input_data_dir,
                '%s_%s%s.csv' % (
                    file_name_after_root.replace('.txt', ''),
                    series_name,
                    data_file_surfix))
            if not os.path.exists(time_series_column_path):
                is_success = False
                continue
            df_column = pd.read_csv(
                time_series_column_path, header=None)
            df_column.columns = [
                time_stamp_col_name,
                '%s_%s' % (file_id, series_name)]
            if is_first_column:
                df_main = df_column.copy()
                is_first_column = False
            else:
                df_main = pd.merge(
                    df_main, df_column,
                    on=time_stamp_col_name, how='outer')
    if not is_success:
        return False

    df_main = df_main.sort_values(
        by=[time_stamp_col_name], ascending=True)
    df_main.index = np.arange(len(df_main.index))

    check_nearly_time_duplicate(df_main)

    # select records without nan
    cols = [s for s in df_main.columns if s != time_stamp_col_name]
    main_data = np.array(df_main[cols])
    record_use_info = \
        [not np.isnan(main_data[i]).any() for i in range(main_data.shape[0])]
    df_main_select = df_main[record_use_info]
    # save
    df_main_select.to_csv(
        os.path.join(
            output_data_dir,
            '%s_selected.csv' % output_file_name_prefix),
        float_format='%.6f', header=True, index=None)
    return True


def check_nearly_time_duplicate(df_main):
    """Wheather very close two time points exist or not.

    Check that there does not exists the case records very near
    timestamps which can be seen as same time.
    """
    epsilon = 0.000100
    for i in range(1, len(df_main.index)):
        delta = df_main.index[i] - df_main.index[i-1]
        if delta < epsilon:
            print('[WARNING] There is some records such that their '
                  'timestumps are too close.')
            print('  index: %d and %d' % (i, i-1))
            print('  timestamp: %s and %s'
                  % (df_main.index[i] - df_main.index[i-1]))
            sys.exit(0)


def create_feature_main(setting, common_values):
    """Create sensor feature by concatenating columns."""
    is_debug = IS_DEBUG
    output_dir_path = \
        setting['resampling']['output_sensor_col_concat_path']
    if not os.path.exists(output_dir_path):
        # Note. not support symlink case
        os.makedirs(output_dir_path)
    timestamp_col_name = setting['resampling']['timestamp_col_name']
    # surfix of input series data file name without extension
    data_file_surfix = common_values['resampling_file_name_surfix']
    data_files_mapping = get_data_file_path_list(
        setting['resampling']['sensor_files_list_path'])
    ret = {}
    ret['err'] = False
    keys = [k for k in data_files_mapping]
    keys.sort()
    for i, video_name_key in enumerate(keys):
        video_name_prefix, data_files = \
            data_files_mapping[video_name_key]
        output_file_name_prefix = \
            '%s%s' % (video_name_prefix, data_file_surfix)
        print('%03d/%03d: %s' % (i+1, len(keys), output_file_name_prefix))
        res = create_feature(
            setting['resampling']['output_sensor_resample_data_path'],
            output_dir_path,
            setting['resampling']['use_columns'],
            data_files,
            data_file_surfix,
            output_file_name_prefix,
            timestamp_col_name)
        if not res:
            print('[WARNING] fail for %s' % output_file_name_prefix)
            ret['err'] = True
            if 'ng_files' in ret:
                ret['ng_files'].append(output_file_name_prefix)
            else:
                ret['ng_files'] = [output_file_name_prefix]
            continue
        if is_debug:
            print('[WARNING] this is debug, break with only one loop.')
            break
    return ret


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        prog='sensor raw data resampling',
        add_help=True)
    parser.add_argument(
        '-s', '--setting_path',
        help='path to setting toml',
        default='./setting/setting_sensor_default.toml',
        action='store', required=False)

    args = parser.parse_args()
    setting_path = args.setting_path
    setting = toml.load(setting_path)
    common_values = {}
    common_values, ret1 = resampling_main(setting, common_values)
    print('=' * 80)
    ret2 = create_feature_main(setting, common_values)
    print('=' * 80)
    for i, (ret_, msg_sub) in enumerate([
            (ret1, 'original sensor data files are not found.'),
            (ret2, 'sensor feature files are not created.')]):
        if ret_['err']:
            msg = '[WARNING] %s %s ' % (len(ret_['ng_files']), msg_sub)
            msg += 'Please see log file: \"./fail_cases_proc%d.log\".' % (i+1)
            print(msg)
            with open('fail_cases_proc%d.log' % (i+1), 'w') as f_w:
                for ng_file in ret_['ng_files']:
                    f_w.write('%s\n' % ng_file)


if __name__ == '__main__':
    main()
