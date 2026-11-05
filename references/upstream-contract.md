# 上游契约入口

联动使用同一份正式契约。仓库版和本地超集都从这里进入。升级时只替换本入口并验证新契约，本地独有 SOP 继续放在原文件。

- [Knowledge Mastery Planner 联动契约](https://github.com/chenwu0409/knowledge-mastery-planner/blob/0b2f09876ba497c345a8f97f5d2014bfff751ed4/references/async-selection.md)
- [KMP v1 schema](https://github.com/chenwu0409/knowledge-mastery-planner/blob/0b2f09876ba497c345a8f97f5d2014bfff751ed4/schemas/kmp-v1.json)

读取这个提交中的契约及校验器，再按当前 RW、版本、批次及审核轮次接续。补搜理由只读任务复盘当前 delivery。题目侧可以保留 RW 与批次指针。无法读取固定版本或校验失败时，保留待验收或待制卷状态。

## 下游工具

- **附件。** 通过 `scripts/lark_client.py` 中的 `upload_attachments` 上传。返回单个已校验的字典，失败抛出 `LarkError` 并保留飞书错误码。KMP 路径遵照上游字段归属，独立模式的整包入库脚本不参与放行。在测试轮里，复用题目只读。
- **动作重叠。** 候选和已保留题可按同一任务要求写稳定动作标签，例如 pivot、arm、rotate。用 `python scripts/action_overlap.py <json>` 比较 `candidate`、`prior` 和 `mandatory` 三个标签数组。去除共同必测动作后按 Jaccard 相似度判断。默认 0.75，任一剩余集合为空时为未知。结果只标疑似重复，交上游复核。题源和题干的去重另做。
- **测试清理。** 每次联调将新建或复用的实际 ID 记入创建清单。默认只预览。已获本轮清理授权时，用 `python scripts/cleanup_test_records.py <manifest.json> --apply` 按 ID 删除并回读。核对同一身份、Base、表和记录 ID 后，仅将 `1254043` 视为记录不存在。遇到错误 Base 或权限不明时停止并报告。

清理清单示例。创建时用测试标记开头设置任务名、题名或批次 ID，并把完整字段值记录为 marker_value。清理前检查该记录在知识库里没有本轮之外的引用，通过后才填 external_references_checked。已有对象标 reused。无需增设线上字段。

```json
{
  "base_token": "ExampleBase",
  "identity": "user",
  "run_marker": "KMP-TEST-036-OFFLINE",
  "records": [
    {
      "kind": "task",
      "table_id": "tblFEVEPllFOztXp",
      "record_id": "recFixture01",
      "ownership": "created",
      "marker_value": "KMP-TEST-036-OFFLINE 示例任务",
      "external_references_checked": true
    }
  ]
}
```

kind 用 batch、task 或 question。脚本依次处理这三类记录，验证失败时报告后续未尝试的 ID。云盘题包等独立文件用本轮单独保存的文件 ID 清单核对后处理。共享文件和复用资产保留。
