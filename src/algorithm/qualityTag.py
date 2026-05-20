# _*_ coding : utf-8 _*_
# @Time : 2026/2/18
# @Author : Morton
# @File : qualityTag.py
# @Project : algorithm-engine

from src.util.jsonHandler import loadJson
from src.util.database import get_redis_client
from src.common.redisConstants import QUALITY_THRESHOLD_KEY
from src.util.wordHandler import get_segmenter
from src.algorithm.uniqueness import calUniquenessScores
import numpy as np
import jieba.analyse
from collections import defaultdict

PROFESSIONAL_WORDS = loadJson('professionalWords.json')


def loadThreshold():
    """三级阈值加载：Redis → JSON → 默认值"""
    try:
        redis_client = get_redis_client()
        temp = redis_client.hgetall(QUALITY_THRESHOLD_KEY)
        if temp:
            return {
                'high_quality_threshold': float(temp.get('high_quality_threshold', 0.5)),
                'low_quality_threshold': float(temp.get('low_quality_threshold', 0.3)),
                'professional_ratio_threshold': float(temp.get('professional_ratio_threshold', 0.2)),
                'long_danmaku_threshold': int(temp.get('long_danmaku_threshold', 20)),
                'short_danmaku_threshold': int(temp.get('short_danmaku_threshold', 5))
            }
    except Exception as e:
        print(f'从Redis获取质量阈值失败: {e}')

    try:
        config = loadJson('qualityThreshold.json')
        return {
            'high_quality_threshold': config.get('high_quality_threshold', 0.5),
            'low_quality_threshold': config.get('low_quality_threshold', 0.3),
            'professional_ratio_threshold': config.get('professional_ratio_threshold', 0.2),
            'long_danmaku_threshold': config.get('long_danmaku_threshold', 20),
            'short_danmaku_threshold': config.get('short_danmaku_threshold', 5)
        }
    except Exception as e:
        print(f'加载质量阈值失败，使用默认值: {e}')
        return {
            'high_quality_threshold': 0.5,
            'low_quality_threshold': 0.3,
            'professional_ratio_threshold': 0.2,
            'long_danmaku_threshold': 20,
            'short_danmaku_threshold': 5
        }


THRESHOLDS = loadThreshold()

_segmenter = get_segmenter(use_stopwords=True, use_pos_filter=False)


def preprocessText(text):
    if not text:
        return []
    return _segmenter.segment(text)


def _countProfessionalWords(words):
    return sum(1 for w in words if w in PROFESSIONAL_WORDS)


def calDanmuScore(text, words, video_keywords, uniqueness_score=None):
    if not text or not words:
        return 0.0
    if uniqueness_score is None:
        uniqueness_score = 1.0
    score = 0.0

    # 1. 文本长度（20%）
    length_score = min(len(words) / 10, 1.0)
    score += length_score * 0.2

    # 2. 内容深度（30%）
    professional_count = _countProfessionalWords(words)
    if len(words) > 0:
        professional_ratio = professional_count / len(words)
        depth_score = 0.3 + professional_ratio * 0.7
        depth_score = min(depth_score, 1.0)
    else:
        depth_score = 0.3
    score += depth_score * 0.3

    # 3. 内容独特性（30%）
    score += uniqueness_score * 0.3

    # 4. 内容相关性（20%）
    #    基于 jieba TF-IDF 提取弹幕关键词，与视频标题+标签关键词的交集占比
    if video_keywords:
        clean_text = ' '.join(words)
        danmu_keywords = set(jieba.analyse.extract_tags(clean_text, topK=3))
        if danmu_keywords:  # Jaccard 系数
            overlap = danmu_keywords & video_keywords
            relevance = len(overlap) / len(danmu_keywords)
            score += relevance * 0.2

    return min(score, 1.0)


