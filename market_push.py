#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股超短行情双体系分析 + 明日预案 + 企业微信自动推送
======================================================
融合: taoguba-ultra-short(淘股吧超短) + oute-dragon-strategy(欧特慢慢龙头)
数据: akshare + 腾讯财经API
推送: 企业微信机器人 Webhook
版本: V1.2 — 支持Server酱推送
"""

import akshare as ak
import requests
import json
import sys
import io
import os
import time
import traceback
import argparse
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================================
# 配置
# ============================================================
# WeChat Work webhook - from env var, fallback to default
WEBHOOK_URL = os.environ.get(
    "WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=b0683641-3e75-4f3e-8808-ddb4bbcfc387"
)
# Server酱 SENDKEY - from env var, skipped if empty
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
# Push method: wechat / serverchan / all (can also be set via --push)
PUSH_METHOD = os.environ.get("PUSH_METHOD", "wechat")
# Project root
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))

# ============================================================
# 工具函数
# ============================================================

def get_latest_trading_day(date_override: str = None) -> str:
    """获取最近已完成交易日"""
    if date_override:
        return date_override

    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo('Asia/Shanghai'))
    except Exception:
        now = datetime.now()

    today = now

    if today.weekday() == 5:
        today = today - timedelta(days=1)
    elif today.weekday() == 6:
        today = today - timedelta(days=2)

    if today.date() == now.date() and now.hour < 15 and now.weekday() < 5:
        today = today - timedelta(days=1)
        if today.weekday() == 5:
            today = today - timedelta(days=1)
        elif today.weekday() == 6:
            today = today - timedelta(days=2)

    return today.strftime("%Y%m%d")


def fetch_market_data(date_str: str) -> dict:
    """获取全市场数据"""
    data = {
        "date": date_str,
        "index": {},
        "limit_up_board": None,
        "strong_pool": None,
        "prev_day_board": None,
        "sentiment": {},
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 1. 上证指数
    try:
        df_sh = ak.stock_zh_index_daily(symbol="sh000001")
        last5 = df_sh.tail(6)
        latest = last5.iloc[-1]
        prev = last5.iloc[-2]
        data["index"] = {
            "close": float(latest["close"]),
            "open": float(latest["open"]),
            "change_pct": round((float(latest["close"]) - float(latest["open"])) / float(latest["open"]) * 100, 2),
            "volume_wan": round(float(latest["volume"]) / 10000, 0),  # 成交量(万手)
            "prev_close": float(prev["close"]),
            "trend_5d": [{"date": str(r["date"]), "close": float(r["close"]), "vol": float(r["volume"])}
                         for _, r in last5.iterrows()],
        }
    except Exception as e:
        data["index"]["error"] = str(e)

    # 2. 涨停板
    try:
        df_zt = ak.stock_zt_pool_em(date=date_str)
        data["limit_up_board"] = df_zt
        data["sentiment"]["total_limit_up"] = len(df_zt)
    except Exception as e:
        data["limit_up_board_error"] = str(e)

    # 3. 强势池
    try:
        df_strong = ak.stock_zt_pool_strong_em(date=date_str)
        data["strong_pool"] = df_strong
        data["sentiment"]["total_strong"] = len(df_strong) if df_strong is not None else 0
    except:
        data["sentiment"]["total_strong"] = 0

    # 4. 前一日涨停(对比)
    try:
        prev_date = (datetime.strptime(date_str, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
        df_prev = ak.stock_zt_pool_em(date=prev_date)
        data["prev_day_board"] = df_prev
        data["sentiment"]["prev_total_limit_up"] = len(df_prev) if df_prev is not None else 0
    except:
        data["sentiment"]["prev_total_limit_up"] = 0

    return data


def analyze_taoguba(data: dict) -> str:
    """淘股吧超短体系分析"""
    lines = []
    lines.append("## 🏴‍☠️ 一、淘股吧超短体系解读")
    lines.append("")

    idx = data.get("index", {})
    lb = data.get("limit_up_board")
    prev_lb = data.get("prev_day_board")

    # --- 1. 情绪周期 ---
    lines.append("### 1. 情绪周期：五阶段定位")
    lines.append("")

    total_zt = data["sentiment"].get("total_limit_up", 0)
    prev_zt = data["sentiment"].get("prev_total_limit_up", 0)

    close = idx.get("close", 0)
    change_pct = idx.get("change_pct", 0)
    volume_wan = idx.get("volume_wan", 0)

    # 周期判断逻辑
    if change_pct < -0.5 and total_zt < prev_zt * 0.7:
        stage = "退潮初期(阶段5入口)"
        stage_desc = "指数放量下跌+涨停数骤降→空方释放，节点切换进行中"
        position_advice = "30-40%(退潮防守)"
    elif change_pct < -0.3 and total_zt < 60:
        stage = "混沌/高位震荡(阶段4)"
        stage_desc = "指数偏弱+赚钱效应收缩→多看少动"
        position_advice = "30-50%(混沌猥琐)"
    elif total_zt >= 80 and change_pct > 0:
        stage = "主升期(阶段2-3)"
        stage_desc = "指数配合+涨停数充足→积极做多"
        position_advice = "70-100%(主升满仓)"
    else:
        stage = "震荡分化(阶段3-4过渡)"
        stage_desc = "指数方向不明+涨停数中等→精选个股"
        position_advice = "40-60%(震荡仓位)"

    lines.append(f"> **当前阶段：{stage}**")
    lines.append(f"> {stage_desc}")
    lines.append(f"> 建议仓位：{position_advice}")
    lines.append("")

    # --- 2. 指数环境 ---
    lines.append("### 2. 指数环境（定水位）")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| 上证收盘 | **{close:.2f}** |")
    lines.append(f"| 涨跌幅 | {change_pct:+.2f}% |")
    lines.append(f"| 沪市量能 | {volume_wan:.0f}万手 |")

    # 量能→高度对应
    if volume_wan > 80000:
        height_est = "11板+"
    elif volume_wan > 70000:
        height_est = "9-11板"
    elif volume_wan > 60000:
        height_est = "7-9板"
    else:
        height_est = "5-7板"
    lines.append(f"| 预期连板高度 | {height_est} |")
    lines.append("")

    # --- 3. 连板天梯分析 ---
    lines.append("### 3. 连板天梯与龙头识别")
    lines.append("")

    if lb is not None and not lb.empty:
        # 按连板数分组
        if "连板数" in lb.columns:
            lb_groups = defaultdict(list)
            for _, row in lb.iterrows():
                lb_num = int(row["连板数"])
                lb_groups[lb_num].append({
                    "name": str(row.get("名称", "")),
                    "code": str(row.get("代码", "")),
                    "industry": str(row.get("所属行业", "")),
                    "turnover": float(row.get("换手率", 0)),
                    "stats": str(row.get("涨停统计", "")),
                })

            lines.append("| 连板 | 数量 | 代表标的 |")
            lines.append("|------|------|----------|")
            for lb_num in sorted(lb_groups.keys(), reverse=True):
                stocks = lb_groups[lb_num]
                names = "/".join([s["name"] for s in stocks[:3]])
                lines.append(f"| **{lb_num}板** | {len(stocks)}只 | {names} |")
            lines.append("")

            # 龙头识别
            max_lb = max(lb_groups.keys())
            top_dragons = lb_groups.get(max_lb, [])
            if top_dragons:
                lines.append(f"**最高标({max_lb}板)**：{', '.join([d['name'] for d in top_dragons])}")
                lines.append(f"> 龙头地位：{'板块龙头确立，有梯队助攻' if len(lb_groups.get(max_lb-1,[])) > 0 else '独立走强，板块效应待验证'}")
            lines.append("")

    # --- 4. 断板/节点切换 ---
    lines.append("### 4. 节点切换检测")
    lines.append("")
    if prev_lb is not None and not prev_lb.empty and lb is not None and not lb.empty:
        if "连板数" in prev_lb.columns and "代码" in prev_lb.columns:
            prev_high = prev_lb[prev_lb["连板数"] >= 3]
            curr_codes = set(lb["代码"].tolist()) if "代码" in lb.columns else set()
            broken = []
            for _, row in prev_high.iterrows():
                code = str(row["代码"])
                if code not in curr_codes:
                    broken.append({
                        "name": str(row.get("名称", "")),
                        "code": code,
                        "lb": int(row["连板数"]),
                    })

            if broken:
                lines.append("⚠️ **高标断板信号(节点切换)：**")
                for b in broken:
                    lines.append(f"- {b['name']}({b['code']}) {b['lb']}板→断板 ← 节点切换触发!")
                lines.append("> 断板日=找新生娇妻的最佳时机。关注今日首板/2板品种。")
            else:
                lines.append("✅ 无高标断板，龙头梯队完整。")
            lines.append("")

    # --- 5. 板块主线 ---
    lines.append("### 5. 板块炒作生命周期")
    lines.append("")
    if lb is not None and not lb.empty and "所属行业" in lb.columns:
        industry_counts = lb["所属行业"].value_counts()
        lines.append("| 主线 | 涨停数 | 阶段 |")
        lines.append("|------|--------|------|")
        for ind, cnt in industry_counts.head(5).items():
            if cnt >= 5:
                stage_bk = "爆发期🔥"
            elif cnt >= 3:
                stage_bk = "加强期"
            else:
                stage_bk = "萌芽期"
            lines.append(f"| **{ind}** | {cnt}只 | {stage_bk} |")
        lines.append("")

    # --- 6. 战法适用性 ---
    lines.append("### 6. 战法适用性评估")
    lines.append("")
    lines.append("| 战法 | 适用度 | 说明 |")
    lines.append("|------|--------|------|")

    # 龙头战法
    if total_zt >= 80 and change_pct > 0:
        lm_score = "★★★★★"
        lm_note = "主升期，直接竞价上龙头"
    elif total_zt >= 40:
        lm_score = "★★★☆☆"
        lm_note = "混沌期，头铁可上但性价比降"
    else:
        lm_score = "★★☆☆☆"
        lm_note = "退潮期，回避高位接力"
    lines.append(f"| 龙头战法 | {lm_score} | {lm_note} |")

    # 神龙战法(分歧转一致)
    lines.append(f"| 神龙战法(分歧转一致) | ★★★★☆ | 断板次日1进2/2进3分歧转一致=最佳窗口 |")

    # 炸板战法
    lines.append(f"| 炸板战法 | ★★★☆☆ | 低位缩量炸板可套利，高位爆量炸板回避 |")

    # 升龙战法
    lines.append(f"| 升龙战法(趋势) | ★★★☆☆ | 电力中军沿均线持有，注意板块退潮风险 |")

    # 潜龙战法
    lines.append(f"| 潜龙战法(低吸) | ★★☆☆☆ | 等龙头回调20/30日线+缩量止跌信号 |")

    lines.append("")
    lines.append(f"> 📌 **核心结论**：{stage}，{position_advice}。重点在**断板节点找新生娇妻**，而非追高位龙头。")
    lines.append("")

    return "\n".join(lines)


def analyze_oute(data: dict) -> str:
    """欧特慢慢龙头战法分析 + 明日预案"""
    lines = []
    lines.append("## 🐉 二、欧特慢慢龙头战法解读")
    lines.append("")

    lb = data.get("limit_up_board")
    idx = data.get("index", {})
    prev_lb = data.get("prev_day_board")

    close = idx.get("close", 0)
    change_pct = idx.get("change_pct", 0)

    # --- 1. 真龙检验 ---
    lines.append("### 1. 真龙四条件检验")
    lines.append("")

    if lb is not None and not lb.empty and "连板数" in lb.columns:
        high_board = lb[lb["连板数"] >= 3].sort_values("连板数", ascending=False)
        if not high_board.empty:
            for _, row in high_board.head(3).iterrows():
                name = row.get("名称", "")
                code = row.get("代码", "")
                lb_num = int(row["连板数"])
                industry = row.get("所属行业", "")

                # 统计同板块涨停数
                same_ind = lb[lb["所属行业"] == industry] if "所属行业" in lb.columns else lb.head(0)
                follow_count = len(same_ind) - 1

                lines.append(f"**{name}({code}) {lb_num}板 — {industry}**")
                lines.append("")
                lines.append(f"| 条件 | 判断 |")
                lines.append(f"|------|------|")
                lines.append(f"| 板块跟随 | {'✅' if follow_count >= 2 else '⚠️'} {follow_count}只跟涨 |")
                lines.append(f"| 小弟助攻 | {'✅' if follow_count >= 1 else '❌'} |")
                lines.append(f"| 主动性/领涨 | {'✅ 连板主动上板' if lb_num >= 3 else '观察中'} |")
                lines.append(f"| 发散性/辨识度 | {'✅ 市场焦点' if lb_num >= 4 else '⚠️ 待加强'} |")
                lines.append("")
                lines.append(f"> 真龙判定：{'✅ 真龙确认，进入高位缠斗阶段' if follow_count >= 2 and lb_num >= 4 else '⚠️ 龙头候选，待进一步确认'}")
                lines.append("")

    # --- 2. 节点体系 ---
    lines.append("### 2. 节点定位与100%溢价判断")
    lines.append("")

    # 判断断板
    has_broken = False
    broken_names = []
    if prev_lb is not None and not prev_lb.empty and lb is not None and not lb.empty:
        if "连板数" in prev_lb.columns and "代码" in prev_lb.columns:
            prev_high_codes = set(prev_lb[prev_lb["连板数"] >= 3]["代码"].tolist())
            curr_codes = set(lb["代码"].tolist())
            broken_codes = prev_high_codes - curr_codes
            if broken_codes:
                has_broken = True
                broken_rows = prev_lb[prev_lb["代码"].isin(broken_codes)]
                broken_names = [f"{r['名称']}({r['代码']}){r['连板数']}板" for _, r in broken_rows.iterrows()]

    if has_broken:
        lines.append(f"🔴 **节点类型：高标断板节点**")
        lines.append(f"> 断板品种：{', '.join(broken_names)}")
        lines.append(f"> 断板日：{data['date']} → **次日=节点2确认日**")
        lines.append(f"> 🎯 **冰转次日确认的节点2，出手前排溢价概率=100%**")
    else:
        lines.append(f"🟡 **节点类型：正常延续**")
        lines.append(f"> 无高标断板，龙头梯队完整延续")
    lines.append("")

    # 三冰监测
    trend = idx.get("trend_5d", [])
    if len(trend) >= 3:
        closes = [d["close"] for d in trend[-3:]]
        down_days = sum(1 for i in range(1, len(closes)) if closes[i] < closes[i-1])
        if down_days >= 2:
            lines.append("🧊 **三冰监测：连续下跌中**")
            lines.append(f"> 若下一交易日继续低开下杀→三冰反弹买点!")
            lines.append("")

    # --- 3. 小娇妻扫描 ---
    lines.append("### 3. 节点小娇妻扫描(首板寻龙)")
    lines.append("")

    if lb is not None and not lb.empty and "连板数" in lb.columns:
        first_boards = lb[lb["连板数"] == 1].copy()
        if not first_boards.empty:
            # 按板块分组，找板块效应最强的首板
            if "所属行业" in first_boards.columns:
                ind_counts = first_boards["所属行业"].value_counts()
                hot_industries = ind_counts[ind_counts >= 3].index.tolist()

                if hot_industries:
                    lines.append(f"**新生娇妻候选(板块效应≥3只首板)：**")
                    lines.append("")
                    lines.append("| 板块 | 首板数 | 娇妻候选 | 评分 |")
                    lines.append("|------|--------|----------|------|")
                    for ind in hot_industries[:5]:
                        ind_stocks = first_boards[first_boards["所属行业"] == ind]
                        candidates = []
                        for _, row in ind_stocks.iterrows():
                            name = row.get("名称", "")
                            turnover = float(row.get("换手率", 0))
                            score = 5
                            if turnover > 5:
                                score += 1  # 换手充分
                            if turnover < 20:
                                score += 1  # 不放量出货
                            candidates.append((name, score))
                        candidates.sort(key=lambda x: -x[1])
                        cand_str = "/".join([f"{n}({s}分)" for n, s in candidates[:2]])
                        lines.append(f"| **{ind}** | {len(ind_stocks)}只 | {cand_str} |")
                    lines.append("")

    # --- 4. Buff评分 ---
    lines.append("### 4. Buff叠加评分(明日重点标的)")
    lines.append("")

    lines.append("""
