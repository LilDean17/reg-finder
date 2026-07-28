#!/usr/bin/env python3
"""快速测试 v4：又一批 10 个不同类型站点"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.config import Config
from core.probe import Prober
from core.classifier import BusinessClassifier
from core.score import Scorer

URLS = [
    "https://pilab.tju.edu.cn",
    "https://adminbpm.sxdzkj.edu.cn",
    "https://wel-back.sxit.edu.cn",
    "https://oa.jmsu.edu.cn:8888",
    "https://yqyy.jmsu.edu.cn:8888",
    "https://psy-space.ecnu.edu.cn",
    "https://api.alumni.suda.edu.cn",
    "https://zhjtpt.whu.edu.cn",
    "https://animaltk.whu.edu.cn",
    "https://erkmanager.cqnu.edu.cn",
    "https://sunservice.hunau.edu.cn",
    "https://yyzhyl.whut.edu.cn",
    "https://pxbbm.nenu.edu.cn",
    "https://whxl.fudan.edu.cn",
    "https://szhx.sus.edu.cn",
    "http://xsg.njucm.edu.cn:9001",
]


async def main():
    config = Config.load("config.yaml")
    prober = Prober(
        concurrency=config.probe.concurrency,
        timeout=config.probe.timeout,
        follow_redirects=config.probe.follow_redirects,
        per_domain_limit=10,
    )
    classifier = BusinessClassifier()
    scorer = Scorer(config.profiles, config.exclusions, config.scoring)

    print(f"\n{'=' * 95}")
    print(f"  快速评分测试 v4  |  阈值 {config.scoring.threshold}  |  {len(URLS)} 个站点")
    print(f"{'=' * 95}\n")

    results = []
    for i, url in enumerate(URLS, 1):
        probe_result = await prober.probe(url)
        if probe_result.status_code == 0:
            print(f"  [{i:>2}] ❌  失败  {url}")
            print(f"         错误: {probe_result.error}\n")
            continue

        biz = classifier.classify(probe_result, config.profiles)
        scored = scorer.score(probe_result, biz)
        results.append(scored)

        if scored.score >= 80:
            flag = "★高价值"
        elif scored.score >= config.scoring.threshold:
            flag = "✓过线"
        else:
            flag = "○未过线"

        biz_str = ",".join(scored.business_types) if scored.business_types else "未分类"

        print(f"  [{i:>2}] {scored.score:>3}分 {flag}  {url}")
        print(f"         标题: {probe_result.title[:60]}")
        print(f"         业务: {biz_str}  |  表单: {'是' if scored.has_register_form else '否'}  |  SPA: {'是' if scored.is_spa else '否'}")

        # 输出完整明细（含权重为0的）
        if scored.breakdown:
            pos = [d for d in scored.breakdown if d.weight > 0]
            neg = [d for d in scored.breakdown if d.weight < 0]
            zero = [d for d in scored.breakdown if d.weight == 0]
            if pos:
                print(f"         加分项:")
                for d in pos:
                    print(f"             +{d.weight:>3}  [{d.profile}] {d.indicator}")
            if neg:
                print(f"         扣分项:")
                for d in neg:
                    print(f"             {d.weight:>4}  [{d.profile}] {d.indicator}")
            if zero:
                print(f"         标记项:")
                for d in zero:
                    print(f"               0  [{d.profile}] {d.indicator}")

        print()

    print(f"{'─' * 95}")
    print(f"  汇总（按分数排序）:")
    print(f"{'─' * 95}")
    results.sort(key=lambda r: -r.score)
    for r in results:
        status = "★" if r.score >= 80 else ("✓" if r.score >= config.scoring.threshold else "○")
        biz = ",".join(r.business_types) if r.business_types else "未分类"
        print(f"  {status} {r.score:>3}分  {r.url:<45}  {biz}")

    above = sum(1 for r in results if r.score >= config.scoring.threshold)
    high = sum(1 for r in results if r.score >= config.output.auto_highlight)
    print(f"\n  过线 {above}/{len(results)} | 高价值 {high}/{len(results)}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
