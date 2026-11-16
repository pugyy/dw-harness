# Contributing

- `src/` 是唯一真源：hooks / skills / agents / scaffold / dialects 全部改这里。
  `plugins/`、`template/`、`.claude-plugin/marketplace.json` 是**生成物**，
  改完跑 `python scripts/build.py` 重新生成；CI 的 `build --check` 会拒绝漂移。
- 测试：`python -m unittest discover -s tests -t .`（纯标准库即可跑；
  `pip install -e ".[test]"` 额外覆盖 YAML 契约路径）。
- 新规则：在 `src/dw_core/rules.py` 登记（id/默认级别/engine|policy），补
  `tests/test_rules.py` 正反例，必要时在 `src/scaffold/harness.json` 与
  `docs/support-matrix.md` 同步默认值。
- 新 skill：目录名 == frontmatter name，正文 ≤150 行，参考资料放 `references/`。
- 提交信息用中英均可，说明"改了哪个层"（core / hooks / skills / build / docs）。
