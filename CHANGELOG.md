# Changelog

## 当前发布构建 — 2026-10-20

- 新增 `心率悬浮窗安装程序.exe`：安装时选择目标目录，完成后创建桌面快捷方式。
- 安装器会在所选父目录下创建 `HeartRateMonitor`，请求管理员权限，并注册 Windows 卸载项。
- 安装目录提供 `uninstall.exe`；卸载会删除快捷方式、缓存和安装目录。
- 安装版使用安装目录下的 `cache` 保存配置、SQLite 历史和日志，避免旧 AppData
  运行目录的权限问题。
- 保留 `心率悬浮窗.exe` 作为免安装备用版本。

## v1.0.0 — 2026-10-19

首个公开版本。

### 功能

- 通过 BLE 标准心率服务（0x180D / 0x2A37）读取手环、手表、心率带。
- 多设备同时连接，每台设备一个独立悬浮窗。
- 悬浮窗支持模板、心形字符、字体下拉框、字号、颜色、字符间距、背景透明度、描边、阴影、
  圆角、整体透明度等自定义；数字输入框带上下调节箭头。
- 悬浮窗整框可拖动，四角可缩放，文字随框大小缩放；正下方中心带锁定 / 隐藏按钮。
- 主窗口支持多设备同显，可切换为单个设备大图；每张卡片包含最低 / 平均 / 最高 / 采样、
  实时曲线和所选范围历史曲线。已断开设备独立分组，可折叠。
- 心率历史写入本机 SQLite，提供 5 分钟 / 30 分钟 / 1 小时 / 6 小时 / 24 小时折线图，
  每秒刷新，支持 CSV 导出。
- 收藏 / 常用设备、启动自动重连、样式与位置持久化。
- 系统托盘、`Ctrl+Alt+L` 锁定/解锁、`Ctrl+Alt+H` 显示/隐藏全部悬浮窗。

### 修复

- 发布包改为**自定义单文件启动器**：把 onedir 运行时压缩嵌入 exe，
  首次运行解压到 `%LOCALAPPDATA%\HeartRateOverlay\runtime`，
  不再使用 PyInstaller onefile 的系统临时目录，避免
  `Could not create temporary directory!`。
- `release/` 只保留一个 `心率悬浮窗.exe`，不再需要同目录 `_internal`。
- 运行环境固定解压到 `%LOCALAPPDATA%\HeartRateOverlay\runtime`，数据固定保存在
  `%LOCALAPPDATA%\HeartRateOverlay\data`，不再在 exe 同目录创建 `_runtime` / `_data`。
- 补齐 SmartScreen / 文件解除锁定说明和 SHA256 校验文件。

### 验证

- 19 个单元 / 集成测试通过。
- 单文件 exe：首次解压、Demo 双设备启动、真实 BLE 扫描（11 台附近设备）通过。
- 已验证 `WS_EX_TOPMOST` 与锁定后的 `WS_EX_TRANSPARENT` 窗口属性。

### 已知限制

- 仅支持标准 BLE 心率服务；部分设备需要在官方 App 中开启心率广播。
- 独占全屏（Exclusive Fullscreen）无法被普通窗口覆盖，请使用无边框 / 窗口化全屏。
- 未做代码签名，Windows SmartScreen 会提示未知发布者。
