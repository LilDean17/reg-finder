#!/usr/bin/env python3
"""
注册可行性筛选工具 - 入口
用法: python main.py <urls.txt>
"""
import asyncio
import sys
import time
import json
import csv
from pathlib import Path
from typing import Optional, Dict, List

import colorama
from colorama import Fore, Style
colorama.init()

from core.config import Config
from core.probe import Prober, ProbeResult
from core.score import Scorer, ScoredResult
from core.output import OutputFormatter


class RequestCache:
    """请求缓存：同一 URL 只请求一次"""
    def __init__(self):
        self.cache: Dict[str, ProbeResult] = {}

    def get(self, url: str) -> Optional[ProbeResult]:
        return self.cache.get(url)

    def set(self, url: str, result: ProbeResult):
        self.cache[url] = result


class Scanner:
    def __init__(self, config: Config):
        self.config = config
        self.prober = Prober(
            concurrency=config.probe.concurrency,
            timeout=config.probe.timeout,
            follow_redirects=config.probe.follow_redirects,
            per_domain_limit=10,
        )
        self.scorer = Scorer(config.profiles, config.exclusions, config.scoring)
        self.formatter = OutputFormatter(config.output)
        self.cache = RequestCache()

        # 日志文件：实时写入，可通过 tail -f 查看
        self._log = None
        self._log_path = Path("output/scan.log")

    def _p(self, msg: str = ""):
        """同时输出到终端和日志文件"""
        try:
            print(msg, flush=True)
        except Exception:
            pass
        if self._log:
            try:
                self._log.write(msg + "\n")
                self._log.flush()
            except Exception:
                pass

    def run(self, urls_file: str) -> list:
        """同步入口"""
        self._log_path.parent.mkdir(exist_ok=True)
        self._log = open(self._log_path, "w", encoding="utf-8", buffering=1)

        scored_path = Path("output/04_scored.json")

        if scored_path.exists():
            self._p("[*] 发现已完成的评分结果，直接加载")
            data = json.loads(scored_path.read_text(encoding="utf-8"))
            results = [self._deserialize_scored(r) for r in data]
            self._log.close()
            return results

        urls = self._load_urls(urls_file)

        url_blacklist = self.config.blacklist.url_blacklist
        if url_blacklist:
            passed, blocked = self._filter_url_blacklist(urls, url_blacklist)
        else:
            passed, blocked = urls, []

        # 初始化增量输出文件（在扫描前打开，以便写入黑名单条目）
        self._init_incremental_output()

        # 将 URL 黑名单条目写入输出文件，并逐条终端输出
        if blocked:
            self._p(f"[*] URL 黑名单过滤: {len(blocked)} 个 URL 被跳过")
            for bl_url in blocked:
                # 找出命中的关键字
                url_lower = bl_url.lower()
                matched_kw = None
                for kw in [str(k) for k in url_blacklist]:
                    if kw.lower() in url_lower:
                        matched_kw = kw
                        break
                self._p(f"  {Fore.CYAN}[黑名单] {bl_url}  →  {matched_kw}{Style.RESET_ALL}")
                r = self._make_blocked_result(bl_url, bl_url, 0, "", f"URL黑名单过滤[{matched_kw}]")
                self._write_csv_row(r)
                self._write_jsonl_row(r)

        if not passed:
            self._p("[!] 所有 URL 都被黑名单过滤，无需扫描")
            self._csv_file.close()
            self._jsonl_file.close()
            self._log.close()
            return []

        self._p(f"[*] 加载 {len(passed)} 个 URL（原始 {len(passed) + len(blocked)} 个）")

        start_time = time.time()
        results, content_blocked = asyncio.run(self._run_streaming(passed))
        elapsed = time.time() - start_time

        total_blocked = len(blocked) + content_blocked
        if total_blocked > 0:
            self._p(f"\n[*] 黑名单共过滤: URL层 {len(blocked)} + 内容层 {content_blocked} = {total_blocked} 个")

        self._log.close()
        return results

    async def _run_streaming(self, urls: list) -> tuple:
        """流式处理：每个 URL 探测完立刻输出"""
        concurrency = self.config.probe.concurrency
        semaphore = asyncio.Semaphore(concurrency)
        lock = asyncio.Lock()

        results: List[ScoredResult] = []
        content_blocked_count = 0
        processed = 0
        total = len(urls)
        content_blacklist = self.config.blacklist.content_blacklist
        seen_hashes: set = set()

        high_value_count = 0
        above_threshold_count = 0
        score_sum = 0
        score_count = 0
        error_count = 0
        start_time = time.time()

        self._p(f"\n{'=' * 60}")
        self._p(f"  开始扫描  共 {total} 个 URL | 并发 {concurrency} | 超时 {self.config.probe.timeout}s")
        self._p(f"{'=' * 60}\n")

        async def process_one(url: str, index: int):
            async with semaphore:  # 限制同时运行的任务数
                nonlocal processed, content_blocked_count, error_count
                nonlocal high_value_count, above_threshold_count, score_sum, score_count
                nonlocal seen_hashes

                # 探测
                probe_result = await self.prober.probe(url)

            # 内容去重 — 相同内容只保留第一个
            if probe_result.content_hash:
                if probe_result.content_hash in seen_hashes:
                    async with lock:
                        processed += 1
                        pct = processed * 100 // total
                    self._p(f"  [{processed}/{total}]({pct}%) {url}  →  {Fore.CYAN}内容重复({probe_result.content_hash[:8]}...){Style.RESET_ALL}")
                    return None
                seen_hashes.add(probe_result.content_hash)

            # 内容黑名单检查 — 命中也输出记录，并显示命中的关键字
            if content_blacklist and probe_result.status_code > 0:
                haystack = (probe_result.body_text + " " + probe_result.title).lower()
                blacklist_str = [str(kw) for kw in content_blacklist]
                matched_kw = None
                for kw in blacklist_str:
                    if kw.lower() in haystack:
                        matched_kw = kw
                        break
                if matched_kw:
                    async with lock:
                        content_blocked_count += 1
                        processed += 1
                    blocked = self._make_blocked_result(
                        url, probe_result.final_url, probe_result.status_code,
                        probe_result.title, f"内容黑名单过滤[{matched_kw}]"
                    )
                    self._print_result_line(blocked, processed, total)
                    self._write_csv_row(blocked)
                    self._csv_file.flush()
                    self._write_jsonl_row(blocked)
                    self._jsonl_file.flush()
                    return None

            # CDN/WAF 挑战页 — 输出记录并跳过评分
            if probe_result.error and "CDN" in probe_result.error:
                async with lock:
                    error_count += 1
                    processed += 1
                cdn_result = self._make_blocked_result(
                    url, probe_result.final_url, probe_result.status_code,
                    probe_result.title, probe_result.error
                )
                self._print_result_line(cdn_result, processed, total)
                self._write_csv_row(cdn_result)
                self._csv_file.flush()
                self._write_jsonl_row(cdn_result)
                self._jsonl_file.flush()
                return None

            # 请求失败（timeout / 网络错误等）— 也输出记录
            if probe_result.status_code == 0:
                async with lock:
                    error_count += 1
                    processed += 1
                err_msg = probe_result.error or "请求失败"
                err_result = self._make_blocked_result(
                    url, url, 0, "", f"请求失败[{err_msg}]"
                )
                self._print_result_line(err_result, processed, total)
                self._write_csv_row(err_result)
                self._csv_file.flush()
                self._write_jsonl_row(err_result)
                self._jsonl_file.flush()
                return None

            # 评分（ scorer 内部同时完成分类）
            scored = self.scorer.score(probe_result)

            async with lock:
                processed += 1
                score_sum += scored.score
                score_count += 1

                if scored.score >= self.config.output.auto_highlight:
                    high_value_count += 1
                if scored.score >= self.config.scoring.threshold:
                    above_threshold_count += 1

                results.append(scored)
                self._print_result_line(scored, processed, total)

                # 增量写入 CSV
                self._write_csv_row(scored)
                self._csv_file.flush()

                # 增量写入 JSONL
                self._write_jsonl_row(scored)
                self._jsonl_file.flush()

            return scored

        tasks = [process_one(url, i + 1) for i, url in enumerate(urls)]
        await asyncio.gather(*tasks)

        if self._csv_file:
            self._csv_file.close()
        if self._jsonl_file:
            self._jsonl_file.close()

        return results, content_blocked_count

    def _init_incremental_output(self):
        Path("output").mkdir(exist_ok=True)

        csv_path = Path("output/results.csv")
        self._csv_file = open(csv_path, "w", newline="", encoding="utf-8-sig")
        self._csv_writer = csv.writer(self._csv_file)
        self._csv_writer.writerow([
            "得分", "URL", "最终URL", "状态码", "标题",
            "业务类型", "SPA", "已渲染", "渲染状态", "注册表单", "推荐等级",
            "命中规则明细", "错误"
        ])
        self._csv_file.flush()

        jsonl_path = Path("output/results.jsonl")
        self._jsonl_file = open(jsonl_path, "w", encoding="utf-8")

    def _print_result_line(self, scored: ScoredResult, index: int, total: int):
        """单行输出一个 URL 的结果"""
        score_str = self._color_score(scored.score)
        biz_str = ",".join(scored.business_types) if scored.business_types else "未分类"
        url_str = scored.final_url if scored.final_url else scored.url
        pct = index * 100 // total
        idx_str = f"[{index}/{total}]({pct}%)"

        render_status = "已渲染" if scored.rendered else ("未渲染" if scored.is_spa else "-")

        # 拦截/错误记录：青色单行输出
        if scored.error:
            line = f"  {idx_str} {scored.score} │ {url_str} │ {Fore.CYAN}{scored.error}{Style.RESET_ALL}"
            self._p(line)
            return

        # 正常记录
        colored_first = f"  {idx_str} {score_str} │ {url_str} │ {biz_str} │ {render_status}"
        self._p(colored_first)

        # 详情每项一行
        items = []
        for d in scored.breakdown:
            if d.weight != 0:
                w = f"+{d.weight}" if d.weight > 0 else f"{d.weight}"
                short = self._short_profile(d.profile)
                items.append(f"{w}[{short}]{d.indicator}")

        if items:
            indent = "                         "
            for item in items:
                self._p(f"{indent}{item}")

    def _write_csv_row(self, scored: ScoredResult):
        breakdown_str = "; ".join(
            f"{'+' if d.weight > 0 else ''}{d.weight} [{d.profile}] {d.indicator}"
            for d in scored.breakdown
        )
        self._csv_writer.writerow([
            scored.score,
            scored.url,
            scored.final_url,
            scored.status_code,
            scored.title[:80] if scored.title else "",
            ",".join(scored.business_types) if scored.business_types else "",
            "是" if scored.is_spa else "否",
            "是" if scored.rendered else "否",
            "已渲染" if scored.rendered else ("未渲染" if scored.is_spa else "-"),
            "是" if scored.has_register_form else "否",
            scored.recommendation,
            breakdown_str,
            scored.error,
        ])

    def _write_jsonl_row(self, scored: ScoredResult):
        """写入一条 JSONL 记录"""
        self._jsonl_file.write(
            json.dumps(self._serialize_scored(scored), ensure_ascii=False) + "\n"
        )
        self._jsonl_file.flush()

    def _load_urls(self, urls_file: str) -> list:
        lines = Path(urls_file).read_text(encoding="utf-8").splitlines()
        urls = []
        seen = set()
        for line in lines:
            url = line.strip()
            if url and not url.startswith("#"):
                if url not in seen:
                    urls.append(url)
                    seen.add(url)
        return urls

    @staticmethod
    def _filter_url_blacklist(urls: list, blacklist: list) -> tuple:
        blacklist_str = [str(kw) for kw in blacklist]
        passed = []
        blocked = []
        for url in urls:
            url_lower = url.lower()
            if any(kw.lower() in url_lower for kw in blacklist_str):
                blocked.append(url)
            else:
                passed.append(url)
        return passed, blocked

    def _save_intermediate(self, results: list):
        Path("output").mkdir(exist_ok=True)
        data = [self._serialize_scored(r) for r in results]
        Path("output/04_scored.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def _serialize_scored(self, r: ScoredResult) -> dict:
        return {
            "url": r.url,
            "final_url": r.final_url,
            "status_code": r.status_code,
            "title": r.title,
            "score": r.score,
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

    def _deserialize_scored(self, data: dict) -> ScoredResult:
        from core.score import ScoreDetail
        breakdown = [
            ScoreDetail(
                profile=d["profile"],
                category=d["category"],
                rule_type=d["rule_type"],
                indicator=d["indicator"],
                weight=d["weight"],
            )
            for d in data.get("breakdown", [])
        ]
        return ScoredResult(
            url=data["url"],
            final_url=data["final_url"],
            status_code=data["status_code"],
            title=data.get("title", ""),
            score=data.get("score", 0),
            business_types=data.get("business_types", []),
            is_spa=data.get("is_spa", False),
            rendered=data.get("rendered", False),
            has_register_form=data.get("has_register_form", False),
            recommendation=data.get("recommendation", ""),
            breakdown=breakdown,
            error=data.get("error", ""),
        )

    @staticmethod
    def _short_profile(name: str) -> str:
        """缩写 profile 名称用于详情列显示"""
        mapping = {
            "通用业务检测": "通用",
            "电商业务检测": "电商",
            "投稿业务检测": "投稿",
            "供应商业务检测": "供应商",
            "图书馆系统检测": "图书馆",
            "统一登录检测": "统一登录",
            "CMS系统检测": "CMS",
            "后台站点检测": "后台",
            "校园邮箱检测": "邮箱",
            "门户站检测": "门户",
            "排除": "排除",
        }
        return mapping.get(name, name[:2])

    @staticmethod
    def _make_blocked_result(url: str, final_url: str, status_code: int,
                             title: str, error_msg: str) -> ScoredResult:
        """为超时、黑名单等非评分结果创建统一的 ScoredResult"""
        return ScoredResult(
            url=url,
            final_url=final_url,
            status_code=status_code,
            title=title[:80] if title else "",
            score=0,
            business_types=[],
            is_spa=False,
            rendered=False,
            has_register_form=False,
            recommendation="blocked" if "黑名单" in error_msg else "error",
            error=error_msg,
        )

    @staticmethod
    def _color_score(score: int) -> str:
        if score >= 80:
            return f"{Fore.RED}{score}{Style.RESET_ALL}"
        elif score >= 60:
            return f"{Fore.YELLOW}{score}{Style.RESET_ALL}"
        else:
            return f"{Fore.GREEN}{score}{Style.RESET_ALL}"


def main():
    if len(sys.argv) < 2:
        print("用法: python main.py <urls.txt>", flush=True)
        print("  urls.txt 每行一个 URL", flush=True)
        sys.exit(1)

    urls_file = sys.argv[1]
    if not Path(urls_file).exists():
        print(f"[!] 文件不存在: {urls_file}", flush=True)
        sys.exit(1)

    config = Config.load("config.yaml")
    scanner = Scanner(config)
    results = scanner.run(urls_file)

    sys.exit(0)


if __name__ == "__main__":
    main()
