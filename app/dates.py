# -*- coding: utf-8 -*-
"""
app/dates.py —— 逻辑日（全项目唯一的「今天」来源）

为什么要这个文件：
凌晨 0 点到 4 点之间人往往还没睡，这时候标的东西应该算「昨天」的。
如果直接用系统日期，刚标的记号第二天一开软件就「不是今天」了，
容易让人以为标记丢了。所以全项目统一用「凌晨 4 点为界」的逻辑日。

规则：
1. 取本地当前时间；
2. 小时数小于 4 → 算作「昨天」；否则算作「今天」；
3. 返回 'YYYY-MM-DD' 字符串，格式与数据库 marks.marked_date 完全一致。

约定（铁律）：
全项目任何地方要判断「今天」都必须调用本文件的 today_text()；
不许在别处写 datetime.date.today()，否则凌晨 0–4 点的行为会不一致。
"""

from datetime import datetime, timedelta

# 逻辑日的分界小时：0 点到 3 点 59 分都算前一天
DAY_START_HOUR = 4

# 日期字符串格式，与数据库里 marks.marked_date 的格式一致
DATE_FORMAT = '%Y-%m-%d'


def _logical_today():
    """内部函数：算出逻辑今天的 date 对象（全项目只有这里读系统日期）。"""
    now = datetime.now()
    if now.hour < DAY_START_HOUR:
        # 凌晨 0 点到 3 点 59 分：算作昨天
        return now.date() - timedelta(days=1)
    return now.date()


def today_text():
    """返回「逻辑今天」的日期字符串，例如 '2026-10-28'。"""
    return _logical_today().strftime(DATE_FORMAT)


def today_date():
    """返回「逻辑今天」的 date 对象，给日历算年月用。"""
    return _logical_today()
