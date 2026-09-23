# 顺丰速运 MCP 工具

提供三个 AI Agent 可调用的 MCP 工具：`sf_create_order`（创建顺丰订单）、`sf_track_shipment`（查询运单轨迹）和 `sf_cancel_order`（取消订单）。服务使用 stdio，由 MCP 客户端作为本地子进程启动。当前仅覆盖中国内地普通寄件；顺丰同城、国际件、退货、面单打印与批量下单不在范围内。

## DSH 插件

配套 [DSH 顺丰速运插件](dsh-plugin/README.md) 提供原生工具、设置页和基于极简模式的 Agent 预设。安装后在 **设置 → 顺丰速运** 分别配置沙盒/生产凭据，新建任务选择「顺丰速运」即可使用。客户订单号自动生成，运单对应关系保存 24 小时。

MCP 取消工具接受 `{"request":{"order_id":"原客户订单号"}}`；生产取消与下单共用 `SF_ALLOW_PRODUCTION_ORDERS=true` 开关。取消接口为 `EXP_RECE_UPDATE_ORDER`（`dealType=2`）；只有明确返回成功才报告已取消，超时或不确定响应返回 `outcome_unknown`，不可自动重试。

## 依据与接入前提

公开的顺丰接口规范列出下单 `EXP_RECE_CREATE_ORDER`、路由查询 `EXP_RECE_SEARCH_ROUTES`、订单结果查询 `EXP_RECE_SEARCH_ORDER_RESP`，以及沙盒/生产接入地址。[顺丰接口规范](https://qiao.sf-express.com/doc/download/%E4%B8%B0%E6%A1%A5%E5%B9%B3%E5%8F%B0%E6%96%B0API%E6%8E%A5%E5%8F%A3%E8%A7%84%E8%8C%83.pdf) 和 [官方 SDK 指南](https://qiao.sf-express.com/doc/download/laas/sdk/%E4%B8%B0%E6%A1%A5SF-CSIM-EXPRESS-SDK%E6%8C%87%E5%8D%97.pdf) 用于实现签名与表单请求。公开规范标注于 2019 年；在真实联调前，请以你账号中可见的**最新接口文档**核对字段、签名、接口授权和地址。

先在[顺丰开放平台](https://open.sf-express.com/)注册或登录，按 API 客户流程创建应用、关联下单和路由查询接口，取得顾客编码 `partnerID` 与校验码 `checkWord`。若需要超时后的订单结果核查，也需开通订单结果查询接口。只查询当前接入账号有权限的运单。**不要把校验码发到聊天或提交到 Git。**

## 安装

需要 Python 3.11 或更新版本。Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

本地测试可安装 `-e '.[test]'`，然后运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 配置

在 MCP 主机的环境变量或密钥管理中设置：

| 变量 | 用途 |
|---|---|
| `SF_PARTNER_ID` | 顺丰顾客编码，必填 |
| `SF_CHECK_WORD` | 顺丰校验码，必填 |
| `SF_ENV` | `sandbox`（默认）或 `production` |
| `SF_SIGN_MODE` | `standard`（默认，先做 URL 编码）或 `simple`（简易 MD5，直接签名原始字符串）；须与顺丰平台选项一致 |
| `SF_HTTP_TIMEOUT` | HTTP 超时秒数，默认 `10` |
| `SF_ORDER_MAP_PATH` | 可选：本机订单号与运单号对应关系的 SQLite 文件路径；默认保存在当前用户的应用数据目录 |
| `SF_ALLOW_PRODUCTION_ORDERS` | 仅填 `true` 才允许生产下单，默认关闭 |
| `SF_API_URL` | 可选接口地址覆盖；只允许当前环境对应的顺丰域名和 HTTPS |

`.env.example` 是变量清单；程序不会自动读取 `.env`。可将真实值交给 MCP 主机的密钥管理，也可在启动 MCP 主机的进程环境中设置。服务在没有凭据时仍可列出工具，但调用会返回配置错误。

通用 stdio MCP 客户端配置示例（把 `command` 改为本机实际的绝对路径）：

```json
{
  "mcpServers": {
    "sf-express": {
      "command": "C:\\Users\\PC\\Desktop\\顺丰测试\\.venv\\Scripts\\python.exe",
      "args": ["-m", "sf_express_mcp.server"]
    }
  }
}
```

## 工具输入

### `sf_create_order`

示例参数（MCP 参数最外层的键为 `order`）：

```json
{
  "order": {
    "order_id": "SHOP-20260923-0001",
    "sender": {"name": "寄件人", "mobile": "13800000000", "province": "广东省", "city": "深圳市", "address": "福田区示例路 1 号"},
    "recipient": {"name": "收件人", "mobile": "13900000000", "province": "上海市", "city": "上海市", "address": "浦东新区示例路 2 号"},
    "cargo": [{"name": "文件", "count": 1}],
    "parcel_qty": 1,
    "pay_method": 1,
    "request_pickup": false
  }
}
```

`order_id` 必须是业务系统稳定且唯一的客户订单号。工具返回订单号和顺丰运单号列表。发起订单前，Agent 应向用户展示寄收件人、地址、托寄物、付款方式及揽收选项，并取得确认。**MCP 工具注解只是提示，无法代替 MCP 主机的人类批准机制。**生产环境需要同时开启主机的下单工具批准机制，并设置 `SF_ENV=production` 与 `SF_ALLOW_PRODUCTION_ORDERS=true`。

若下单请求出现网络超时或服务器错误，服务会按同一订单号调用订单结果查询，不会再次提交下单；仍无法确认时返回 `outcome_unknown`，应人工或通过顺丰后台核实。重复订单错误也会按订单号核查。

### `sf_track_shipment`

按运单号查询：

```json
{"query": {"tracking_type": "waybill", "tracking_number": "SF1234567890123"}}
```

也可将 `tracking_type` 设为 `order`，用本账号创建订单时的客户订单号查询。结果包含 `events`（按时间升序）、`latest` 和 `waybill_number`；没有轨迹时 `events` 为空，`status` 为 `no_events`。

## 沙盒联调步骤

1. 确认应用已开通三个所需接口及沙盒权限，配置沙盒顾客编码与校验码。
2. 在 MCP 客户端列出两个工具，先用非真实个人信息和唯一测试订单号调用 `sf_create_order`。
3. 使用返回的运单号调用 `sf_track_shipment`。沙盒订单未必会出现真实运输节点，因此空轨迹不一定是接口失败。
4. 如顺丰返回签名、权限或字段错误，按账号中的最新文档核对，不要把密钥或完整寄收件地址写入问题单或日志。

本仓库的自动化测试使用模拟顺丰响应，不会向顺丰发请求。

## 临时可视化冒烟测试页

在已安装依赖的目录中启动本机网页：

```powershell
.\.venv\Scripts\python.exe -m sf_express_mcp.smoke_web --port 8765
```

浏览器打开 [http://127.0.0.1:8765/](http://127.0.0.1:8765/)。在页面顶部选择沙盒或生产环境，输入该环境的顾客编码、校验码，并选择与顺丰平台一致的签名方式。网页默认使用简易 MD5；若平台选择标准 MD5，请在网页切换。保存后即可用于当前网页的下单与查件请求，无需重启服务。切换环境时，网页使用该环境单独保存的凭据；尚未填写时不会复用另一环境的凭据。保存只表示已填写，真正的签名和权限校验发生在调用顺丰接口时。页面还提供清除当前环境网页配置的按钮。凭据只保存在当前 Python 进程内，重启后失效；若所选环境等于启动进程的 `SF_ENV` 且未在网页配置，仍会使用启动进程的环境变量。状态栏只显示运行环境、签名方式与凭据是否已填写，不展示顾客编码或校验码。页面不会使用 Cookie 或浏览器本地存储；刷新即清空填写内容。

网页下单时自动生成客户订单号，不要求手动填写。提交结果不确定时会保留该编号，并将它填入查件表单供核实；成功下单后清空表单，下一笔订单再生成新编号。

下单成功后，服务将客户订单号与返回的每个运单号保存在当前用户的本机 SQLite 文件中，保存 **24 小时**，重启服务后仍可查询；过期后不再返回，并在后续读写时清理。按运单号查件时，页面会显示保存的客户订单号。记录按运行环境和顾客编码隔离；文件不包含顾客校验码、联系人、电话或地址。此功能只覆盖通过本服务下单并成功取得运单号的订单。

网页服务只监听 `127.0.0.1`，仅接受同源的 JSON 请求。网页下单与查件均使用网页所选环境。生产下单会创建真实订单，页面会显示生产环境确认对话框，服务端也要求明确的生产确认标记和环境一致性。网页生产下单无需 `SF_ALLOW_PRODUCTION_ORDERS`；该变量仍控制 MCP 工具的生产下单权限。关闭运行它的终端或按 `Ctrl+C` 即停止网页服务。

缺少凭据时可先检查页面和输入校验；实际联调需在网页填写当前环境的凭据，或在启动服务的进程环境中设置 `SF_PARTNER_ID`、`SF_CHECK_WORD`，并确保顺丰应用已获得对应环境的接口权限。修改环境变量后须重启网页服务。生产接口默认使用顺丰当前路由查询文档列出的 `https://bspgw.sf-express.com/std/service`；旧版 `sfapi.sf-express.com` 地址仍可通过 `SF_API_URL` 显式指定。
