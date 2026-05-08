import os
import json
from datetime import datetime, timedelta

########## 公共工具 ##########
today = datetime.now().strftime("%Y-%m-%d")

# 将时间精确到秒
def time_accurate_seconds(time):
    strftime = time.strftime('%Y-%m-%d %H:%M:%S')
    return datetime.fromisoformat(strftime)

# 计算两个时间的差值（秒）的绝对值
def time_difference_seconds(time1, time2):
    value = time1 - time2
    # 这里可能有毫秒数，所以要把小数点去掉
    seconds = int(value.total_seconds())
    return abs(seconds)

# 给指定的时间加相应的秒数，得到新的时间
def time_increase_seconds(time, seconds):
    new_time = time + timedelta(seconds=seconds)
    return new_time

def str_to_datetime(str):
    format_str = "%Y-%m-%d %H:%M:%S"
    return datetime.strptime(str, format_str)

def get_need_dir(file):
    current_dir = os.path.dirname(os.path.abspath(__file__))
    str_path = os.path.join(current_dir, file)
    return str_path

#写入文本到指定文件
def with_text(txt):
    with open(get_need_dir(f'data/tick_data_{today}.txt'), 'a') as file:
        file.write('\n' + txt)

if __name__ == "__main__":
    pass