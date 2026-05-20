# _*_ coding : utf-8 _*_
# @Time : 2026/2/18 17:07
# @Author : Morton
# @File : qualityAnalyzer
# @Project : algorithm-engine

from src.util.database import mysql_cursor, get_redis_client
from src.util.jsonHandler import saveJson, loadJson
from src.common.redisConstants import QUALITY_THRESHOLD_KEY
import numpy as np
from datetime import datetime
from collections import defaultdict


def analyze(isSave=True):
    """
    分析弹幕质量分数的分布情况，帮助调整阈值
    Args:
        isSave: 是否将结果保存到JSON文件
    Returns:
        包含分析结果的字典
    """
    result = {
        "analyze_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "score_distribution": {},
        "interval_distribution": []
    }

    # 收集所有弹幕用于计算分数分布
    with mysql_cursor() as cursor:
        cursor.execute("""
            SELECT uid, content, vid, time_point
            FROM danmu
            WHERE status = 1
        """)
        rows = cursor.fetchall()

    if not rows:
        return result

    # 导入评分函数（避免循环引用在函数内导入）
    from src.algorithm.qualityTag import calQualityStats

    # 按 uid 分组，批量计算每个用户的弹幕分数
    uid_groups = defaultdict(list)
    for i, row in enumerate(rows):
        uid_groups[row['uid']].append(i)

    all_scores = []
    for uid in uid_groups:
        try:
            scores, _ = calQualityStats(uid)
            all_scores.extend(scores)
        except Exception as e:
            continue

    if not all_scores:
        return result

    # 基础统计
    result["score_distribution"] = {
        "total_danmus": len(all_scores),
        "min": round(float(min(all_scores)), 3),
        "max": round(float(max(all_scores)), 3),
        "mean": round(float(np.mean(all_scores)), 3),
        "median": round(float(np.median(all_scores)), 3),
        "percentile_20": round(float(np.percentile(all_scores, 20)), 3),
        "percentile_40": round(float(np.percentile(all_scores, 40)), 3),
        "percentile_60": round(float(np.percentile(all_scores, 60)), 3),
        "percentile_80": round(float(np.percentile(all_scores, 80)), 3),
    }

    # 区间分布
    bins = [0, 0.2, 0.4, 0.6, 0.8, 1.0]
    labels = ['0-0.2', '0.2-0.4', '0.4-0.6', '0.6-0.8', '0.8-1.0']
    for i in range(len(bins) - 1):
        count = sum(1 for s in all_scores if bins[i] <= s < bins[i + 1])
        percentage = round(count / len(all_scores) * 100, 1)
        result["interval_distribution"].append({
            "interval": labels[i],
            "danmu_count": count,
            "percentage": percentage
        })

    if isSave:
        saveJson("qualityAnalysis.json", result)

    return result


def resultPrint(result):
    """打印分析结果"""
    if not result.get('score_distribution'):
        print("无有效数据")
        return
    print("=" * 60)
    print("📊 弹幕质量分数分布分析报告")
    print("=" * 60)
    dist = result['score_distribution']
    print(f"  弹幕总数: {dist['total_danmus']}")
    print(f"  平均分: {dist['mean']}")
    print(f"  中位数: {dist['median']}")
    print(f"  P20: {dist['percentile_20']}  |  P40: {dist['percentile_40']}")
    print(f"  P60: {dist['percentile_60']}  |  P80: {dist['percentile_80']}")
    print("\n【分数区间分布】")
    for item in result['interval_distribution']:
        print(f"  {item['interval']}: {item['danmu_count']} 条 ({item['percentage']}%)")


def recoQualityThre():
    """
    根据分析结果给出阈值建议
    高质量阈值 = P60（分数前40%为高质量弹幕贡献者）
    低质量阈值 = P20（分数后20%为低质量弹幕倾向）
    """
    res = None
    try:
        res = loadJson("qualityAnalysis.json")
    except FileNotFoundError:
        print("分析结果文件不存在，正在重新分析……")
        res = analyze(True)

    resDict = {}
    score_dist = res.get('score_distribution', {}) if res else {}

    if score_dist:
        resDict['high_quality_threshold'] = score_dist.get('percentile_60', 0.5)
        resDict['low_quality_threshold'] = score_dist.get('percentile_20', 0.3)
    else:
        print("无有效数据，使用默认阈值")
        resDict = {
            'high_quality_threshold': 0.5,
            'low_quality_threshold': 0.3
        }

    # 保留 qualityThreshold.json 中的其他阈值字段，只更新高/低质量阈值
    try:
        existing = loadJson('qualityThreshold.json')
        for k, v in existing.items():
            if k not in resDict:
                resDict[k] = v
    except FileNotFoundError:
        pass

    try:
        redis_client = get_redis_client()
        redis_client.hset(QUALITY_THRESHOLD_KEY, mapping=resDict)
        print(f"质量阈值已写入Redis: {resDict}")
    except Exception as e:
        print(f"保存到Redis失败: {e}")
        saveJson("qualityThreshold.json", resDict)
        print("已回退保存到 qualityThreshold.json")

    return resDict


def startQualityAnalyze():
    """快速启动：分析分布 + 生成阈值推荐"""
    result = analyze(isSave=True)
    # resultPrint(result)
    return recoQualityThre()


if __name__ == '__main__':
    startQualityAnalyze()