# 注册可行性筛选工具 — 设计文档

> **版本**: v1.0
> **日期**: 2026-07-25
> **定位**: 大批量 URL 的「注册可能性」置信度打分引擎

---

## 一、用户侧写

### 你是谁

你是一名 **src 选手**（漏洞赏金猎人），日常在各类 src 平台（HackerOne、Bugcrowd、国内众测平台等）提交漏洞。

你有一个**信息收集平台**，每天自动化采集几千个 URL。这些 URL 来自你的子域名枚举、旁站探测、流量监控、证书透明度日志等渠道。

你的信息收集平台产生的 URL 有两类：

```
类型 A：大量非业务站
  - 门户站、新闻站、政府公示页
  - 静态资源站（CDN、OSS）
  - 已下线/停用的站点
  - 测试/开发环境

类型 B：真正的业务站
  - 有用户系统的平台
  - 有注册入口的系统
  - 企业内部工具（OA、CRM、ERP）
  - 内容平台（论坛、博客、学报）
  - 电商、金融、SaaS
```

你每天收集 2000-5000 个 URL，其中真正的业务站可能只有几十个。

### 你要解决什么问题

**核心痛点：从海量 URL 中快速筛出「能注册的站」**

```
每天：
  信息收集平台 → 产出 3000 个新 URL
  你的眼睛 → 一秒看一个，看 3000 个要 50 分钟
  但实际上 → 你只想知道哪些能注册，其他都是噪音

问题：
  - 3000 个 URL 手动看一遍，太慢
  - 注册入口可能藏在「作者投稿」「become an author」「提交文章」等非直观入口后面
  - 漏掉一个能注册的站 = 永久损失一个漏洞机会
```

**你不需要的是：**

- ❌ 深度漏洞扫描（那是有漏洞之后的下一步）
- ❌ 自动注册并测试（那是爬虫工程师做的事，不是你的职责）
- ❌ 注册后的权限分析（那是你人工去挖的）

**你需要的是：**

- ✅ 从 3000 个 URL 中快速筛出 50 个「高概率可注册」的候选
- ✅ 标注每个候选的业务类型（电商？投稿？OA？）
- ✅ 告诉你为什么这个站值得看（命中了什么关键词，多少分）
- ✅ 宁可多给 10 个假阳性，不能漏 1 个真阳性

### 你的工作流

```
信息收集平台（每天自动产出 3000 URL）
        ↓
本工具（注册可行性筛选）
  - 对 3000 个 URL 并发探测
  - 对每个页面做业务分类和注册可能性打分
  - 输出：50 个高置信度候选 + 业务类型标注
        ↓
你的人工复核
  - 打开 50 个候选，快速浏览
  - 确认哪些真的能注册
  - 排除误报
        ↓
漏洞挖掘
  - 对确认可注册的站做注册测试
  - 分析注册流程中的漏洞
  - 提交报告
```

### 你的核心诉求

| 诉求 | 优先级 | 说明 |
|------|--------|------|
| 召回率 | **最高** | 漏掉一个可注册站 = 损失一个漏洞 |
| 速度 | 高 | 每天 3000 URL，处理时间越短越好 |
| 业务分类 | 中 | 知道候选站是什么类型，方便你决定优先测哪个 |
| 精确率 | 中 | 宁可多给几个假的，你人工很快就能排除 |
| 可维护性 | 中 | 规则库需要你能自己加关键词、调权重 |

### 你的使用习惯

- 每天跑一到两次（早一次晚一次）
- 关注输出中的「高置信度」条目
- 根据业务类型决定优先测试顺序（供应商 > 电商 > 投稿 > ...）
- 发现漏掉的站点类型后，会要求更新关键词库
- 偶尔会调整评分阈值和权重，根据实际效果微调

---

## 二、工具定位

### 它是什么

这是一个**注册功能专用探测引擎 + 置信度打分系统**。

