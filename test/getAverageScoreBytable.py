# _*_ coding : utf-8 _*_
# @Time : 2026/5/19 19:12
# @Author : Morton
# @File : getAverageScoreBytable
# @Project : algorithm-engine

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.util.database import mysql_cursor
from src.algorithm.qualityTag import preprocessText, calDanmuScore, getVideoContext
from src.algorithm.uniqueness import calUniquenessScores


def get_average_score_by_table(table_name: str = "sub_danmu"):
    """统计整张表所有弹幕的平均质量得分"""
    with mysql_cursor() as cursor:
        cursor.execute(f"""
            SELECT id, vid, content
            FROM {table_name}
            WHERE status = 1
        """)
        rows = cursor.fetchall()

    if not rows:
        print(f"表 {table_name} 没有弹幕数据")
        return 0.0

    # 1. 分词 + 构建纯文本
    danmu_list = []
    clean_texts = []
    for row in rows:
        text = row['content']
        words = preprocessText(text)
        clean_text = ' '.join(words)
        danmu_list.append({'vid': row['vid'], 'text': text, 'words': words})
        clean_texts.append(clean_text)

    # 2. 全量计算独特性得分（不分组）
    uniqueness_scores = calUniquenessScores(clean_texts)

    # 3. 逐条计算弹幕得分
    scores = []
    for dm, uniqueness in zip(danmu_list, uniqueness_scores):
        context = getVideoContext(dm['vid'])
        score = calDanmuScore(dm['text'], dm['words'], context, uniqueness)
        scores.append(score)

    avg_score = float(np.mean(scores))
    print(f"表 {table_name}: 共 {len(scores)} 条弹幕, 平均得分: {avg_score:.4f}")
    return avg_score


if __name__ == '__main__':
    table = sys.argv[1] if len(sys.argv) > 1 else "sub_danmu"
    get_average_score_by_table(table)