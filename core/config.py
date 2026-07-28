#!/usr/bin/env python3
"""加载 YAML 配置文件，解析 profiles、exclusions、scoring 等配置"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class Check:
    type: str
    weight: int
    indicators: List[str] = field(default_factory=list)
    category: str = ""
    input_types: List[str] = field(default_factory=list)
    form_attributes: List[str] = field(default_factory=list)
    form_text_contains: List[str] = field(default_factory=list)


@dataclass
class Profile:
    name: str
    weight: int
    category: str
    threshold: int = 2
    checks: List[Check] = field(default_factory=list)


@dataclass
class Exclusion:
    type: str
    weight: int
    indicators: List[str] = field(default_factory=list)


@dataclass
class OutputConfig:
    min_score: int = 30
    auto_highlight: int = 80
    formats: List[str] = field(default_factory=lambda: ["terminal"])


@dataclass
class ProbeConfig:
    concurrency: int = 50
    timeout: int = 10
    follow_redirects: bool = True


@dataclass
class SpaConfig:
    enabled: bool = True


@dataclass
class BlacklistConfig:
    url_blacklist: List[str] = field(default_factory=list)
    content_blacklist: List[str] = field(default_factory=list)


@dataclass
class ScoringConfig:
    threshold: int = 60
    mode: str = "accumulate"


@dataclass
class Config:
    profiles: List[Profile] = field(default_factory=list)
    exclusions: List[Exclusion] = field(default_factory=list)
    blacklist: BlacklistConfig = field(default_factory=BlacklistConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    spa: SpaConfig = field(default_factory=SpaConfig)

    @staticmethod
    def load(path: str) -> "Config":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        profiles = Config._load_profiles(data.get("profiles", []))
        exclusions = Config._load_exclusions(data.get("exclusions", []))

        blacklist_data = data.get("blacklist", {})
        blacklist = BlacklistConfig(
            url_blacklist=blacklist_data.get("url_blacklist", []),
            content_blacklist=blacklist_data.get("content_blacklist", []),
        )

        scoring_data = data.get("scoring", {})
        scoring = ScoringConfig(
            threshold=scoring_data.get("threshold", 60),
            mode=scoring_data.get("mode", "accumulate"),
        )

        output_data = data.get("output", {})
        output = OutputConfig(
            min_score=output_data.get("min_score", 30),
            auto_highlight=output_data.get("auto_highlight", 80),
            formats=output_data.get("formats", ["terminal"]),
        )

        probe_data = data.get("probe", {})
        probe = ProbeConfig(
            concurrency=probe_data.get("concurrency", 50),
            timeout=probe_data.get("timeout", 10),
            follow_redirects=probe_data.get("follow_redirects", True),
        )

        spa_data = data.get("spa", {})
        spa = SpaConfig(enabled=spa_data.get("enabled", True))

        return Config(
            profiles=profiles,
            exclusions=exclusions,
            blacklist=blacklist,
            scoring=scoring,
            output=output,
            probe=probe,
            spa=spa,
        )

    @staticmethod
    def _load_profiles(includes: List[dict]) -> List[Profile]:
        profiles = []
        for item in includes:
            if "include" in item:
                include_path = Path(item["include"])
                if include_path.exists():
                    with open(include_path, "r", encoding="utf-8") as f:
                        profile_list = yaml.safe_load(f) or []
                    for p in profile_list:
                        profiles.append(Config._parse_profile(p))
            elif "name" in item:
                profiles.append(Config._parse_profile(item))
        return profiles

    @staticmethod
    def _parse_profile(data: dict) -> Profile:
        checks = []
        for c in data.get("checks", []):
            check_type = c.get("type", "")

            if check_type == "register_form":
                check = Check(
                    type=check_type,
                    weight=c.get("weight", 0),
                    input_types=c.get("input_types", []),
                    form_attributes=c.get("form_attributes", []),
                    form_text_contains=c.get("form_text_contains", []),
                )
            else:
                check = Check(
                    type=check_type,
                    weight=c.get("weight", 0),
                    indicators=c.get("indicators", []),
                    category=c.get("category", ""),
                )
            checks.append(check)

        return Profile(
            name=data.get("name", ""),
            weight=data.get("weight", 0),
            category=data.get("category", ""),
            threshold=data.get("threshold", 2),
            checks=checks,
        )

    @staticmethod
    def _load_exclusions(includes: List[dict]) -> List[Exclusion]:
        exclusions = []
        for item in includes:
            if "include" in item:
                include_path = Path(item["include"])
                if include_path.exists():
                    with open(include_path, "r", encoding="utf-8") as f:
                        excl_list = yaml.safe_load(f) or []
                    for e in excl_list:
                        exclusions.append(Exclusion(
                            type=e.get("type", ""),
                            weight=e.get("weight", 0),
                            indicators=e.get("indicators", []),
                        ))
        return exclusions