def loadDanmu(uid, preload=None):
    """
    从预加载数据中提取用户弹幕列表，无预加载时返回空列表（不查库）。
    """
    if preload and 'danmu_list' in preload:
        return preload['danmu_list']
    return []


def getVideoKeywords(vid, preload):
    """
    从预加载数据中获取视频标题+标签的关键词集合。
    若无预加载数据或 vid 不存在，返回空 set。
    """
    if not preload or 'vid_info_map' not in preload:
        return set()
    info = preload['vid_info_map'].get(vid)
    if not info:
        return set()

    keywords = set()
    title = info.get('title', '') or ''
    tags_str = info.get('tags', '') or ''

    if title:
        title_words = preprocessText(title)
        keywords.update(title_words)
    if tags_str:
        for tag in tags_str.split():
            tag = tag.strip()
            if tag:
                keywords.add(tag)
    return keywords


def calQualityStats(uid, preload=None):
    danmakus = loadDanmu(uid, preload)
    if not danmakus:
        return [], {}

    # ===== 分词并按 vid 分组 =====
    vid_groups = defaultdict(list)
    for idx, danmaku in enumerate(danmakus):
        text = danmaku['text']
        words = preprocessText(text)
        danmaku['_words'] = words
        danmaku['_clean_text'] = ' '.join(words)
        vid_groups[danmaku['vid']].append(idx)

    # ===== 按视频分组计算独特性得分 =====
    uniqueness_map = {}
    for vid, indices in vid_groups.items():
        group_texts = [danmakus[i]['_clean_text'] for i in indices]
        group_scores = calUniquenessScores(group_texts)
        for i, score in zip(indices, group_scores):
            uniqueness_map[i] = score

    # ===== 逐条评分与统计 =====
    scores = []
    stats = {
        'total_count': len(danmakus),
        'professional_count': 0,
        'long_count': 0,
        'short_count': 0,
        'total_length': 0,
        'scores': []
    }

    for idx, danmaku in enumerate(danmakus):
        text = danmaku['text']
        words = danmaku['_words']
        vid = danmaku['vid']

        video_keywords = getVideoKeywords(vid, preload)
        uniqueness_score = uniqueness_map.get(idx, 1.0)

        score = calDanmuScore(text, words, video_keywords, uniqueness_score)
        scores.append(score)
        stats['scores'].append(score)

        if any(w in PROFESSIONAL_WORDS for w in words):
            stats['professional_count'] += 1

        text_len = len(text)
        stats['total_length'] += text_len
        if text_len >= THRESHOLDS['long_danmaku_threshold']:
            stats['long_count'] += 1
        elif text_len <= THRESHOLDS['short_danmaku_threshold']:
            stats['short_count'] += 1

    return scores, stats


def calQualityTags(uid, preload=None):
    scores, stats = calQualityStats(uid, preload)
    if not scores:
        return {}
    tags = {}
    total = stats['total_count']
    avg_score = np.mean(scores)
    if avg_score >= THRESHOLDS['high_quality_threshold']:
        tags['高质量弹幕贡献者'] = round(avg_score, 2)
    elif avg_score <= THRESHOLDS['low_quality_threshold']:
        tags['低质量弹幕倾向'] = round(avg_score, 2)
    if total > 0:
        professional_ratio = stats['professional_count'] / total
        if professional_ratio >= THRESHOLDS['professional_ratio_threshold']:
            tags['干货贡献者'] = round(professional_ratio, 2)
    if total > 0:
        long_ratio = stats['long_count'] / total
        short_ratio = stats['short_count'] / total
        if long_ratio > 0.3 and long_ratio > short_ratio:
            tags['长文弹幕偏好'] = round(long_ratio, 2)
        elif short_ratio > 0.5:
            tags['短平快弹幕'] = round(short_ratio, 2)
    return tags


def geneQualityTags(uid, preload=None):
    """构建用户质量画像（主函数）"""
    tags = calQualityTags(uid, preload)
    return tags if tags else {}