- **输入**: 大批量 URL（2 万+，或被动流量中的域名）
- **输出**: 每个 URL 的「注册可行性分数」以及命中详情（为什么高分 / 为什么被扣分）
- **驱动方式**: YAML 模板定义「什么算注册入口」「什么算减分项」
- **独立运行**: 可以作为自动化管道中的一环，类似 httpx 但带状态和推理能力

### 它不是什么

- ❌ 不是漏扫器（不做漏洞检测）
- ❌ 不是爬虫（不做深度页面遍历）
- ❌ 不是浏览器自动化（不做表单提交）
- ❌ 不是注册后深度分析工具（不分析注册后的权限、角色、越权）

### 核心价值

```
信息收集平台（每天产生几千 URL）
        ↓
注册可行性筛选器（本工具）
        ↓
给你一个「能注册的站」的高概率候选列表
        ↓
你人工去测这些站的注册功能能挖出什么
```

中间这个环节，之前靠眼睛看，效率低且容易漏。

---

## 三、核心设计哲学

### 3.1 召回率优先，宁可误报，不可漏报

这是整个工具最重要的设计原则。

```
真实场景：
  你一天收集 5000 个 URL
  真正能注册的站可能只有 5-10 个
  错过 1 个 = 永久损失一个漏洞机会

设计 consequence：
  - 阈值设低，初筛后人工复核
  - 宁可多给 10 个假阳性，不能漏 1 个真阳性
  - 排除规则要谨慎，宁可少排除
```

### 3.2 单层设计，不做多级工作流

```
架构：
  对每个 URL → 发一次 HTTP 请求 → 匹配所有规则 → 计算分数 → 输出

不做的：
  - 不做多级 workflow（首页 → 提取链接 → 再请求子页面）
  - 不做 foreach 分支探测
  - 不做递归深度控制
```

**为什么单层足够？**

```
场景：学报投稿站，真正的注册口在「作者投稿」按钮后面

多级 workflow 的思路：
  首页 → 找「注册」按钮 → 没找到 → 认为没有注册口 → 漏掉 ✗

单层评分的思路：
  首页 → 匹配「作者投稿」「投稿」「become an author」→ 加分
        → 匹配「输入框」「表单」→ 加分
        → 匹配「CMS 技术栈」→ 加分
        → 总分高 → 标记为可疑 → 人工复核 ✓
```

**关键洞察：注册入口的触发词远不止「注册」两个字。**

一个站点可能在任何入口后面藏着注册功能：
- 注册类：register, signup, create account, join
- 登录类：login, signin, auth, 登录
- 角色类：作者投稿, 成为作者, contributor, writer
- 功能类：submit article, write post, 投稿, 发布
- 入口类：portal, dashboard, workspace, 控制台, 工作台
- 系统类：OA, ERP, CRM, 管理后台, 内部系统

单层评分通过**丰富的关键词库 + 加权累加**，让这些间接证据汇聚成高置信度判断。

### 3.3 分数是置信度，不是概率

```
加分项分三档：

  强特征（+30 ~ +50）：
    - 页面包含可提交的注册表单（有 action 含 register 的 form）
    - 明确显示「注册账号」按钮
    - 检测到明确的用户管理系统特征

  中等特征（+15 ~ +25）：
    - 有 type=password + type=email 输入框组合
    - 有登录/注册切换标签
    - URL 路径含 /register, /signup
    - 链接文本含「注册」
    - 页面含业务类型关键词（购物车、投稿、作者等）

  弱特征（+5 ~ +10）：
    - 页面标题含「登录」
    - 有 input name=email
    - 有 /login 路径
    - 页面含通用登录相关词

惩罚项（负分）：
    - 页面返回 403/404/500：-40
    - 域名含 test/demo/staging：-30
    - 页面含「注册已关闭」「registration closed」：-50
    - 页面是纯静态内容（无表单、无交互）：-20
```

