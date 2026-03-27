---
name: whack_a_mole
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: {{timestamp}}
---

# Whack-a-Mole Critic

## 检测目标
检测修复"移动"了问题而非真正解决了问题的模式。
核心思想：真正的修复消除根因；打地鼠式修复把问题从 A 移到 B。

## 检测规则
1. **修复-回退模式**：如果一个 fix 在后续被 revert 或需要 re-fix，标记 severity 3
2. **问题迁移**：如果修复 A 引入了新问题 B（同一 PR/commit 范围内），标记 severity 2
3. **振荡模式**：如果同一区域在短时间内被反复修改（>3次），标记 severity 2
4. **副作用声明**：如果 agent 声称"修复了 X"但 evidence 显示 Y 出现了新问题，标记 severity 3
5. **指标转移**：如果某指标改善但关联指标恶化（如修复性能但破坏正确性），标记 severity 2

{{#domain_rules}}
## 领域规则
{{domain_rules}}
{{/domain_rules}}

## 来源案例
{{source_case}}

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "问题迁移路径：A→B，修复hash/时间线", "reasoning": "一句话"}
```