| Buff维度 | 权重 |
|----------|------|
| 高标断板 | ★★★★★ |
| 板块有高度 | ★★★★ |
| 图形性感 | ★★★★ |
| 价格低 | ★★★ |
| 概念正宗 | ★★★★★ |
| 情绪节奏对 | ★★★★ |
| 大盘配合 | ★★★ |
| 身位唯一 | ★★★★ |
| 竞价超预期 | ★★★★ |

> **Buff≥4→下手，≥7→打满，不在→清仓**
""")

    # --- 5. 五阶段操作律 ---
    lines.append("### 5. 五阶段操作律")
    lines.append("")
    if change_pct < -0.3 and data["sentiment"].get("total_limit_up", 0) < 60:
        current_phase = "**冰点找龙头** ← 当前阶段"
        lines.append(f"> 冰点找龙头 → 回暖上龙头 → 主升满龙头 → 分歧T龙头 → 退潮卖龙头")
        lines.append(f"> {current_phase}")
        lines.append(f"> 策略：不做高位，精选首板/2板中下一个龙头")
    else:
        lines.append(f"> 冰点找龙头 → **回暖上龙头** ← 当前阶段 → 主升满龙头 → 分歧T龙头 → 退潮卖龙头")
    lines.append("")

    # --- 6. 防守七条 ---
    lines.append("### 6. 防守纪律自检")
    lines.append("")
    lines.append("""
