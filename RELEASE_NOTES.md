# dq-doctor v1.0.9

<p align="center">
  <a href="#english">English</a> · <a href="#简体中文">简体中文</a>
</p>

<a id="english"></a>
## English

**Documentation-only maintenance release. No runtime behavior changed.**

v1.0.9 fixes the two stale documentation references left after the repository
rebuild.

### Fixed

- `docs/limitations.md` now points at the CI run that exists on the rebuilt
  repository (`44136716589`, v1.0.8), not the deleted pre-rebuild run.
- README and CONTRIBUTING now report the local suite accurately: **216 passed,
  11 skipped** (227 collected) when optional backend/dashboard extras are not
  installed.

### Install

```bash
pip install -U "dq-doctor==1.0.9"
dqdoctor doctor
```

---

<a id="简体中文"></a>
## 简体中文

**仅文档维护版本，运行行为没有变化。**

v1.0.9 修正仓库重建后遗留的两处过期文档引用。

### 修复

- `docs/limitations.md` 改为引用重建后实际存在的 CI run
  （`44136716589`，v1.0.8），不再指向已删除仓库的旧 run。
- README 和 CONTRIBUTING 改为准确口径：缺可选后端/面板 extras 时，本地
  **216 passed、11 skipped**（共收集 227 项）。

### 安装

```bash
pip install -U "dq-doctor==1.0.9"
dqdoctor doctor
```
