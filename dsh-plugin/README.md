# DSH 顺丰速运插件

适配 DeepSeek Harness `0.1.7-rc.1`，提供原生工具和基于极简模式的「顺丰速运」Agent 预设，无需配置 MCP 服务。

## 安装

先在本项目安装 Python 3.11+ 虚拟环境及依赖（见根目录 README）。在 DSH 源码目录运行：

```powershell
pnpm dsh plugin --profile web add C:\Users\你的用户名\Desktop\sf\dsh-plugin
```

已安装发行版的用户使用 `dsh plugin --profile web add <插件绝对路径>`。安装后重启 DSH。插件默认使用 `%USERPROFILE%/Desktop/sf` 及其中的 `.venv/Scripts/python.exe`；其他安装目录或平台需在启动 DSH 前设置 `SF_DSH_PROJECT` 与 `SF_DSH_PYTHON`，分别指向项目目录和 Python 可执行文件。

## 配置与使用

1. 打开 **设置 → 顺丰速运**（位于 Agent 预设下方）。
2. 选择沙盒或生产环境，填写该环境的顾客编码、校验码和签名方式，点击「保存并启用此环境」。凭据分别存入 DSH 本机凭据库，校验码不回显。签名方式必须与顺丰平台一致。
3. 新建任务，选择 **顺丰速运** 预设，通过对话下单、查件或取消。生产环境支持真实查件、下单及取消；下单和取消前，Agent 需要核对本次操作并获得确认。

| 工具 | 用途 |
|---|---|
| `sf_create_order` | 创建订单，客户订单号可自动生成 |
| `sf_track_shipment` | 按运单号或客户订单号查询轨迹 |
| `sf_cancel_order` | 按客户订单号取消；也支持本机 24 小时内保存了对应关系的运单号 |

仅在「顺丰速运」预设中注册这三个工具，保留极简模式的终端能力。既有任务的预设不会自动切换。订单对应关系按环境和顾客编码隔离；未保存或已过期的运单号无法反查订单号。取消使用 `EXP_RECE_UPDATE_ORDER`、`dealType=2`，需开通相应接口且订单尚可取消。

若结果为 `outcome_unknown`，操作可能已被顺丰接收，需先核实，不能盲目重试。Python 服务通过标准输入接收凭据，不把凭据放进命令行或工具结果。配置页与独立查件网页使用各自的凭据设置。

## 验证

```powershell
node --test dsh-plugin/runner.test.js
.\.venv\Scripts\python.exe -m pytest -q
```

这些自动化测试不创建真实订单。