分数不是概率，而是**「这个特征强烈暗示存在注册功能」的程度**。

通过调试找到合理阈值（建议 60 分以上视为命中），阈值可配置。

### 3.4 配置驱动，规则和代码完全分离

```
所有业务知识都在 YAML 配置文件里：
  - 什么算注册入口（关键词、路径、表单特征）
  - 什么算减分项
  - 分数怎么计算
  - 阈值是多少

代码只负责：
  - 怎么发 HTTP 请求
  - 怎么提取响应特征
  - 怎么执行 YAML 里定义的规则
  - 怎么计算分数

修改业务规则 = 改 YAML，不动代码
```

### 3.5 中间结果持久化，支持断点续跑

```
N 个 URL 的扫描跑一次可能几十分钟
中间断了全部重跑是不可接受的

设计：
  核心流程简化为：HTTP 探测 → 评分 → SPA 标记 → 过滤输出
  每个阶段输出到文件
  断了可以从断点继续

阶段输出：
  output/03_probed.json       (HTTP 探测结果)
  output/04_scored.json       (评分结果)
  output/results.json         (最终结果)
```

---

## 四、整体处理流程

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│ N 个 URL │ ──→ │  阶段一   │ ──→ │  阶段二   │ ──→ │  阶段三   │
│  直接输入  │     │ HTTP探测  │     │ 业务分类  │     │ 加权评分  │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                       │               │               │
                       ▼               ▼               ▼
                 N 探测结果         业务类型         按分数排序
                (提取特征)         标注完成          最终结果
                       │               │               │
                       ▼               ▼               ▼
                 ┌──────────┐     ┌──────────┐     ┌──────────┐
                 │  阶段四   │     │  阶段五   │     │  阶段六   │
                 │ SPA标记  │ ←── │ 过滤输出  │ ←── │ 排除规则  │
                 └──────────┘     └──────────┘     └──────────┘
```

### 阶段一：HTTP 探测（核心阶段，需要并发）

```
输入：N 个 URL（已预处理，无重复，无需清洗）
处理：对每个 URL 发一次 GET 请求，提取：
  - HTTP 状态码、响应头
  - 页面标题
  - 页面纯文本内容
  - HTML 中的表单结构
  - 页面正文中的业务关键词
  - SPA 标记（HTML 内容极少 + 有 JS bundle → 标记为疑似 SPA）
输出：N 个 ProbeResult
```

### 阶段二：业务分类

```
输入：N 个 ProbeResult
处理：对每个页面的正文内容做业务类型关键词匹配
  - 命中「电商」关键词 → 标记为电商站
  - 命中「投稿」关键词 → 标记为投稿站
  - 命中「金融」关键词 → 标记为金融站
  - 多个类型同时命中 → 标记为多个类型
  - 无一命中 → 标记为「未分类」
输出：N 个带业务类型标签的结果
```

业务分类依赖的关键词库：

```
电商：购物车、结算、下单、商品、订单、运费、优惠券、add to cart、checkout
投稿：投稿、作者、审稿、编辑部、submit article、become an author、contribute
金融：理财、借贷、保险、基金、股票、银行卡、支付、转账
博客：博客、日志、文章、归档、分类、tag、rss、atom
论坛：帖子、回帖、版块、精华、置顶、forum、thread、reply
SaaS：仪表盘、工作台、控制台、dashboard、workspace、portal
OA：考勤、请假、审批、工作流、OA、办公自动化
CRM：客户管理、销售漏斗、联系人、CRM
ERP：进销存、供应链、财务、ERP
```

### 阶段三：加权评分

```
输入：N 个带业务类型标签的 ProbeResult
处理：对每个结果，遍历所有 profile 的 check 规则
  - 对每个 check，在 ProbeResult 的特征中匹配
  - 命中则加/减分
  - 多个 profile 的分数累加
  - 排除规则扣分
  - 最终分数 = max(总分, 0)
