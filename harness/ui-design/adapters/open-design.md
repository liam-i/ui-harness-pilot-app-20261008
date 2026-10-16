# open-design 制作、回读与完整交付

本页说明已验的**所选桌面安装产物 → 绝对 MCP 入口 → 明确 daemon → 固定文件**路线。它不安装工具、不更改全局 MCP 配置，也不证明 Settings／launchSpec 自动安装、自动寻找 daemon 或系统命令回退已验收。桌面包版本与 MCP `serverInfo.version` 分别记录；二者不同不能直接判为错误或当作相同身份。

## 1. 核对本次安装与会话

先选择实际安装产物，记录应用版本、可执行文件、包内 `daemon-cli.mjs` 及其依赖、摘要和使用的 Node／Electron 宿主。在新隔离目录准备本次 `OD_DATA_DIR`；已有制作数据继续使用原目录，不另起空目录假装恢复。核对 daemon 的实际 PID、URL、监听端口、数据目录及操作者，只有 URL 可达不能证明它属于所选安装。

已验桌面产物的 direct MCP 启动形式如下。占位路径由本机观察替换；先核对该产物的帮助与实际 daemon 启动方式，再由所选 MCP 客户端以 stdio 启动此命令。此命令连接已有明确 daemon，不是 daemon 安装或启动器：

```bash
OD_DATA_DIR='/absolute/path/to/this-design-data' \
ELECTRON_RUN_AS_NODE=1 \
  '/absolute/path/to/Open Design.app/Contents/MacOS/Open Design' \
  '/absolute/path/to/Open Design.app/Contents/Resources/app/prebundled/daemon/daemon-cli.mjs' \
  mcp --daemon-url 'http://127.0.0.1:17651'
```

端口是填写示例，不能连接未知的既有进程。客户端完成 MCP `initialize`／`notifications/initialized`，读取实际 `tools/list` 及参数 Schema，保存协议身份和响应。确认能使用本次需要的 `create_project / create_artifact / write_file / get_project / get_artifact` 后才开始 B 制作；A 接收只需要实际获授权的读取能力。不要调用不明来源的 `od`，也不要将系统 `/usr/bin/od` 当作此工具。

身份不明、daemon 不可达或能力缺失时，停在准备环节，由安装负责人核对；可使用已有完整文件走[文件路线](files.md)。不修改 PATH、端口或全局配置来试探性换源。已验路线不要求调用内置模型或付费代理；需要另行使用这些能力时先明确本次范围。

## 2. 制作并回读同一项目

创建或选择授权项目后保存返回的实际 ID。后续使用完整 ID；若工具通过名称匹配返回 `resolvedProject`，先核对命中的是同一项目。按实际 Schema 写入源、tokens 和素材，通过 `get_project` 核对 `id / entryFile / resolvedDir / artifactRef`，预览本轮状态，再通过 `get_artifact` 读取全部内容。保存每次修改、反馈及回读，不把工具自述当作布局或交互通过。

下面是 `tools/call` 的**参数示意**，不是终端命令；字节上限按实际包大小选择，返回仍须核对完整性：

```json
{
  "name": "get_artifact",
  "arguments": {
    "project": "本次实际完整项目ID",
    "entry": "index.html",
    "include": "all",
    "maxBytes": 2000000
  }
}
```

## 3. 完整取回文本与二进制

先确认调用无错误、项目／入口正确、`truncated: false`、`skippedFileCount: 0`。再核对 `files` 的完整、唯一且安全的路径集合，逐项记录 `name / mime / size / binary`。这些条件只是入口检查：**binary 项的 `content: null` 即使伴随 `truncated: false`，仍未交付媒体字节。**

从已经核实的同一项目 `resolvedDir` 取原始媒体，或通过本次已确认可返回完整字节的原媒体接口取得；逐项检查真实大小、格式、尺寸及 SHA-256。文本与 `get_artifact` 内容逐字节比较，二进制与实际源清单比较；路径不能越界、通过符号链接换源或只剩 LFS pointer。下载预览 URL 不等于完整源导出，预览 URL 的会话寿命也不构成固定引用。

在新候选目录导出完整集合，导出前后再次比较同项目源的摘要；有变化、截断、缺图或无法取回字体／外链时拒绝该批。提高响应上限后重新读取也要重做完整性检查；不能只把 `truncated` 字段改成 false。修正原草稿并重新导出，或让来源负责人提供同版本的完整文件。

## 4. 重开与脱离服务恢复

在获授权的专用进程范围内关闭本次会话，先从留存文件在独立目录恢复并核对全部摘要，再用原安装、URL 和数据目录重开同一项目，回读项目 ID、入口、完整文件及媒体。仅有预览再次打开不证明源恢复。不要停止同机无关 daemon；不知道进程归属时保存现场并交负责人。

两种恢复分别记录：服务不可用时固定文件仍可恢复；服务重开时同一项目仍能回读。任一项失败，保留具体缺件和下一操作，不重建同名新项目掩盖丢失。已批准包仍通过固定 Git 历史恢复，不从活动源覆盖。

把完整源、素材、tokens、参考和实际工具观察写入 `sources.md` 与 `manifest.yaml`，沿[人工清单](../manual-checklist.md)形成 D、完整闭包与真实 A。HTML／浏览器交互是设计参考，不能计入 iOS、Android 或 Cocos 的设备用例。工程使用固定包，CI 不连接活动 daemon。

[文件路线](files.md) · [交付入口](../README.md)
