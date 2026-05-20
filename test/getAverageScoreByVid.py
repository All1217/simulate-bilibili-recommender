# _*_ coding : utf-8 _*_
# @Time : 2026/5/19 18:28
# @Author : Morton
# @File : getAverageScoreByUid
# @Project : algorithm-engine

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from src.util.database import mysql_cursor
from src.algorithm.qualityTag import preprocessText, calDanmuScore
from src.algorithm.uniqueness import calUniquenessScores


def _get_video_keywords(vid: int) -> set:
    """查询视频的标题+标签，构建关键词集合"""
    keywords = set()
    with mysql_cursor() as cursor:
        cursor.execute("SELECT title, tags FROM video WHERE vid = %s", (vid,))
        row = cursor.fetchone()
    if not row:
        return keywords
    title = row.get('title', '') or ''
    tags_str = row.get('tags', '') or ''
    if title:
        keywords.update(preprocessText(title))
    if tags_str:
        for tag in tags_str.split():
            tag = tag.strip()
            if tag:
                keywords.add(tag)
    return keywords


def get_average_score_by_vid(vid: int) -> float:
    """获取指定视频下所有弹幕的平均质量得分"""
    # 1. 查询该视频所有有效弹幕
    with mysql_cursor() as cursor:
        cursor.execute("""
            SELECT id, content
            FROM danmu
            WHERE vid = %s AND status = 1
        """, (vid,))
        rows = cursor.fetchall()

    if not rows:
        print(f"视频 {vid} 没有弹幕数据")
        return 0.0

    # 2. 分词 + 构建纯文本
    danmu_list = []
    clean_texts = []
    for row in rows:
        text = row['content']
        words = preprocessText(text)
        clean_text = ' '.join(words)
        danmu_list.append({'text': text, 'words': words})
        clean_texts.append(clean_text)

    # 3. 批量计算唯一性得分
    uniqueness_scores = calUniquenessScores(clean_texts)

    # 4. 获取视频关键词
    video_keywords = _get_video_keywords(vid)

    # 5. 逐条计算弹幕得分
    scores = []
    for dm, uniqueness in zip(danmu_list, uniqueness_scores):
        score = calDanmuScore(dm['text'], dm['words'], video_keywords, uniqueness)
        scores.append(score)

    avg_score = float(np.mean(scores))
    print(f"视频 {vid}: {len(scores)} 条弹幕, 平均得分: {avg_score:.4f}")
    return avg_score


if __name__ == '__main__':
    get_average_score_by_vid(50)