输出：N 个 ScoredResult，按分数排序
```

### 阶段四：SPA 标记（标记为主，渲染为可选后处理）

```
输入：N 个 ScoredResult
处理：
  1. 对疑似 SPA 的 URL 做标记（is_spa = true）
  2. 不在此阶段做渲染（渲染太慢，拖慢主流程）
  3. 分数在阈值附近的疑似 SPA → 标记为 needs_headless = true
输出：N 个带 SPA 标记的结果
```

### 阶段五：排除规则过滤

```
输入：N 个 ScoredResult
处理：
  - 应用排除规则（域名含 test/demo、状态码 403/404、页面含垃圾内容）
  - 命中排除规则的扣分
输出：N 个带排除标记的结果
```

### 阶段六：过滤输出

```
输入：N 个 ScoredResult
处理：
  - 过滤掉低于阈值的
  - 按总分排序
  - 按业务类型分组
输出：高置信度结果（终端表格 + JSON + CSV）
```

---

## 五、配置文件结构

### 4.1 顶层结构

```yaml
# config.yaml

profiles:          # 业务检测模板列表
  - include: profiles/generic.yaml
  - include: profiles/ecommerce.yaml
  - include: profiles/submission.yaml
  - include: profiles/supplier.yaml

exclusions:        # 全局排除规则
  - include: exclusions/common.yaml

scoring:           # 评分系统配置
  threshold: 60
  mode: accumulate  # accumulate | max | weighted

output:            # 输出配置
  min_score: 30
  auto_highlight: 80
  formats:
    - terminal
    - json
    - csv

spa:               # SPA 检测配置
  enabled: true
  headless_script: scripts/spa_worker.py  # 后处理脚本路径
```

### 4.2 Profile 结构

```yaml
# profiles/generic.yaml

- name: 通用业务检测
  weight: 10                    # 命中这个 profile 的基础分
  category: generic             # 业务类型标签
  checks:

    - type: body_keyword         # 页面正文关键词
      weight: 8
      indicators:
        - register
        - signup
        - sign up
        - create account
        - login
        - signin
        - sign in
        - forgot password
        - reset password
        - 注册
        - 登录

    - type: path                 # URL 路径
      weight: 6
      indicators:
        - /register
        - /signup
        - /login
        - /signin
        - /auth
        - /account
        - /admin

    - type: register_form        # 注册表单结构
      weight: 15
      indicators:
        input_types:
          - email
          - password
          - text
```

### 4.3 business_type 检测逻辑

```yaml
# profiles/ecommerce.yaml

- name: 电商业务检测
  weight: 15
  category: ecommerce
  checks:

    - type: business_type
      weight: 15
      category: ecommerce
      indicators:
        - 购物车
        - 结算
        - 下单
        - 商品
        - 订单
        - 运费
        - 优惠券
        - 支付
        - add to cart
        - checkout
        - shipping
        - billing
        - product
        - wishlist

    - type: body_keyword
      weight: 6
      indicators:
        - 购物
        - 商城
        - 商店
        - 在线购买
        - 立即购买
        - 加入购物车
```

### 4.4 支持的所有 check 类型

| check 类型 | 匹配目标 | 权重范围 | 说明 |
|-----------|---------|---------|------|
| `path` | URL 路径 | 5-12 | 匹配 URL 中的路径片段 |
| `body_keyword` | 页面正文 | 5-15 | 匹配页面纯文本内容中的关键词 |
| `title_keyword` | 页面标题 | 5-15 | 匹配 `<title>` 标签内容 |
| `register_form` | 表单结构 | 15-30 | 匹配注册表单的特征（见下方） |
| `business_type` | 业务分类 | 10-20 | 匹配业务类型关键词，标记站点分类 |

### 4.5 register_form 的检测逻辑

```yaml
- type: register_form
  weight: 15
  indicators:
    # 任意一个 input type 命中即算
    input_types:
      - email          # <input type="email">
      - password        # <input type="password">
      - text            # <input type="text"> (用户名)

    # form 属性特征
    form_attributes:
      - action_contains: register    # form action URL 含 register
      - method: POST                 # 表单是 POST 方法

    # form 内的文本特征
    form_text_contains:
      - 注册
      - sign up
      - create account
      - 新用户
