# 大乐透预测系统

自动预测 + 开奖验证 + 策略自学习，通过微信推送结果。

## 自动化运行

- **每周一、三、六 22:00 (CST)**：自动验证上一期开奖、更新学习数据库、生成下一期预测
- 结果通过 ServerChan 推送到微信
- 预测报告可在 GitHub Actions 运行记录的 Artifacts 中下载

## 文件说明

| 文件 | 说明 |
|------|------|
| `dlt_predict.py` | 主脚本 |
| `dlt_learn.json` | 学习数据库（缓存，自动持久化） |
| `.github/workflows/dlt_predict.yml` | GitHub Actions 配置 |

## 本地运行

```bash
# 仅预测
python dlt_predict.py

# 验证 + 学习 + 预测
python dlt_predict.py verify
```

## 免责声明

彩票开奖是随机事件，任何分析方法都不能保证中奖。请理性购彩。
