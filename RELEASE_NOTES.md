# dq-doctor v1.0.8

<p align="center">
  <a href="#english">English</a> · <a href="#简体中文">简体中文</a>
</p>

<a id="english"></a>
## English

**Maintenance release. No runtime behavior changed.**

v1.0.8 cleans up the test fixture and documentation shipped with 1.0.7, and
rebuilds the wheel/sdist from the corrected tree.

### Fixed

- The SQL-rule bypass fixture now writes `secret.parquet` inside its temporary
  directory and asserts the file exists. It no longer leaves a `LEAKED`
  fixture in the caller's working directory.
- Corrected stale documentation: CI verification status, contributor setup,
  test-count/structure, and the dbt minimum version.
- Removed an unsuitable meta sentence from the v1.0.6 changelog.

### Verification

- 216 tests passed, 11 skipped with optional backend/extras absent in this
  environment; Ruff clean.
- Wheel and sdist rebuilt from the fixed tree.

### Install

```bash
pip install -U "dq-doctor==1.0.8"
dqdoctor doctor
```

---

<a id="简体中文"></a>
## 简体中文

**维护版本，运行行为没有变化。**

v1.0.8 清理了 1.0.7 中的测试 fixture 和文档问题，并用修正后的源码重新构建
wheel/sdist。

### 修复

- SQL 规则绕过测试的 fixture 现在把 `secret.parquet` 写进自己的临时目录，
  并断言文件确实存在；不再在调用方工作目录留下 `LEAKED` 测试文件。
- 修正过期文档：CI 验证状态、贡献指南、测试数量/结构、dbt 最低版本。
- 删除 v1.0.6 changelog 中不合适的 meta 句子。

### 复验

- 当前环境（缺少可选后端/extras）216 passed、11 skipped；Ruff 全绿。
- 从修正后的源码重新构建 wheel/sdist。

### 安装

```bash
pip install -U "dq-doctor==1.0.8"
dqdoctor doctor
```
