# ue5 skillsbench

## 背景

docs/

这个目录是之前做的一版 skillsbench ue5 实现

里边有之前完整的调研文档、设计文档、计划文档

---

D:\Workspace\UnrealProject\UnrealHarnessBenchPS

这个目录是上一版实现

---

skills/UnrealHarness/skills/ue-build

这个目录是我想进行ue5 skills bench基准测试的 skill

---

sample/

这个目录是ue5 的第三人称示例模板

--- 

## 需求

上一版也就是 UnrealHarnessBenchPS 这个版本是用 Powershell 实现的

基准测试出来的报告跟我体感差距非常大而且感觉结果并不对

现在需要你：

- 完整分析之前的文档和实现

- 把基准测试设计的更通用而不是仅局限于指定的几个skill

- 我把ue-lsp、ue-autotest 暂时去掉了，使用ue-build进行测试先跑通

- 参考上一版实现用 python 重写

- 修复上一版基准测试结果失真的问题

如果新的设计和实现比较大，可以分阶段实现或者直接在原先的计划文档里修改