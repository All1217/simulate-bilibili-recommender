# _*_ coding : utf-8 _*_
# @Time : 2026/5/19 13:00
# @Author : Morton
# @File : insertDanmu
# @Project : algorithm-engine

import sys
import os
import random
import re
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.util.database import get_mysql_conn

VID = 51
MODE = 0
UID_POOL = [
    "1", "2",
    "3", "4", "5", "6", "7", "8", "9", "10", "11", "12",
    "13", "14", "15", "16", "17", "18", "19", "20", "21", "480119548703100"
]
DATA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "Assets", "弹幕.txt"
)


def parse_time(time_str: str) -> float:
    """将 H:MM:SS.ss 转为秒"""
    h, m, s = time_str.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)


def extract_content(text: str) -> str:
    """去掉 ASS 样式标记 {\\...}，返回纯文本"""
    text = re.sub(r'\{[^}]*\}', '', text)
    return text.strip()


def parse_danmu(filepath: str) -> list:
    """解析弹幕文件，返回 [{time_point, content}, ...]"""
    danmu_list = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line.startswith('Dialogue:'):
                continue
            # 格式: Dialogue: Layer,Start,End,Style,Name,ML,MR,MV,Effect,Text
            rest = line[len('Dialogue: '):]
            parts = rest.split(',', 9)
            if len(parts) < 10:
                continue
            time_point = parse_time(parts[1])
            content = extract_content(parts[9])
            if content:
                danmu_list.append({'time_point': time_point, 'content': content})
    return danmu_list


def insert_danmu():
    danmu_list = parse_danmu(DATA_FILE)
    if not danmu_list:
        print("未解析到任何弹幕数据")
        return

    conn = get_mysql_conn()
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    sql = """
        INSERT INTO danmu (vid, uid, content, mode, time_point, create_date)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    inserted = 0
    for dm in danmu_list:
        uid = random.choice(UID_POOL)
        # uid = str(random.randint(10**14, 10**15 - 1))
        cursor.execute(sql, (VID, uid, dm['content'], MODE, dm['time_point'], now))
        inserted += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"成功插入 {inserted} 条弹幕")


if __name__ == '__main__':
    insert_danmu()