```
1. 分歧日不接一字 ✅
2. 不上中位（做最高或最低）✅
3. 不接一致性预期之后 ✅
4. 不是主升不做强上强 ✅
5. 反包不打3板 ✅
6. 没有模式票宁愿空仓 ⚠️
7. 一周最好只出手1-2次 ✅
```
""")

    return "\n".join(lines)


def _rank_dynamic_candidates(data: dict) -> dict:
    """根据当日涨停池生成动态候选股，避免报告使用固定股票名单。

    这里仅使用涨停池中已有的字段，不把候选股伪装成实时买入信号。
    返回值同时供“重点观察池”和“明日买入建议”使用，保证两处口径一致。
    """
    lb = data.get("limit_up_board")
    empty = {"industries": [], "watch": [], "buy": [], "avoid": []}
    if lb is None or getattr(lb, "empty", True):
        return empty

    required = {"名称", "代码", "连板数"}
    if not required.issubset(set(lb.columns)):
        return empty

    df = lb.copy()
    # AkShare 字段可能包含字符串、空值或带百分号的文本，统一成可排序数值。
    for col in ("连板数", "换手率", "成交额"):
        if col in df.columns:
            df[col] = (
                df[col].astype(str).str.replace("%", "", regex=False)
                .str.replace(",", "", regex=False)
            )
            df[col] = __import__("pandas").to_numeric(df[col], errors="coerce").fillna(0)
        else:
            df[col] = 0
    if "所属行业" not in df.columns:
        df["所属行业"] = "未分类"
    df["所属行业"] = df["所属行业"].fillna("未分类").astype(str)
    df["名称"] = df["名称"].fillna("未知").astype(str)
    df["代码"] = df["代码"].fillna("").astype(str).str.replace(".0", "", regex=False)

    industry_counts = df["所属行业"].value_counts()
    top_industries = list(industry_counts.head(3).index)
    df["板块涨停数"] = df["所属行业"].map(industry_counts).fillna(1)
    # 板块效应、连板高度、成交额和适度换手共同构成候选排序。
    turnover_score = df["换手率"].clip(lower=0, upper=30) / 30
    volume_score = df["成交额"].rank(pct=True).fillna(0)
    df["评分"] = (
        df["板块涨停数"].clip(upper=10) * 2
        + df["连板数"].clip(upper=7) * 2
        + turnover_score
        + volume_score
    )

    def row_to_item(row, reason, action):
        code = str(row["代码"]).zfill(6)
        return {
            "name": row["名称"],
            "code": code,
            "industry": row["所属行业"],
            "boards": int(row["连板数"]),
            "turnover": float(row["换手率"]),
            "amount": float(row["成交额"]),
            "sector_count": int(row["板块涨停数"]),
            "reason": reason,
            "action": action,
        }

    watch = []
    buy = []
    for industry in top_industries:
        sector = df[df["所属行业"] == industry].sort_values(
            ["评分", "连板数", "成交额"], ascending=False
        )
        # 每个强势板块最多选两只：一只高度票、一只低位首板/二板。
        selected = []
        high = sector.iloc[0] if len(sector) else None
        low = sector[sector["连板数"].isin([1, 2])].iloc[0] if not sector[
            sector["连板数"].isin([1, 2])
        ].empty else None
        for row in (high, low):
            if row is not None and str(row["代码"]) not in [x["code"] for x in selected]:
                selected.append(row_to_item(
                    row,
                    f"{industry}涨停{int(row['板块涨停数'])}只，{int(row['连板数'])}板",
                    "竞价/分歧转一致确认",
                ))
        watch.extend(selected)
        # 买入建议优先放低位换手票，避免把所有最高标都当成买点。
        for item in selected:
            if item["boards"] in (1, 2) and item["turnover"] <= 65:
                buy.append(item)

    # 候选不足时，从全市场补充评分最高的低位票；不再写死股票名称。
    if len(buy) < 3:
        low_df = df[df["连板数"].isin([1, 2]) & (df["换手率"] <= 65)].sort_values(
            "评分", ascending=False
        )
        for _, row in low_df.iterrows():
            item = row_to_item(
                row,
                f"{row['所属行业']}板块涨停{int(row['板块涨停数'])}只",
                "竞价超预期且上板确认",
            )
            if item["code"] not in [x["code"] for x in buy]:
                buy.append(item)
            if len(buy) >= 5:
                break

    # 明确列出不适合追涨的高换手/高位标的，增强报告解释性。
    avoid_df = df[(df["连板数"] >= 3) & (df["换手率"] > 65)].sort_values(
        "换手率", ascending=False
    )
    avoid = [
        row_to_item(row, "高位且换手率超过65%", "回避追高")
        for _, row in avoid_df.head(3).iterrows()
    ]
    return {
        "industries": top_industries,
        "watch": watch[:8],
        "buy": buy[:5],
        "avoid": avoid,
    }


def _candidate_line(item):
    """将动态候选转换为简洁的报告文本。"""
    return (
        f"{item['name']}({item['code']}) | {item['industry']} | "
        f"{item['boards']}板 | 板块{item['sector_count']}只 | "
        f"换手{item['turnover']:.1f}%"
    )


def generate_tomorrow_plan(data: dict) -> str:
    """生成明日操作预案"""
    lines = []
    lines.append("## 📋 三、明日操作预案")
    lines.append("")

    lb = data.get("limit_up_board")
    idx = data.get("index", {})

    # 日期
    tomorrow = (datetime.strptime(data["date"], "%Y%m%d") + timedelta(days=3)).strftime("%m/%d")  # rough
    # Actually let's just use next trading day
    date_obj = datetime.strptime(data["date"], "%Y%m%d")
    next_day = date_obj + timedelta(days=1)
    if next_day.weekday() == 5:
        next_day = next_day + timedelta(days=2)
    elif next_day.weekday() == 6:
        next_day = next_day + timedelta(days=1)

    lines.append(f"**{next_day.strftime('%Y年%m月%d日')}(周{['一','二','三','四','五','六','日'][next_day.weekday()]}) 预案**")
    lines.append("")

    # --- 条线预案 ---
    lines.append("### 盘前条线预案")
    lines.append("")

    if lb is not None and not lb.empty and "所属行业" in lb.columns:
        ind_counts = lb["所属行业"].value_counts()

        for rank, (ind, cnt) in enumerate(ind_counts.head(3).items()):
            ind_stocks = lb[lb["所属行业"] == ind]
            line_label = ["最强", "次强", "观察"][rank]

            # 找龙一(最高连板)
            if "连板数" in ind_stocks.columns:
                dragon = ind_stocks.sort_values("连板数", ascending=False).iloc[0]
                dragon_name = dragon["名称"]
                dragon_lb = int(dragon["连板数"])
            else:
                dragon_name = ind_stocks.iloc[0]["名称"]
                dragon_lb = "?"

            # 找容量
            if "成交额" in ind_stocks.columns:
                capacity = ind_stocks.sort_values("成交额", ascending=False).iloc[0]
                cap_name = capacity["名称"]
            else:
                cap_name = dragon_name

            # 找补涨候选(首板)
            if "连板数" in ind_stocks.columns:
                first_boards = ind_stocks[ind_stocks["连板数"] == 1]
                budoux = "/".join(first_boards["名称"].head(3).tolist()) if len(first_boards) > 0 else "无"
            else:
                budoux = "待定"

            lines.append(f"**条线{rank+1}({line_label})：{ind}**")
            lines.append(f"```")
            lines.append(f"龙一: {dragon_name}({dragon_lb}板)")
            lines.append(f"容量核心: {cap_name}")
            lines.append(f"补涨候选: {budoux}")
            lines.append(f"```")
            lines.append("")

    candidates = _rank_dynamic_candidates(data)

    # --- 具体操作计划 ---
    lines.append("### 操作计划")
    lines.append("")

    total_zt = data["sentiment"].get("total_limit_up", 0)
    change_pct = idx.get("change_pct", 0)

    if change_pct < -0.5 and total_zt < 60:
        plan = "**防守为主，试错为辅**"
        detail = [
            "1. 竞价9:20-9:25观察下方候选是否出现弱转强",
            "2. 出现竞价爆量抢筹→只做1进2确认板(仓位30%)",
            "3. 无模式票→空仓等待，不见兔子不撒鹰",
            "4. 高位龙头只做T不做新开仓",
        ]
    else:
        plan = "**积极参与**"
        detail = [
            "1. 竞价确认最强方向→第一时间跟随",
            "2. 1进2确认→打板加仓(仓位可至60%)",
            "3. 总龙分歧→均线低吸做T",
            "4. 跟随真龙，不碰杂毛",
        ]

    lines.append(f"> {plan}")
    lines.append("")
    for d in detail:
        lines.append(d)
    lines.append("")

    # --- 具体标的 ---
    lines.append("### 重点观察池")
    lines.append("")
    lines.append("| 优先级 | 标的 | 逻辑 | 买点 |")
    lines.append("|--------|------|------|------|")
    for rank, item in enumerate(candidates["watch"][:3], 1):
        medal = ["🥇", "🥈", "🥉"][rank - 1]
        lines.append(
            f"| {medal} | {_candidate_line(item)} | {item['reason']} | {item['action']} |"
        )
    if not candidates["watch"]:
        lines.append("| - | 暂无符合条件的动态候选 | 当日涨停池数据不足或字段不完整 | 空仓观察 |")
    lines.append("")

    # --- 风控 ---
    lines.append("### 风控红线")
    lines.append("")
    lines.append("| 规则 | 标准 |")
    lines.append("|------|------|")
    lines.append("| 止损 | -5%无条件 |")
    lines.append("| 单票上限 | 20% |")
    lines.append("| 3连亏 | 当日停止交易 |")
    lines.append("| 永不满仓 | 铁律 |")
    lines.append("")

    return "\n".join(lines)


def generate_buy_recommendation(data: dict) -> str:
    """生成明日买入建议"""
    lines = []
    lines.append("## 💰 四、明日买入建议")
    lines.append("")

    candidates = _rank_dynamic_candidates(data)

    # 基于当日涨停池动态生成推荐，不再使用固定股票名单。
    lines.append("### 🥇 第一优先级：1进2确认板(新生娇妻)")
    lines.append("")
    lines.append("| 排序 | 标的 | 代码 | 逻辑 | 买点策略 |")
    lines.append("|------|------|------|------|----------|")
    for rank, item in enumerate(candidates["buy"], 1):
        lines.append(
            f"| **{rank}** | **{item['name']}** | {item['code']} | "
            f"{item['reason']} | {item['action']} |"
        )
    if not candidates["buy"]:
        lines.append("| - | 暂无符合条件的动态候选 | 数据不足/没有合适的1-2板标的 | 不交易 |")
    lines.append("")

    lines.append("### 🥈 第二优先级：总龙缠斗(防守配置)")
    lines.append("")
    lines.append("| 标的 | 代码 | 策略 | 条件 |")
    lines.append("|------|------|------|------|")
    for item in candidates["watch"]:
        if item["boards"] >= 3 and item["turnover"] <= 65:
            lines.append(
                f"| {item['name']} | {item['code']} | 分歧低吸/均线做T | "
                f"{item['industry']}板块未退潮，换手{item['turnover']:.1f}% |"
            )
    if not any(item["boards"] >= 3 and item["turnover"] <= 65 for item in candidates["watch"]):
        lines.append("| 暂无 | - | 不开高位新仓 | 等待动态候选出现 |")
    lines.append("")

    lines.append("### ⛔ 明确回避")
    lines.append("")
    lines.append("- 连续一字板品种(量化堵门)")
    lines.append("- 高位断板品种(不接飞刀)")
    lines.append("- 无板块效应的独立走强(穿越十穿九死)")
    lines.append("- 换手率>65%的高位票(死亡分界线)")
    for item in candidates["avoid"]:
        lines.append(f"- {item['name']}({item['code']})：{item['reason']}")
    lines.append("")

    lines.append("> ⚠️ **免责声明**：以上分析仅供学习交流，不构成投资建议。股市有风险，投资需谨慎。")
    lines.append("")

    return "\n".join(lines)


def build_report(data: dict) -> str:
    """组装完整报告"""
    parts = []

    # 头部
    date_str = data["date"]
    date_fmt = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}"
    idx = data.get("index", {})

    parts.append(f"# 📊 A股超短双体系日报 — {date_fmt}")
    parts.append("")
    parts.append(f"> 上证 **{idx.get('close', 'N/A')}** | "
                f"涨跌 {idx.get('change_pct', 0):+.2f}% | "
                f"量能 {idx.get('volume_wan', 0):.0f}万手 | "
                f"涨停 **{data['sentiment'].get('total_limit_up', 0)}**只")
    parts.append(f"> 生成时间：{data['timestamp']}")
    parts.append("")
    parts.append("---")
    parts.append("")

    # 淘股吧分析
    parts.append(analyze_taoguba(data))
    parts.append("---")
    parts.append("")

    # 欧特龙分析
    parts.append(analyze_oute(data))
    parts.append("---")
    parts.append("")

    # 明日预案
    parts.append(generate_tomorrow_plan(data))
    parts.append("---")
    parts.append("")

    # 买入建议
    parts.append(generate_buy_recommendation(data))
    parts.append("---")
    parts.append("")

    # 尾部
    parts.append("🤖 本报告由 A股超短双体系分析引擎 自动生成")
    parts.append(f"📅 {data['timestamp']} | 淘股吧超短 + 欧特慢慢龙头战法")

    return "\n".join(parts)


def push_to_wechat(content: str, webhook_url: str = WEBHOOK_URL) -> bool:
    """推送到企业微信机器人"""
    # 企业微信markdown消息限制4096字节(UTF-8)，中文每字3字节
    MAX_BYTES = 3800  # 留余量

    # 按 --- 分隔符拆分(每个section是独立分析模块)
    raw_sections = content.split("\n---\n")

    sections = []
    current = ""
    for raw in raw_sections:
        test = current + ("\n---\n" if current else "") + raw
        if len(test.encode("utf-8")) > MAX_BYTES and current:
            sections.append(current.strip())
            current = raw
        else:
            current = test
    if current.strip():
        sections.append(current.strip())

    success = True
    for i, section in enumerate(sections):
        byte_len = len(section.encode("utf-8"))
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": section
            }
        }
        try:
            resp = requests.post(
                webhook_url,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            result = resp.json()
            if result.get("errcode") != 0:
                print(f"  [ERROR] Part {i+1} push failed: {result}")
                success = False
            else:
                print(f"  [OK] Part {i+1} pushed ({byte_len} bytes)")
        except Exception as e:
            print(f"  [ERROR] Part {i+1} exception: {e}")
            success = False
        # 段间间隔，避免频率限制
        if i < len(sections) - 1:
            time.sleep(1)

    return success


def push_to_serverchan(content: str, sendkey: str = None) -> bool:
    """Push to Server酱 (WeChat service account)"""
    if sendkey is None:
        sendkey = SERVERCHAN_KEY
    if not sendkey:
        print("  [WARN] SERVERCHAN_KEY not set, skipped Server酱")
        return False

    title = extract_title(content)
    if len(title) > 32:
        title = title[:32]

    url = "https://sctapi.ftqq.com/{}.send".format(sendkey)

    MAX_DESP = 30000
    desp_body = content
    if len(desp_body.encode("utf-8")) > MAX_DESP:
        desp_body = content[:25000] + "\n\n> Report truncated, see local file for full version"

    try:
        resp = requests.post(url, data={"title": title, "desp": desp_body}, timeout=30)
        result = resp.json()
        if result.get("code") == 0:
            print("  [OK] Server酱 sent: {}".format(title))
            return True
        else:
            print("  [ERROR] Server酱 failed: {}".format(result))
            return False
    except Exception as e:
        print("  [ERROR] Server酱 exception: {}".format(e))
        return False


def extract_title(content: str) -> str:
    """Extract a short push title from the report"""
    for line in content.split("\n"):
        if line.startswith("# ") and "双体系" in line:
            return line.replace("# ", "").strip()
    for line in content.split("\n"):
        if "上证" in line and "涨停" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                return "A股双体系 {}".format(parts[1].strip()[:20])
    return "A股超短双体系日报"


def main():
    """Main flow"""
    parser = argparse.ArgumentParser(description="A股超短双体系分析引擎")
    parser.add_argument("--no-push", action="store_true",
                       help="Disable push, save report only")
    parser.add_argument("--push", type=str, default=None,
                       choices=["wechat", "serverchan", "all"],
                       help="Push method: wechat, serverchan, all")
    parser.add_argument("--date", type=str, default=None,
                       help="Trading day (YYYYMMDD), auto-detect if omitted")
    parser.add_argument("--webhook", type=str, default=None,
                       help="WeChat Work webhook URL override")
    args = parser.parse_args()

    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except (AttributeError, ValueError):
        pass

    print("=" * 60)
    print("A股超短双体系分析引擎 V1.2")
    print("Started: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    if args.no_push:
        print("Push: disabled (--no-push)")
    print("=" * 60)

    print("")
    print("[1/5] Determining trading day...")
    trade_date = get_latest_trading_day(args.date)
    print("  Date: {}".format(trade_date))

    print("")
    print("[2/5] Fetching market data...")
    try:
        data = fetch_market_data(trade_date)
        print("  Limit up: {} stocks".format(data['sentiment'].get('total_limit_up', 'N/A')))
        print("  Strong pool: {} stocks".format(data['sentiment'].get('total_strong', 'N/A')))
        print("  Prev limit up: {} stocks".format(data['sentiment'].get('prev_total_limit_up', 'N/A')))
    except Exception as e:
        print("  [ERROR] Data fetch failed: {}".format(e))
        traceback.print_exc()
        return

    print("")
    print("[3/5] Generating dual-system analysis...")
    try:
        report = build_report(data)
        print("  Report: {} chars".format(len(report)))
    except Exception as e:
        print("  [ERROR] Report generation failed: {}".format(e))
        traceback.print_exc()
        return

    print("")
    print("[4/5] Saving local report...")
    report_dir = os.path.join(PROJECT_DIR, "reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "daily_report_{}.md".format(trade_date))
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print("  Saved: {}".format(report_path))

    # Step 5: Push
    should_push = not args.no_push
    push_method = args.push or PUSH_METHOD

    if should_push:
        print("")
        print("[5/5] Pushing...")

        if push_method in ("wechat", "all"):
            print("  -> WeChat Work...")
            push_to_wechat(report, args.webhook or WEBHOOK_URL)

        if push_method in ("serverchan", "all"):
            print("  -> ServerChan...")
            push_to_serverchan(report)

        if push_method not in ("wechat", "serverchan", "all"):
            print("  [WARN] Unknown push method: {}, skipped".format(push_method))
    else:
        print("")
        print("[5/5] (push skipped)")

    print("")
    print("=" * 60)
    print("Done!")
    print("=" * 60)

    print("")
    print("Summary:")
    idx = data.get("index", {})
    lb = data.get("limit_up_board")
    max_lb = "N/A"
    if lb is not None and not lb.empty and "连板数" in lb.columns:
        max_lb = int(lb["连板数"].max())
    print("  SH Index: {} ({:+.2f}%)".format(idx.get('close', 'N/A'), idx.get('change_pct', 0)))
    print("  Limit up: {} stocks".format(data['sentiment'].get('total_limit_up', 0)))
    print("  Max board: {} boards".format(max_lb))
    print("  Report: {}".format(report_path))

if __name__ == "__main__":
    main()
