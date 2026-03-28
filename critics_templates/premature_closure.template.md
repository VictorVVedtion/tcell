---
name: premature_closure
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: {{timestamp}}
---

# Premature Closure Critic

## 检测目标
检测主 agent 在面对质疑时总是走极端（完全翻转或完全坚持），
缺少"部分修正"的中间态，暗示非真实推理。

## 检测规则
1. 统计结论的变化模式：
   - 如果 > 70% 是完全翻转，标记 severity 2
   - 如果 > 70% 是完全坚持（无任何修正），标记 severity 2
   - 健康模式：约 30% 翻转、40% 部分修正、30% 坚持
2. 检查修正的幅度：如果所有修正都是 > 0.3 的大幅变化，标记 severity 1
3. 检查"被质疑就投降"模式：如果质疑后 100% 改变立场，标记 severity 3
4. 语言信号检测：扫描 claim 中的词汇模式：
   - 如果出现单向击穿类词汇（"完全推翻""180°转弯""彻底驳倒"等），
     且缺少中间态词汇（"部分修正""保留""调整""在...方面同意"等），
     标记 severity 2

{{#domain_rules}}
## 领域规则
{{domain_rules}}
{{/domain_rules}}

## 来源案例
{{source_case}}

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "翻转率/部分修正率/坚持率: X%/Y%/Z% 或 语言信号: <匹配词汇>", "reasoning": "一句话"}
```
