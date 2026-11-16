---
name: dw-requirement-analysis
description: >
  Step 1/8 数仓需求分析：解读 PRD、梳理字段口径草稿、探索上游表结构、
  输出待确认问题清单。适用于接到新数仓需求需要结构化拆解时。
argument-hint: "[需求文档路径或粘贴的需求描述]"
allowed-tools: Read, Grep, Glob, Write
---

# Step 1: 需求分析

## 执行流程

1. 读 PRD/需求描述，提取核心诉求（≤5 行摘要）
2. 结构探索交给 `dw-explorer` agent（防 DDL 刷屏）
3. 产出字段口径草稿：每个字段标注数据来源
4. 列出待确认问题清单（不能省略）
5. 口径落在契约草稿 `contracts/contract.[json|yaml]`（后续步骤共用）

## 交付物（/dw-next 校验）

- `01_requirement.md`：需求摘要 + 字段口径草稿 + 待确认清单
- 契约草稿（若需求涉及新表/改口径）

## 规则

- 待确认问题必须显式列出，宁多勿漏
- 字段口径必须标来源表；金额必须写清币种与单位（分/元/千元）
- 不要在本步写任何 SQL