```

### 4.6 排除规则

```yaml
exclusions:

  - type: domain_keyword
    weight: -30
    indicators:
      - test
      - demo
      - staging
      - dev.
      - example
      - localhost

  - type: body_keyword
    weight: -50
    indicators:
      - domain for sale
      - this domain expired
      - parking
      - 注册已关闭
      - 暂停注册

  - type: status_code
    weight: -40
    indicators:
      - 403
      - 404
      - 500
```

---

## 六、评分系统设计

### 5.1 评分流程

```
对每个 ProbeResult：

  total_score = 0

  # 1. 遍历所有 profile
  for profile in profiles:
    profile_score = profile.weight  # 基础分
    for check in profile.checks:
      if check.hit(result):
        profile_score += check.weight
    total_score += profile_score

  # 2. 应用排除规则
  for exclusion in exclusions:
    if exclusion.hit(result):
      total_score += exclusion.weight  # weight 是负数

  # 3. 确保不低于 0
  total_score = max(total_score, 0)

  # 4. 标记结果
  if total_score >= auto_highlight:
    recommendation = "high_value"
  elif total_score >= threshold:
    recommendation = "review"
  else:
    recommendation = "skip"
```

### 5.2 组合规则（Combo Rules）

多个特征同时命中时触发额外加分：

```yaml
combo_rules:
  - name: 注册表单三件套
    description: "同时有注册路径 + 注册关键词 + 注册表单"
    conditions:
      - type: path
        indicator: "/register"
      - type: body_keyword
        indicator: "create account"
      - type: register_form
        has_password: true
    score: 50  # 三件套全中直接给高分

  - name: 电商全链路
    description: "同时有购物车 + 结算 + 订单相关关键词"
    conditions:
      - type: body_keyword
        indicator: "shopping cart"
      - type: body_keyword
        indicator: "checkout"
      - type: body_keyword
        indicator: "order"
    score: 40
```

### 5.3 分数衰减（防膨胀）

```
特征数量很多时，后面的特征不应该再大幅加分：

  基础分 = 最强特征的分数
  后续每个命中特征的加分 = 原始权重 × 衰减系数

  衰减系数：
    第 1 个额外特征：× 1.0
    第 2 个额外特征：× 0.8
    第 3 个额外特征：× 0.6
    第 4 个及以后：  × 0.4

示例：
  发现注册表单 → 40 分（基础）
  + WordPress → +10 × 1.0 = +10
  + /register → +8 × 0.8 = +6.4
  + "sign up" → +5 × 0.6 = +3
  + 有 API 路径 → +5 × 0.4 = +2
  总分 = 40 + 10 + 6 + 3 + 2 = 61
```

---

## 七、SPA 检测设计

### 6.1 不放在核心流程中

SPA 检测作为**后处理钩子**，原因：

```
SPA 渲染需要启动 Chromium：
  - 每个页面 5-15 秒
  - 内存占用大
  - 并发只能 5-10

如果对 500 个候选都渲染：
  500 × 10 秒 = 80 分钟
  500 × 200MB 内存 = 100GB

如果只对高分候选渲染：
  50 × 10 秒 = 8 分钟
  50 × 200MB 内存 = 10GB
```

### 6.2 快速判断（不启动浏览器）

```python
def quick_spa_check(html: str) -> bool:
    """从 HTML 特征快速判断是否为 SPA"""
    # 特征 1: body 内容极少（去掉 script/link/style 后 < 200 字符）
    # 特征 2: 有 SPA 框架 JS 文件
    # 特征 3: 有 <div id="app"> 或 <div id="root">
    # 满足 2/3 即标记为疑似 SPA
