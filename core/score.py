#!/usr/bin/env python3
"""加权评分引擎：对每个 URL 计算注册可行性分数"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from core.config import Profile, Exclusion, Check, ScoringConfig


@dataclass
class ScoreDetail:
    profile: str
    category: str
    rule_type: str
    indicator: str
    weight: int


@dataclass
class ScoredResult:
    url: str
    final_url: str
    status_code: int
    title: str
    score: int = 0
    business_types: List[str] = field(default_factory=list)
    is_spa: bool = False
    rendered: bool = False
    has_register_form: bool = False
    recommendation: str = ""
    breakdown: List[ScoreDetail] = field(default_factory=list)
    error: str = ""


class Scorer:
    def __init__(self, profiles: List[Profile], exclusions: List[Exclusion], scoring_config: ScoringConfig):
        self.profiles = profiles
        self.exclusions = exclusions
        self.threshold = scoring_config.threshold
        self.mode = scoring_config.mode

    def score(self, probe_result) -> ScoredResult:
        """对单个探测结果计算总分，并依据 profile 阈值打分类标签"""
        result = ScoredResult(
            url=probe_result.url,
            final_url=probe_result.final_url,
            status_code=probe_result.status_code,
            title=probe_result.title,
            is_spa=probe_result.is_spa,
            rendered=probe_result.rendered,
            has_register_form=probe_result.has_register_form,
            business_types=[],
            error=probe_result.error,
        )

        total_score = 0
        biz_types = []

        # 遍历所有 profile 评分
        for profile in self.profiles:
            hit_count = 0

            for check in profile.checks:
                hits = self._check_hit(check, probe_result)
                hit_count += len(hits)
                for hit in hits:
                    detail = ScoreDetail(
                        profile=profile.name,
                        category=profile.category,
                        rule_type=check.type,
                        indicator=hit,
                        weight=check.weight,
                    )
                    result.breakdown.append(detail)
                    total_score += check.weight

            # profile 基础分：命中 indicator 总数 >= threshold 即发放
            if hit_count >= profile.threshold:
                total_score += profile.weight
                result.breakdown.append(ScoreDetail(
                    profile=profile.name,
                    category=profile.category,
                    rule_type="profile_base",
                    indicator="命中基础分",
                    weight=profile.weight,
                ))
                # 分类标签：通用不算标签，其余去重加入
                if profile.category != "通用" and profile.category not in biz_types:
                    biz_types.append(profile.category)

        # 应用排除规则（扣分）
        for exclusion in self.exclusions:
            hits = self._check_exclusion(exclusion, probe_result)
            for hit in hits:
                detail = ScoreDetail(
                    profile="排除",
                    category="exclusion",
                    rule_type=exclusion.type,
                    indicator=hit,
                    weight=exclusion.weight,
                )
                result.breakdown.append(detail)
                total_score += exclusion.weight  # weight 是负数

        # SPA 渲染加分：需要 JS 渲染才能获取内容的站点加 5 分
        if result.is_spa and result.rendered:
            detail = ScoreDetail(
                profile="系统",
                category="spa",
                rule_type="spa_rendered",
                indicator="SPA 渲染(+5)",
                weight=5,
            )
            result.breakdown.append(detail)
            total_score += 5

        result.business_types = biz_types
        result.score = max(total_score, 0)

        # 标记推荐等级
        if result.score >= 80:
            result.recommendation = "high_value"
        elif result.score >= self.threshold:
            result.recommendation = "review"
        else:
            result.recommendation = "skip"

        return result

    def _check_hit(self, check: Check, probe_result) -> List[str]:
        """检查某个 check 是否命中，返回命中的 indicator 列表"""
        check_type = check.type
        hits = []

        if check_type == "body_keyword":
            for ind in check.indicators:
                if ind.lower() in probe_result.body_lower:
                    hits.append(ind)

        elif check_type == "path":
            url_lower = probe_result.url.lower()
            final_lower = probe_result.final_url.lower()
            for ind in check.indicators:
                if ind.lower() in url_lower or ind.lower() in final_lower:
                    hits.append(ind)

        elif check_type == "title_keyword":
            title_lower = probe_result.title.lower()
            for ind in check.indicators:
                if ind.lower() in title_lower:
                    hits.append(ind)

        elif check_type == "register_form":
            if probe_result.has_register_form:
                # 返回命中的 input type 作为 indicator
                if check.input_types:
                    # 检查哪些 input type 确实存在
                    found_types = set()
                    for form in probe_result.forms_detected:
                        for t in form["input_types"]:
                            if t in [it.lower() for it in check.input_types]:
                                found_types.add(t)
                    if found_types:
                        hits.append(f"表单含: {', '.join(sorted(found_types))}")
                    else:
                        hits.append("注册表单")
                else:
                    hits.append("注册表单")

        return hits

    def _check_exclusion(self, exclusion: Exclusion, probe_result) -> List[str]:
        """检查排除规则是否命中"""
        hits = []

        if exclusion.type == "domain_keyword":
            try:
                domain = probe_result.url.split("/")[2].lower()
                for ind in exclusion.indicators:
                    if ind.lower() in domain:
                        hits.append(f"域名含: {ind}")
            except (IndexError, AttributeError):
                pass

        elif exclusion.type == "body_keyword":
            for ind in exclusion.indicators:
                if ind.lower() in probe_result.body_lower:
                    hits.append(ind)

        elif exclusion.type == "status_code":
            code = probe_result.status_code
            if str(code) in [str(x) for x in exclusion.indicators]:
                hits.append(f"HTTP {code}")

        return hits
