# A股超短双体系每日行情分析推送

## 功能
每日16:00自动获取A股行情，用**淘股吧超短**+**欧特慢慢龙头**双体系分析，生成明日预案并可推送到企业微信。
“重点观察池”和“明日买入建议”会根据当日涨停池、板块涨停数量、连板高度、成交额和换手率动态筛选，不再使用固定股票名单；当数据不足时会明确提示暂无候选，而不是重复推送旧名单。

## 架构
```
market-push/
├── market_push.py   # 主程序(数据获取→双体系分析→报告生成→推送)
├── run_daily.bat    # Windows定时任务启动脚本
├── setup_task.ps1   # 一键安装Windows任务计划(管理员)
├── .env.template    # 环境变量模板(Webhook等)
├── reports/         # 历史报告存档
└── logs/            # 运行日志
```

## 使用方式

### 1. 安装Python依赖
```bash
pip install akshare requests pandas
```

### 2. 测试运行（仅保存报告，不推送）
```bash
python market_push.py --no-push
```

### 3. 指定交易日运行
```bash
python market_push.py --date 20260629 --no-push
```

### 4. 启用企业微信推送
设置环境变量 `WEBHOOK_URL`，或修改脚本中的默认值：
```bash
set WEBHOOK_URL=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key
python market_push.py
```

### 5. 设置Windows定时任务(每日16:00)
以**管理员**身份运行PowerShell:
```powershell
.\setup_task.ps1
```

或手动设置:
1. 打开"任务计划程序"(taskschd.msc)
2. 创建基本任务 → 名称"A股双体系行情推送"
3. 触发器: 每日 16:00
4. 操作: 启动程序 → `完整路径\run_daily.bat`

## 命令行参数
| 参数 | 说明 |
|------|------|
| `--no-push` | 不推送企业微信，仅保存本地报告 |
| `--date YYYYMMDD`
