#!/usr/bin/env python3
"""输出模块：终端彩色表格 + JSON + CSV"""
import json
import csv
import os
from dataclasses import asdict
from pathlib import Path
from datetime import datetime

import colorama
from colorama import Fore, Style
colorama.init()

from core.config import OutputConfig


class OutputFormatter:
    def __init__(self, output_config: OutputConfig):
        self.config = output_config
        Path("output").mkdir(exist_ok=True)

    def print(self, results: list, total_urls: int, elapsed: float):
        """根据配置的输出格式输出结果"""
        if "terminal" in self.config.formats:
            self._print_terminal(results, total_urls, elapsed)

        if "json" in self.config.formats:
            self._save_json(results)

        if "csv" in self.config.formats:
            self._save_csv(results)

    def _print_terminal(self, results: list, total_urls: int, elapsed: float):
        """终端彩色表格输出"""
        if not results:
            print(f"\n[!] 未找到高于 {self.config.min_score} 分的结果")
            return

        # 计算列宽
        url_width = max(len(r.final_url) for r in results)
        url_width = min(url_width, 55)

        divider = "─" * (8 + url_width + 10 + 14 + 10)

        print(f"\n{'═' * len(divider)}")
        print(f"  注册可行性筛选结果  (共 {len(results)} 个 / 扫描 {total_urls} 个 / 耗时 {elapsed:.1f}s)")
        print(f"{'═' * len(divider)}")

        header = f"{'得分':<6} {'URL':<{url_width}} {'状态':<6} {'业务类型':<14} {'渲染':<5} {'注册表单'}"
        print(header)
        print(divider)

        for r in results:
            score_str = self._color_score(r.score)
            url_short = r.final_url[:url_width]
            biz = ",".join(r.business_types) if r.business_types else "未分类"
            biz = biz[:12]
            rendered = "✓" if r.rendered else ""
            form = "✓" if r.has_register_form else ""

            print(
                f"{score_str:<6} {url_short:<{url_width}} "
                f"{r.status_code:<6} {biz:<14} {rendered:<5} {form}"
            )

            # 输出每条命中规则
            for d in r.breakdown:
                weight_str = f"+{d.weight}" if d.weight > 0 else f"{d.weight}"
                print(f"       │  {weight_str:>4}  [{d.profile}] {d.indicator}")

            print(divider)

    def _color_score(self, score: int) -> str:
        """分数着色"""
        if score >= 80:
            return f"{Fore.RED}{score}{Style.RESET_ALL}"    # 红色：高价值
        elif score >= 60:
            return f"{Fore.YELLOW}{score}{Style.RESET_ALL}"  # 黄色：过线
        else:
            return f"{Fore.GREEN}{score}{Style.RESET_ALL}"   # 绿色：低分

    def _save_json(self, results: list):
        path = Path("output/results.json")
        data = [self._serialize(r) for r in results]
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"\n[*] JSON 已保存: {path}")

    def _save_csv(self, results: list):
        path = Path("output/results.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "得分", "URL", "最终URL", "状态码", "标题",
                "业务类型", "SPA", "已渲染", "注册表单", "推荐等级",
                "命中规则明细", "错误"
            ])
            for r in results:
                breakdown_str = "; ".join(
                    f"{'+' if d.weight > 0 else ''}{d.weight} [{d.profile}] {d.indicator}"
                    for d in r.breakdown
                )
                writer.writerow([
                    r.score,
                    r.url,
                    r.final_url,
                    r.status_code,
                    r.title[:80] if r.title else "",
                    ",".join(r.business_types) if r.business_types else "",
                    "是" if r.is_spa else "否",
                    "是" if r.rendered else "否",
                    "是" if r.has_register_form else "否",
                    r.recommendation,
                    breakdown_str,
                    r.error,
                ])
        print(f"[*] CSV 已保存: {path}")

    def _serialize(self, r) -> dict:
        return {
            "score": r.score,
            "url": r.url,
            "final_url": r.final_url,
            "status_code": r.status_code,
            "title": r.title,
            "business_types": r.business_types,
            "is_spa": r.is_spa,
            "rendered": r.rendered,
            "has_register_form": r.has_register_form,
            "recommendation": r.recommendation,
            "breakdown": [
                {
                    "profile": d.profile,
                    "category": d.category,
                    "rule_type": d.rule_type,
                    "indicator": d.indicator,
                    "weight": d.weight,
                }
                for d in r.breakdown
            ],
            "error": r.error,
        }
