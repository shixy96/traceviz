# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-12

### Added

- 执行 traceroute 并在交互式世界地图上可视化每一跳
- 自动识别中国三大运营商骨干网段（电信 163/CN2、联通 CUNet、移动 CMI 等）
- 延迟突变检测，自动标记可能的跨洋节点
- 支持 macOS / Linux / Windows
- 支持 ICMP 和 UDP 两种探测模式
- 纯 JSON 输出模式，便于脚本集成
- 内置 Demo 模式，无需实际 traceroute 即可体验前端效果
- 中英文双语界面
