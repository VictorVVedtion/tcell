---
name: root_cause_blindness
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: {{timestamp}}
---

# Root Cause Blindness Critic

## 检测目标
检测主 agent 只做表面修复而忽略结构性根因的模式。
核心思想：表面修复让症状消失；根因修复让问题不再可能发生。

## 检测规则
1. **热点文件**：如果同一文件在近期被频繁修改（>5次），问"为什么这个文件总需要改？"
   - 频繁修改本身不是问题，但频繁 *修复* 是根因未解决的信号
   - 标记 severity 2
2. **禁止规则替代结构修复**：如果 agent 通过增加规则/约束来"解决"问题，而非修改产生问题的结构，标记 severity 2
3. **症状修复**：如果修复只消除了错误信息/异常，但未解释为什么会产生这个错误，标记 severity 1
4. **重复模式**：如果 canaries 中已有同类问题的历史记录，当前修复又采用了相似的表面手段，标记 severity 3

{{#domain_rules}}
## 领域规则
{{domain_rules}}
{{/domain_rules}}

## 来源案例
{{source_case}}

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "表面修复：[做了什么] vs 根因：[应该做什么]", "reasoning": "一句话"}
```
