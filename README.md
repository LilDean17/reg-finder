# reg-finder

批量 URL **注册可行性筛选器**。

对大规模 URL 列表进行并发探测，通过页面内容分析、表单检测和多维评分，识别具有注册入口的站点并输出置信度排序结果。

## 核心功能

- **并发探测** — 对数千个 URL 发起异步 HTTP 请求，自动限流（全局 + 域名级并发控制）
- **SPA 渲染** — 自动识别单页应用，可选调用 Playwright 渲染后提取内容
- **多维评分** — 基于 URL 路径、页面正文、标题、表单结构进行加权打分
- **业务分类** — 自动识别站点业务类型（电商、投稿、OA、供应商、统一登录等）
- **双层过滤** — URL 层黑名单（零请求开销）+ 内容层黑名单，提前排除无效目标
- **流式输出** — 扫描过程中实时增量写入 CSV / JSONL，支持 `tail -f` 监控
- **配置驱动** — 所有评分规则通过 YAML 文件定义，无需修改代码即可调整关键词和权重

## 输出格式

| 文件 | 格式 | 说明 |
|---|---|---|
| `results.csv` | CSV | 实时增量写入，可直接打开查看 |
| `results.jsonl` | JSONL | 每行一条记录，适合程序二次处理 |
| `scan.log` | 文本 | 终端输出副本，支持实时追踪 |
| `results_filtered.xlsx` | Excel | 通过 `format_excel.py` 格式化输出 |

## 评分机制

每个 URL 经过多层规则匹配累计得分，分数反映页面具有注册入口的可能性。

**加分项：**

- 页面存在注册表单（含 email + password 输入框、form action 含注册关键词）
- URL 路径命中注册/登录相关关键词（`/register`、`/signup`、`/login` 等）
- 页面正文命中业务关键词（注册、登录、购物车、投稿、采购等）
- 页面标题命中注册/登录相关关键词
- 命中特定业务类型规则（电商、供应商、图书馆、统一登录、CMS、后台系统、校园邮箱、门户站）
- SPA 成功渲染额外加分

**扣分/过滤项：**

- URL 命中黑名单（404、error、parked、test.、demo. 等）— 直接跳过，不发请求
- 页面内容命中黑名单（维护中、系统升级、仅限内部访问等）— 探测后跳过评分
- 域名含 test / demo / staging — 扣分
- HTTP 错误状态码（403 / 404 / 500）— 扣分
- 页面标注注册已关闭 — 扣分
- 纯静态页面（无表单、无交互元素）— 扣分

## 安装

```bash
git clone https://github.com/LilDean17/reg-finder.git
cd reg-finder
pip install -r requirements.txt
```

**依赖说明：**

| 库 | 用途 |
|---|---|
| httpx | 异步 HTTP 请求 |
| beautifulsoup4 | HTML 解析 |
| lxml | HTML 解析器 |
| pyyaml | YAML 配置加载 |
| playwright *(可选)* | SPA 页面渲染 |

Playwright 为可选依赖，未安装时自动跳过 SPA 渲染，其余功能不受影响：

```bash
playwright install chromium
```

## 使用

```bash
python main.py urls.txt
```

`urls.txt` 每行一个 URL，注释行以 `#` 开头。

## 配置

### 主配置 `config.yaml`

```yaml
# 加载业务检测模板
profiles:
  - include: profiles/通用.yaml
  - include: profiles/电商站.yaml
  # 按需增减...

# 全局排除规则
exclusions:
  - include: exclusions/通用排除.yaml

# 黑名单（命中直接跳过）
blacklist:
  url_blacklist:       # 发请求前过滤，零开销
    - 404
    - error
    - test.
    - demo.
  content_blacklist:   # 请求后过滤页面内容
    - 网站维护中
    - 注册功能已关闭
    - Welcome to nginx!

# 评分系统
scoring:
  threshold: 60        # 高于此分视为候选
  mode: accumulate      # 累加所有命中权重

# HTTP 探测
probe:
  concurrency: 150     # 全局并发数
  timeout: 8           # 单请求超时（秒）
  follow_redirects: true

# SPA 检测
spa:
  enabled: true        # 启用 SPA 自动渲染
```

### 业务检测规则 `profiles/*.yaml`

每个 YAML 文件定义一个检测模板，包含多个 check 规则：

```yaml
- name: 电商业务检测
  weight: 15            # 该模板命中的基础分
  threshold: 2          # 至少命中 2 个 indicator 才发放基础分
  category: 电商站      # 业务分类标签
  checks:
    - type: body_keyword   # 匹配页面正文
      weight: 15
      indicators:
        - 购物车
        - 结算
        - 下单
    - type: path           # 匹配 URL 路径
      weight: 6
      indicators:
        - /shop
        - /cart
    - type: title_keyword  # 匹配页面标题
      weight: 10
      indicators:
        - 商城
```

内置 9 个业务模板：通用、电商站、供应商站、统一登录、后台站点、CMS 系统、图书馆系统、校园邮箱系统、门户站。

### 排除规则 `exclusions/通用排除.yaml`

命中即扣分，用于过滤明显不相关的站点类型。

## 项目结构

```
reg-finder/
├── main.py                 # 入口脚本
├── config.yaml             # 主配置
├── requirements.txt        # Python 依赖
│
├── core/
│   ├── config.py           # YAML 配置加载与解析
│   ├── probe.py            # HTTP 异步探测 + SPA 检测与渲染
│   ├── score.py            # 加权评分引擎
│   └── output.py           # 终端表格 / CSV / JSON 输出
│
├── profiles/               # 业务检测规则（YAML）
│   ├── 通用.yaml
│   ├── 电商站.yaml
│   ├── 供应商站.yaml
│   ├── 统一登录.yaml
│   ├── 后台站点.yaml
│   ├── CMS系统.yaml
│   ├── 图书馆系统.yaml
│   ├── 校园邮箱系统.yaml
│   ├── 期刊投稿平台.yaml
│   └── 门户站.yaml
│
├── exclusions/
│   └── 通用排除.yaml       # 全局排除规则
│
├── output/                 # 输出目录
│   ├── results.csv
│   ├── results.jsonl
│   ├── scan.log
│   └── results_filtered.xlsx
│
├── format_excel.py         # CSV → Excel 格式化
├── filter_merge.py         # 结果过滤与合并
└── DESIGN.md               # 设计文档
```

## 典型工作流

```bash
# 1. 导入 URL 列表
cat > urls.txt

# 2. 运行筛选
python main.py urls.txt

# 3. 实时追踪输出
tail -f output/scan.log

# 4. 查看结果
open output/results.csv

# 5. 格式化为 Excel（可选）
python format_excel.py
```

## License

MIT
