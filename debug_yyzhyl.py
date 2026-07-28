#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, ".")
from core.config import Config
from core.probe import Prober
from core.score import Scorer
from core.classifier import BusinessClassifier

async def main():
    config = Config.load("config.yaml")
    p = Prober(timeout=10, follow_redirects=True, per_domain_limit=10)
    r = await p.probe("https://yyzhyl.whut.edu.cn/")

    biz = BusinessClassifier().classify(r, config.profiles)
    scorer = Scorer(config.profiles, config.exclusions, config.scoring)
    s = scorer.score(r, biz)

    print(f"score: {s.score}")
    print(f"is_spa: {r.is_spa}  rendered: {r.rendered}")
    print(f"body_text: {repr(r.body_text)}")
    print()

    for profile in config.profiles:
        hit_count = 0
        hits_detail = []
        for check in profile.checks:
            hits = scorer._check_hit(check, r)
            if hits:
                hit_count += len(hits)
                for h in hits:
                    hits_detail.append(f"    +{check.weight} [{check.type}] {h}")

        base_awarded = hit_count >= 2
        base_str = f"+{profile.weight} 基础分 ✓" if base_awarded else f"0  基础分 ✗ (hit_count={hit_count}<2)"

        if hits_detail or profile.weight != 0:
            print(f"[{profile.name}] weight={profile.weight}  hit_count={hit_count}  base={base_str}")
            for d in hits_detail:
                print(d)
            print()

asyncio.run(main())