```

### 6.3 后处理渲染

```
核心流程跑完后，输出一个 needs_headless 列表：

  output/needs_headless.json  ← 包含 URL + 当前分数 + 疑似原因

用单独的脚本处理：

  python scripts/spa_worker.py --input output/needs_headless.json

spa_worker.py：
  1. 读取列表
  2. 启动 Chromium（并发 5-10）
  3. 渲染每个页面
  4. 提取渲染后的 DOM 中的注册相关元素
  5. 更新 results.json 中的分数
```

### 6.4 SPA 渲染提取的内容

```python
# 渲染后提取：
{
    "rendered_title": "...",
    "register_buttons": ["注册", "Sign Up", "Create Account"],
    "register_forms": [
        {
            "action": "/api/register",
            "inputs": ["email", "password", "name"]
        }
    ],
    "api_paths": ["/api/users", "/api/auth/login", "/api/register"],
    "spa_framework": "react" | "vue" | "angular"
}
```

---

## 八、性能设计

### 7.1 并发控制

```yaml
probe:
  global_concurrency: 50       # 全局并发
  per_host_concurrency: 3      # 同一域名最多 3 个并发
  per_host_rate: 10            # 同一域名每秒最多 10 请求
  timeout: 10                  # 单请求超时（秒）
  follow_redirects: true
```

### 7.2 请求缓存

```
同一个 URL 被多个 profile 匹配到时，只发一次请求：

  profile1 匹配到 https://a.com/  → 发请求 → 缓存结果
  profile2 匹配到 https://a.com/  → 读缓存，不发请求
  profile3 匹配到 https://a.com/  → 读缓存，不发请求
```

### 7.3 响应大小控制

```
只取响应前 8KB 做分析，不需要完整下载：
  - HTML 前 8KB 足够提取所有业务关键词和表单特征
  - 节省带宽
  - 加快处理速度

例外：需要完整内容的检测（如注册表单分析）才下载全部
```

---

## 九、输出格式

### 8.1 终端输出

```
══════════════════════════════════════════════════════════════════
  可注册业务站筛选结果  (共 47 个)
══════════════════════════════════════════════════════════════════
得分   URL                                    状态   业务类型        注册
──────────────────────────────────────────────────────────────────
95     https://crm.example.com/register       200    供应商,SaaS     ✓
       │  +10  [通用业务] login
       │  +20  [供应商业务] supplier
       │  +8   [通用业务] /user/login
       │  +15  [供应商业务] vendor
       │  +10  [通用业务] create account
       │  +15  [通用业务] 注册表单

82     https://shop.example.com/checkout      200    电商              ✗
       │  +15  [电商业务] shopping cart
       │  +12  [电商业务] checkout
       │  +8   [电商业务] /checkout
       │  +10  [电商业务] add to cart
       │  +10  [电商业务] order
──────────────────────────────────────────────────────────────────
```

### 8.2 JSON 输出

```json
[
  {
    "url": "https://crm.example.com",
    "final_url": "https://crm.example.com/register",
    "score": 95,
    "recommendation": "high_value",
    "business_types": ["供应商", "SaaS"],
    "is_spa": false,
    "needs_headless": false,
    "register_links": ["https://crm.example.com/register"],
    "breakdown": [
      {"step": "probe", "score_delta": 10, "reason": "body: login"},
      {"step": "score", "score_delta": 20, "reason": "供应商业务: supplier"}
    ]
  }
]
```

### 8.3 CSV 输出

```csv
得分,URL,最终URL,状态码,业务类型,SPA,注册表单,命中的profile,注册链接
95,https://crm.example.com,https://crm.example.com/register,200,供应商/SaaS,否,否,"通用业务检测,供应商业务检测",https://crm.example.com/register
```

---

## 十、与 Nuclei 的关系

### 9.1 不复用 Nuclei 的原因

```
Nuclei 的能力：
  ✅ HTTP 请求引擎（成熟）
  ✅ 模板解析和匹配（成熟）

