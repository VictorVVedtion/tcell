---
name: overcorrection
version: 1
detection_rate: 0.00
fp_rate: 0.00
last_evolved: 2026-03-27T23:51:21Z
---

# Overcorrection Critic

## 检测目标
检测修复过度导致正常功能被误伤的模式。
核心思想：好的修复是精准的手术刀；过度修正是用大锤打苍蝇。

## 检测规则
1. **功能删除**：如果修复 bug 的同时删除了功能/测试/配置，标记 severity 2
2. **过度限制**：如果安全修复过度收紧导致合法操作被阻断，标记 severity 2
3. **类型消失**：如果修复导致某个合法类别/分类从输出中完全消失，标记 severity 3
4. **回退降级**：如果修复 B 的方案是回退到 A 之前的状态，丢失了 A 带来的改进，标记 severity 1
5. **面积不成比例**：如果一个小 bug 的修复涉及大面积代码变更（修改文件数 > bug 影响范围的 3x），标记 severity 1



## 来源案例
(auto-bootstrap for cli-tool): 尚无领域来源案例。测试删除考古可能已挖掘到相关 canary。

## 输出格式
```json
{"detected": true/false, "severity": 0-3, "evidence": "修复目标：[bug描述] → 误伤：[被删除/限制的功能]", "reasoning": "一句话"}
```
