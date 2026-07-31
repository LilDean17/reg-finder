#!/usr/bin/env python3
"""HTTP 探测模块：对 URL 发请求，提取页面特征。支持 SPA 渲染。使用 curl_cffi 模拟 Chrome TLS 指纹。"""
import re
import asyncio
import warnings
from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession
from dataclasses import dataclass, field
from typing import List, Optional, Dict

warnings.filterwarnings("ignore", category=UserWarning)


@dataclass
class ProbeResult:
    url: str
    final_url: str
    status_code: int
    title: str = ""
    body_text: str = ""
    body_lower: str = ""
    forms_detected: List[dict] = field(default_factory=list)
    has_register_form: bool = False
    is_spa: bool = False
    rendered: bool = False
    error: str = ""


class Prober:
    def __init__(self, concurrency: int = 50, timeout: int = 10, follow_redirects: bool = True,
                 per_domain_limit: int = 10):
        self.concurrency = concurrency
        self.timeout = timeout
        self.follow_redirects = follow_redirects
        self.per_domain_limit = per_domain_limit
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = {}
        self._playwright_available = None
        self._playwright_lock = asyncio.Lock()
        self._session = None  # AsyncSession 复用连接池
        # Playwright 浏览器并发限制：每个 Chromium 实例吃 100~500MB，必须严格限流
        self._pw_semaphore = asyncio.Semaphore(2)

    def _get_session(self):
        """懒初始化 AsyncSession，复用连接池"""
        if self._session is None:
            self._session = AsyncSession(
                max_clients=self.concurrency,
                timeout=self.timeout,
            )
        return self._session

    async def _get_playwright(self):
        """懒检测 Playwright 是否可用，仅第一次启动浏览器测试"""
        if self._playwright_available is None:
            async with self._playwright_lock:
                if self._playwright_available is None:  # double-check
                    try:
                        from playwright.async_api import async_playwright
                        async with async_playwright() as p:
                            browser = await p.chromium.launch(headless=True)
                            await browser.close()
                        self._playwright_available = True
                    except ImportError:
                        self._playwright_available = False
                    except Exception:
                        self._playwright_available = False
        return self._playwright_available

    async def probe(self, url: str) -> ProbeResult:
        """
        探测单个 URL：
          1. 用 curl_cffi (Chrome TLS 指纹) 发请求拿 HTML
          2. 判断是否为 SPA
          3. 如果是 SPA 且有 Playwright → 渲染
          4. 从最终 HTML 提取特征
        """
        try:
            domain = url.split("//")[1].split("/")[0]
        except (IndexError, AttributeError):
            domain = "default"

        if domain not in self._domain_semaphores:
            self._domain_semaphores[domain] = asyncio.Semaphore(self.per_domain_limit)

        async with self._domain_semaphores[domain]:
            return await self._do_probe(url)

    async def _do_probe(self, url: str) -> ProbeResult:
        """实际探测逻辑，由 probe() 调用并加上域名级并发限制"""
        try:
            session = self._get_session()

            # 浏览器级 headers（Chrome TLS 指纹 + Sec-CH-UA 等）
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "Sec-CH-UA": '"Chromium";v="146", "Google Chrome";v="146", "Not=A?Brand";v="99"',
                "Sec-CH-UA-Mobile": "?0",
                "Sec-CH-UA-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }

            # curl_cffi: impersonate="chrome" 模拟 Chrome 146 的 TLS 指纹
            resp = await session.get(
                url,
                headers=headers,
                impersonate="chrome",
                allow_redirects=self.follow_redirects,
            )
            raw_html = resp.text

            # 检测 CDN/WAF 挑战
            if resp.status_code in (567, 569, 593, 599):
                return ProbeResult(
                    url=url, final_url=str(resp.url),
                    status_code=resp.status_code,
                    error="CDN挑战"
                )

            if len(raw_html) < 100 and resp.status_code >= 200:
                return ProbeResult(
                    url=url, final_url=str(resp.url),
                    status_code=resp.status_code,
                    error="CDN挑战[短响应]"
                )

            # 判断是否为 SPA
            is_spa = self._detect_spa(raw_html)

            # 如果是 SPA，尝试 Playwright 渲染
            html_to_parse = raw_html
            rendered = False
            if is_spa:
                rendered_html = await self._render_spa(url)
                if rendered_html:
                    html_to_parse = rendered_html
                    rendered = True

            return self._extract_features(url, str(resp.url), resp.status_code, html_to_parse, is_spa, rendered)

        except Exception as e:
            err = str(e)[:100]
            if "timeout" in err.lower():
                return ProbeResult(url=url, final_url=url, status_code=0, error="timeout")
            return ProbeResult(url=url, final_url=url, status_code=0, error=err)

    async def _render_spa(self, url: str) -> Optional[str]:
        """用 Playwright 渲染 SPA 页面，返回渲染后的 HTML"""
        async with self._pw_semaphore:  # 限制同时运行的浏览器数量（每个吃 100~500MB）
            try:
                pw = await self._get_playwright()
                if not pw:
                    return None

                from playwright.async_api import async_playwright

                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                        ],
                    )
                    context = await browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                        locale="zh-CN",
                    )
                    page = await context.new_page()

                    await page.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                        window.chrome = { runtime: {} };
                        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                    """)

                    await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    await page.wait_for_timeout(3000)

                    html = await page.content()
                    await browser.close()
                    return html

            except Exception:
                return None

    def _detect_spa(self, html: str) -> bool:
        """检测是否为 SPA 或 JS 重定向页"""
        body_match = re.search(r'<body[^>]*>(.*?)</body>', html, re.DOTALL | re.IGNORECASE)
        if not body_match:
            return False

        body_content = body_match.group(1)
        clean = re.sub(
            r'<(script|link|style|noscript)[^>]*>.*?</\1>',
            '', body_content, flags=re.DOTALL | re.IGNORECASE
        )
        clean = re.sub(r'<[^>]+>', '', clean).strip()

        content_is_empty = len(clean) < 300
        content_is_completely_empty = len(clean) == 0

        spa_js_patterns = [
            r'main\.\w+\.js', r'chunk-vendors', r'chunk\.\w+\.js',
            r'_next/static', r'_nuxt/', r'nuxt\.',
            r'createRoot\s*\(', r'createApp\s*\(', r'ngDoBootstrap',
            r'element-ui', r'element-ui\.css',
            r'new\s+Vue\s*\(', r'Vue\.component\s*\(', r'Vue\.use\s*\(',
            r'el-table', r'el-form', r'el-button', r'el-input',
        ]
        has_spa_js = any(re.search(p, html, re.IGNORECASE) for p in spa_js_patterns)

        has_root_div = bool(re.search(
            r'<div\s+id=["\'](app|root|app-root|app-container)["\']\s*>\s*(?:</div>)?',
            html, re.IGNORECASE
        ))

        has_js_redirect = bool(re.search(
            r'window\.location\.(href|replace)\s*=|location\.href\s*=',
            html, re.IGNORECASE
        ))

        signals = sum([content_is_empty, has_spa_js, has_root_div, has_js_redirect])
        if content_is_completely_empty:
            return True
        return signals >= 2

    def _extract_features(self, url, final_url, status_code, html, is_spa, rendered) -> ProbeResult:
        """从 HTML 提取所有特征"""
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        if soup.title and soup.title.string:
            title = soup.title.string.strip()

        body_text = soup.get_text(separator=" ", strip=True)
        body_lower = body_text.lower()

        forms_detected = self._extract_forms(soup)
        has_register_form = self._has_register_form(forms_detected, body_lower)

        return ProbeResult(
            url=url, final_url=final_url, status_code=status_code,
            title=title, body_text=body_text, body_lower=body_lower,
            forms_detected=forms_detected, has_register_form=has_register_form,
            is_spa=is_spa, rendered=rendered,
        )

    def _extract_forms(self, soup) -> List[dict]:
        forms = []
        for form in soup.find_all("form"):
            inputs = form.find_all("input")
            input_types = [i.get("type", "text").lower() for i in inputs]
            input_names = [i.get("name", "").lower() for i in inputs]
            action = form.get("action", "").lower()
            form_text = form.get_text(separator=" ", strip=True).lower()
            forms.append({
                "input_types": input_types, "input_names": input_names,
                "action": action, "text": form_text,
            })
        return forms

    def _has_register_form(self, forms: List[dict], body_lower: str) -> bool:
        for form in forms:
            has_email = any(t == "email" or "email" in n for t, n in zip(form["input_types"], form["input_names"]))
            has_password = "password" in form["input_types"]
            if has_email and has_password:
                return True
            register_words = ["register", "signup", "sign-up", "create account", "注册"]
            if any(w in form["text"] or w in form["action"] for w in register_words):
                return True
        if any("password" in f["input_types"] for f in forms):
            register_words = ["register", "signup", "sign up", "create account", "注册账号", "新用户"]
            if any(w in body_lower for w in register_words):
                return True
        return False