Nuclei 的局限：
  ❌ 没有原生计分系统（只有命中/未命中）
  ❌ 没有变量在 step 之间传递
  ❌ 没有 foreach + aggregation
  ❌ 权重只影响执行优先级，不影响分数计算
  ❌ 多个模板的匹配结果无法自动合并评分

结论：Nuclei 的 request + matcher + extractor 可以借鉴，
      但计分系统和 workflow 逻辑需要自己写。
```

### 9.2 可以借鉴的部分

```
借鉴：
  - HTTP 请求的最佳实践（超时、重试、并发）
  - 模板的 YAML 结构设计思路

不借鉴：
  - workflow 多级探测（我们用单层）
  - matcher 的 condition 语法（我们用加减分）
  - 模板优先级机制（我们用分数）
  - 技术栈指纹库（我们不识别技术栈，只做业务分类）
```

---

## 十一、实战库的演进策略

### 10.1 初期：通用模板

```
覆盖最常见的注册入口模式：
  - 通用注册/登录类关键词
  - 基础表单结构检测

覆盖率目标：40%
精确率目标：60%
```

### 10.2 中期：分行业模板

```
按业务类型写专用关键词库：
  - 电商：购物车、结算、下单、商品、订单、运费
  - 投稿：投稿、作者、审稿、编辑部、submit article
  - 金融：理财、借贷、保险、基金、支付
  - 博客：博客、日志、文章、归档、rss
  - 论坛：帖子、回帖、版块、精华、forum
  - SaaS：仪表盘、工作台、控制台、dashboard、portal
  - OA：考勤、请假、审批、工作流
  - CRM：客户管理、销售漏斗、联系人
  - ERP：进销存、供应链、财务

覆盖率目标：70%
精确率目标：70%
```

### 10.3 长期：数据驱动优化

```
反馈循环：
  工具输出 → 你人工验证 → 记录「哪些被漏掉了」→ 更新关键词库 → 重新跑

具体做法：
  1. 维护一个 verified.json，记录你验证过的结果
  2. 定期分析 false negative（工具输出低分但实际能注册的站）
  3. 从 false negative 中提取新业务关键词，加入规则库
  4. 从 false positive（工具输出高分但实际不能注册的站）中提取排除规则

覆盖率目标：85%
精确率目标：85%
```

### 10.4 外部字典文件

```yaml
# keywords/business_types.txt — 业务类型关键词（按行业分组）
电商:
  - 购物车
  - 结算
  - 下单
  - 商品
  - 订单
  - 运费
  - 优惠券
  - 支付
  - add to cart
  - checkout
  - shipping
  - billing

投稿:
  - 投稿
  - 作者
  - 审稿
  - 编辑部
  - submit article
  - become an author
  - contribute
  - 发布文章

金融:
  - 理财
  - 借贷
  - 保险
  - 基金
  - 股票
  - 银行卡
  - 支付
  - 转账

论坛:
  - 帖子
  - 回帖
  - 版块
  - 精华
  - 置顶
  - forum
  - thread
  - reply

SaaS:
  - 仪表盘
  - 工作台
  - 控制台
  - dashboard
  - workspace
  - portal
```

模板中引用：

```yaml
- type: business_type
  weight: 15
  category: ecommerce
  indicators:
    - "@import: keywords/business_types.txt::ecommerce"
