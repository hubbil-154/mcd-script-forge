# MCP_INTEGRATION · 麦当劳官方 MCP 接入文档

本作品通过**麦当劳中国官方 MCP 服务**（`https://mcp.mcd.cn`）获取真实菜单、优惠券与计价数据。

## 1. 获取 MCP Token

1. 打开 https://open.mcd.cn/mcp
2. 手机号验证码登录
3. 右上角「控制台」→「激活」→ 复制 Token

## 2. 在 WorkBuddy 中配置连接器

WorkBuddy 左侧【专家·技能·连接器】→【连接器】→【自定义连接器】→【配置 MCP】，填入：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer 你的MCP_Token"
      }
    }
  }
}
```

保存并启用 `mcd-mcp`（首次启用需点「信任」）。

> 安全提示：Token 只保存在你本地 WorkBuddy 配置里，**不要提交到任何 Git 仓库**。本项目代码不读取、不存储 Token。

## 3. 工具调用流程（本作品的用法）

```
┌─────────────┐   ①菜单查询    ┌──────────────┐
│ 用户一句话需求 │ ───────────→ │ 确认单品存在   │
└─────────────┘               │ 原价/卖点tags  │
                              └──────┬───────┘
                  ②查可领券 ↓              ↓ ③calculate-price
              ┌──────────────┐      ┌───────────────┐
              │ 找适用券/折扣价 │ ───→ │ 真实试算券后价  │
              └──────────────┘      │ 输出 best_final │
				    └───────┬───────┘
              ④campaign-calendar ↓        │
              ┌──────────────┐            │
              │ 可蹭的节日钩子 │ ───────────┤
              └──────────────┘            ▼
                                 mcp-data.json（固定 schema）
                                          │
                                          ▼
                        python mcd_script_forge.py --data mcp-data.json
                                          │
                                          ▼
                            script.md + storyboard.csv + captions.srt
```

### mcp-data.json Schema

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `_source` | string | 否 | 数据来源标注，写入脚本头部 |
| `menu` | object | ✅ | `{单品名: {price, category?, calories_kcal?, tags[]}}` |
| `coupons` | array | ✅ | `[{id, title, discount_price, applies_to, expire_days?}]` |
| `price_calc` | object | ✅ | `{单品名: {original, best_final, coupon_id?, save, plan?}}` |
| `campaign_calendar` | array | 否 | `[{name, date, hook}]`，用于钩子话术蹭节点 |

## 4. 失败降级

| 情况 | 处理 |
|---|---|
| MCP 未配置 / Token 失效 | 用 `--demo`（内置演示数据，输出标注"演示数据"）|
| 单品不在菜单 | 明确告知用户可用品类列表，不猜名字 |
| 券已过期 | 以 calculate-price 返回为准重算，不引用失效券价格 |
| 接口超时 | 重试 1 次；仍失败则降级 demo 并明确告知 |

## 实测记录（2026-10-11 · 真实联通）

- 端点：`https://mcp.mcd.cn`（JSON-RPC 2.0，HTTP POST，`Authorization: Bearer <token>`）
- 客户端：`mcp_client.py`（纯标准库，用法 `python mcp_client.py <tool> ['{...}']`）
- 实测通过工具：`available-coupons` / `auto-bind-coupons` / `query-my-coupons` / `query-nearby-stores` / `query-meals` / `query-meal-detail` / `calculate-price` / `campaign-calendar`
- 计价要点（踩坑）：
  - items 字段名是 **productCode**（不是 code），优惠券需同时传 `couponId + couponCode`
  - 价格单位为**分**，展示时 ÷100
  - 券适用性有校验：麦旋风买一送一券对泷盐星星麦旋风返回 600012「当前优惠券不可用」
- 真实计价快照（龙华和平东路店 1420139，2026-10-11）：
  | 商品 | 原价 | 券后 | 备注 |
  |---|---|---|---|
  | 麦咖啡™冰美式中杯 | ¥19.0 | **¥9.9** | 9.9元中杯冰美式券，立省9.1 |
  | "我就喜欢"鸡薯双全盒 | ¥15.9 | — | 上新品：心形薯饼×5+韩式辣椒黄油酱+5块麦乐鸡 |
  | 泷泷星愿四件套 | ¥39.9 | — | 汪苏泷限量周边，默认麦辣鸡腿汉堡 |
  | 板烧鸡腿堡（单品） | ¥23.5 | — | — |
  | 精选单人餐三件套 | ¥34.5 | — | 默认板烧 |
  | 泷盐星星麦旋风 | ¥16.5 | — | 买一送一券不适用 |
- 样片：`../mcd-demo/film-real.html?sku=1|2|3`（一页三 SKU 参数化），渲染
  `node tools/render.js --page=film-real.html --x=sku=1 --out=...`