```

好处：更新业务关键词不需要改模板文件，只需要改字典文件。

---

## 十二、关键设计决策汇总

| 决策 | 选择 | 原因 |
|------|------|------|
| 单层 vs 多层 workflow | 单层 | 注册入口的触发词多样，单层评分通过关键词库覆盖更灵活 |
| 召回率 vs 精确率 | 召回率优先 | 错过一个可注册站 = 永久损失漏洞机会 |
| 分数性质 | 置信度 | 强/中/弱特征加权累加，通过阈值控制敏感性 |
| 模板数量 | 分行业多个 | 不同业务类型的注册入口差异大，分开维护更清晰 |
| SPA 检测 | 后处理 | 渲染太慢，不拖慢主流程 |
| 中间结果 | 持久化到文件 | 支持断点续跑，断了不用从头开始 |
| 并发策略 | 全局 + 域名级双控 | 全局控制总吞吐，域名级防止打挂目标 |
| 请求缓存 | 按 URL 缓存 | 同一 URL 被多个 profile 匹配时只发一次请求 |
| 技术栈识别 | 不做 | 工具定位是业务分类 + 注册可能性打分，不是指纹识别 |

---

## 十三、项目文件结构

```
reg-finder/
├── config.yaml                  ← 主配置（引用子模板）
├── main.py                      ← 入口
├── requirements.txt
│
├── core/
│   ├── __init__.py
│   ├── config.py                ← 加载/校验 YAML 配置
│   ├── prober.py                ← HTTP 探测，提取响应特征
│   ├── scorer.py                ← 加权评分引擎
│   ├── classifier.py            ← 业务类型分类器
│   ├── output.py                ← 终端表格 + JSON + CSV
│   └── cache.py                 ← 请求缓存
│
├── profiles/                    ← 业务检测模板（按行业拆分）
│   ├── generic.yaml             ← 通用业务（注册/登录/表单）
│   ├── ecommerce.yaml           ← 电商
│   ├── submission.yaml          ← 投稿/内容平台
│   ├── supplier.yaml            ← 供应商/B2B
│   ├── finance.yaml             ← 金融
│   ├── blog.yaml                ← 博客
│   ├── forum.yaml               ← 论坛
│   ├── saas.yaml                ← SaaS
│   ├── oa.yaml                  ← OA
│   ├── crm.yaml                 ← CRM
│   └── erp.yaml                 ← ERP
│
├── exclusions/                  ← 排除规则
│   └── common.yaml
│
├── keywords/                    ← 外部关键词字典
│   ├── business_types.txt       ← 业务类型关键词
│   └── register_forms.txt       ← 注册表单关键词
│
├── scripts/
│   └── spa_worker.py            ← SPA 后处理脚本
│
└── output/                      ← 中间结果和最终输出
    ├── 03_probed.json
    ├── 04_scored.json
    ├── needs_headless.json
    └── results.json
```

---

## 十四、核心指标

```
召回率（Recall）：
  工具标记为「可注册」的站点中，实际能注册的比例
  目标：> 85%

精确率（Precision）：
  实际能注册的站点中，被工具标记为「可注册」的比例
  目标：> 70%

处理速度：
  20k URL 全程处理 < 30 分钟
  HTTP 探测阶段 < 15 分钟
```

---

## 十五、后续可扩展方向

```
短期（v1 完成即可）：
  ✅ 单层评分引擎
  ✅ YAML 配置驱动
  ✅ 业务类型分类（电商/投稿/金融/博客/论坛/SaaS/OA/CRM/ERP）
  ✅ 终端 + JSON + CSV 输出
  ✅ 断点续跑
  ✅ SPA 后处理钩子

中期（v2）：
  - 注册表单字段分析（分析表单有哪些字段，推断注册门槛）
  - 业务类型自动识别后切换专用模板
  - 结果可视化面板（Web 界面浏览结果）

长期（v3）：
  - 对接你的信息收集平台（自动拉取新 URL 并扫描）
  - 社区驱动的业务关键词库（共享业务分类关键词）
  - 自动注册试探（在授权范围内自动提交测试数据，分析响应）
```

---

*本文档是此工具的设计权威来源。所有实现决策应以本文档为准。*
